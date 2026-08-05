// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DeviceHealthPage } from "../src/features/health/DeviceHealthPage";
import { PlannedOperationsPage } from "../src/features/health/PlannedOperationsPage";
import { SystemHealthPage } from "../src/features/health/SystemHealthPage";
import { loadDeviceHealth, loadPlannedOperations } from "../src/api/client";

const planned = {
  items: [{
    id: "PO-1", incident_id: null, status: "matched", scope: { transformer_id: "T-1" },
    scheduled_start: "2026-08-05T09:00:00Z", scheduled_end: "2026-08-05T10:00:00Z",
    observed_start: "2026-08-05T09:12:00Z", observed_end: null,
    end_grace_minutes: 40, source_updated_at: "2026-08-04T09:00:00Z", snapshot_stale: true,
    promotion_outcome: "suppressed",
  }],
  page: 1, page_size: 25, total: 1,
};

const devices = {
  items: [{
    device_id: "D-1", serial_number: "SN-1", pole_id: "P-1", is_online: false,
    battery_pct: 12, rssi_dbm: -119, evidence_class: "unknown_silent", device_health: "offline",
    mismatch_events: 2, stale_replay_events: 1,
  }],
  page: 1, page_size: 25, total: 1,
};

const readiness = {
  database: "ready", seed: "ready", worker: "ready", ai: "unconfigured",
  last_processed_at: "2026-08-05T10:00:00Z", unprocessed_count: 7, oldest_backlog_age_seconds: 42,
};

describe("planned operations view", () => {
  it("shows published and observed timing, match state, grace, and stale source without a fault ticket", () => {
    render(<PlannedOperationsPage page={planned} />);

    expect(screen.getByText(/transformer_id/)).toBeTruthy();
    expect(screen.getByText(/Published 2026-08-05T09:00:00Z to 2026-08-05T10:00:00Z/)).toBeTruthy();
    expect(screen.getByText(/Observed 2026-08-05T09:12:00Z to running/)).toBeTruthy();
    expect(screen.getByText("matched")).toBeTruthy();
    expect(screen.getByText(/40 minute end grace/)).toBeTruthy();
    expect(screen.getByText(/Schedule snapshot is stale/)).toBeTruthy();
    expect(screen.getByText(/suppressed/)).toBeTruthy();
    expect(screen.getByText(/Planned work is not a fault ticket/)).toBeTruthy();
  });
});

describe("device health view", () => {
  it("shows silence, offline, mismatch, stale replay, battery, and RSSI as maintenance, not outages", () => {
    render(<DeviceHealthPage page={devices} />);

    expect(screen.getByText(/Device health is not a power outage/)).toBeTruthy();
    expect(screen.getByText("offline")).toBeTruthy();
    expect(screen.getByText("silent")).toBeTruthy();
    expect(screen.getByText("12%")).toBeTruthy();
    expect(screen.getByText("-119 dBm")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("1")).toBeTruthy();
    expect(screen.getByText(/Duplicate deliveries are rejected at ingest/)).toBeTruthy();
  });
});

describe("system health view", () => {
  it("shows seed, worker, backlog, database, API, map tiles, and AI availability", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, status: 200, json: async () => ({}) } as Response);
    render(<SystemHealthPage readiness={readiness} />);

    expect(screen.getByText("Database: ready")).toBeTruthy();
    expect(screen.getByText("Seed: ready")).toBeTruthy();
    expect(screen.getByText("Worker: ready")).toBeTruthy();
    expect(screen.getByText("API: reachable")).toBeTruthy();
    expect(screen.getByText("AI explanations: unconfigured")).toBeTruthy();
    expect(screen.getByText("Backlog: 7 events, oldest 42s")).toBeTruthy();
    expect(screen.getByText("Last processed: 2026-08-05T10:00:00Z")).toBeTruthy();
    expect(await screen.findByText("Map tiles: reachable")).toBeTruthy();
  });

  it("reports an unreachable API instead of an empty page", () => {
    render(<SystemHealthPage error={new Error("offline")} />);
    expect(screen.getByText("API: unreachable")).toBeTruthy();
  });
});

describe("secondary operational api", () => {
  it("reads planned operations and device health from their paginated endpoints", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => ({
      ok: true, status: 200, json: async () => String(input).includes("planned-operations") ? planned : devices,
    }) as Response);

    await expect(loadPlannedOperations()).resolves.toMatchObject({ total: 1 });
    await expect(loadDeviceHealth()).resolves.toMatchObject({ total: 1 });
    const urls = fetchSpy.mock.calls.map(([url]) => String(url));
    expect(urls.some((url) => url.startsWith("/api/v1/planned-operations?"))).toBe(true);
    expect(urls.some((url) => url.startsWith("/api/v1/device-health?"))).toBe(true);
  });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
