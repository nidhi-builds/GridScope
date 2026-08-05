// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SimulatorPage } from "../src/features/simulator/SimulatorPage";

const scenarios = [
  { key: "known_span", label: "Exact known-topology span fault", expected_incident_count: 1, expected_classes: ["span"], boundary_kind: "span", observability: "observable" },
  { key: "firmware_12_silence", label: "Firmware 1.2 terminal silence", expected_incident_count: 0, expected_classes: [], boundary_kind: "span", observability: "unobservable" },
];

const run = {
  id: "RUN-1", scenario: "known_span", status: "completed", started_at: "2026-08-05T10:00:00Z", finished_at: "2026-08-05T10:00:41Z",
  truth: { deenergized: ["P-2", "P-3"], event_ids: ["E-1", "E-2"] },
  expected: { incident_count: 1, classes: ["span"], observability: "observable" },
  actual: { incident_count: 1, classes: ["span"], outcome: "matched", accepted_events: 2, detection_elapsed_seconds: 41, generated_effects: ["known_topology"], effect_evidence: { duplicate: { duplicate_attempts: 1 } } },
  incident_ids: ["INC-9"],
};

const repaired = { ...run, actual: { ...run.actual, repair_outcome: "verified", restoration_elapsed_seconds: 61, repair_accepted_events: 2 } };

const events = {
  items: [
    { id: "E-1", device_id: "D-1", pole_id: "P-2", event_type: "power_lost", device_time: "2026-08-05T10:00:00Z", received_at: "2026-08-05T10:00:02Z", processing_state: "processed", epoch_decision: "in_order" },
    { id: "E-2", device_id: "D-2", pole_id: "P-3", event_type: "power_lost", device_time: "2026-08-05T09:00:00Z", received_at: "2026-08-05T10:00:03Z", processing_state: "audit_only", epoch_decision: "stale" },
    { id: "E-3", device_id: "D-3", pole_id: "P-4", event_type: "heartbeat", device_time: "2026-08-05T10:00:01Z", received_at: "2026-08-05T10:00:04Z", processing_state: "quarantined", epoch_decision: "quarantined" },
  ],
  page: 1, page_size: 100, total: 3,
};

function mockApi(started = run, afterRepair = repaired) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const body = url.includes("/simulator/scenarios") ? scenarios
      : url.includes("/events") ? events
        : url.includes("/repair") ? afterRepair
          : url.includes("/simulator/reset") ? { status: "cleared" }
            : url.endsWith("/simulator/runs") && init?.method === "POST" ? started
              : started;
    return { ok: true, status: 200, json: async () => body } as Response;
  });
}

async function start(scenarioKey = "known_span") {
  render(<SimulatorPage />);
  fireEvent.change(await screen.findByLabelText("Scenario"), { target: { value: scenarioKey } });
  fireEvent.click(screen.getByRole("button", { name: "Start scenario" }));
}

describe("simulator demo view", () => {
  it("runs, compares, repairs, and links to the resulting incident", async () => {
    mockApi();
    await start();

    expect(await screen.findByText("Expected: 1 span incident")).toBeTruthy();
    expect(screen.getByText("Actual: 1 span incident")).toBeTruthy();
    expect(screen.getByText(/Detected in 41s/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "INC-9 (run RUN-1)" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Repair fault" }));
    expect(await screen.findByText("Restoration verified")).toBeTruthy();
    expect(screen.getByText(/Restored in 61s/)).toBeTruthy();
  });

  it("streams generated events with their delivery outcome and keeps ground truth demo-only", async () => {
    mockApi();
    await start();

    const stream = await screen.findByRole("table", { name: "Generated events" });
    const rows = within(stream).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("accepted")).toBeTruthy();
    expect(within(rows[1]).getByText("stale replay")).toBeTruthy();
    expect(within(rows[2]).getByText("quarantined")).toBeTruthy();
    expect(within(rows[1]).getByText("P-3")).toBeTruthy();
    expect(within(stream).getAllByText("2026-08-05T09:00:00Z")).toHaveLength(1);
    expect(screen.getByText("1 duplicate delivery rejected at ingest")).toBeTruthy();
    expect(screen.getByText(/Demo view/)).toBeTruthy();
    expect(screen.getByText(/2 poles de-energized/)).toBeTruthy();
  });

  it("reports an unobservable scenario as expected silence rather than a detection failure", async () => {
    mockApi({
      ...run, scenario: "firmware_12_silence", incident_ids: [],
      expected: { incident_count: 0, classes: [], observability: "unobservable" },
      actual: { ...run.actual, incident_count: 0, classes: [], outcome: "unobservable" },
    });
    await start("firmware_12_silence");

    expect(await screen.findByText("Unobservable by design")).toBeTruthy();
    expect(screen.queryByText(/mismatch/i)).toBeNull();
  });

  it("resets simulator state through the public endpoint and clears the run view", async () => {
    const fetchSpy = mockApi();
    await start();
    expect(await screen.findByText("Expected: 1 span incident")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    await waitFor(() => expect(screen.queryByText("Expected: 1 span incident")).toBeNull());
    expect(fetchSpy.mock.calls.map(([url]) => String(url))).toContain("/api/v1/simulator/reset");
    expect(screen.getByText(/Seed state restored/)).toBeTruthy();
  });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
