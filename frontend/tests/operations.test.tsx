// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("react-leaflet", () => ({ GeoJSON: () => null, MapContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>, TileLayer: () => null, useMap: () => undefined }));

import { loadIncidentGeometry, loadOperations } from "../src/api/client";
import { IncidentQueue, sortIncidents } from "../src/features/operations/IncidentQueue";
import { emptyFilters, filterIncidents, IncidentFilters } from "../src/features/operations/IncidentFilters";
import { MapLegend } from "../src/features/operations/MapLegend";
import { POLE_LABEL, POLE_STYLE } from "../src/features/operations/NetworkLayer";
import { isGeometryForIncident } from "../src/features/operations/NetworkMap";
import { OperationsPage } from "../src/features/operations/OperationsPage";
import { OperationsProvider } from "../src/features/operations/OperationsProvider";
import type { IncidentSummary } from "../src/api/types";

const incidents: IncidentSummary[] = [
  { id: "resolved", fault_class: "span", status: "resolved", location_class: "span", affected_count: 80, confidence: { level: "high", reasons: [] }, navigation: { latitude: 12, longitude: 77 }, pin: { value: "1", source: "registry" }, feeder_id: "f-1", transformer_id: "dt-1", pole_id: null, updated_at: "2026-08-05T10:00:00Z" },
  { id: "new-small", fault_class: "span", status: "detected", location_class: "span", affected_count: 2, confidence: { level: "medium", reasons: [] }, navigation: { latitude: 12, longitude: 77 }, pin: { value: "1", source: "registry" }, feeder_id: "f-1", transformer_id: "dt-1", pole_id: null, updated_at: "2026-08-05T08:00:00Z" },
  { id: "new-large", fault_class: "feeder", status: "detected", location_class: "feeder", affected_count: 20, confidence: { level: "high", reasons: [] }, navigation: { latitude: 12, longitude: 77 }, pin: { value: "1", source: "registry" }, feeder_id: "f-2", transformer_id: null, pole_id: null, updated_at: "2026-08-05T09:00:00Z" },
];

describe("operator workspace", () => {
  it("prioritizes unacknowledged incidents and exposes a selected queue row", () => {
    expect(sortIncidents(incidents).map(({ id }) => id)).toEqual(["new-large", "new-small", "resolved"]);
    const html = renderToStaticMarkup(<IncidentQueue incidents={incidents} selectedIncidentId="new-large" onSelect={() => {}} />);
    expect(html).toContain('aria-label="Incident queue"');
    expect(html).toContain('aria-current="true"');
  });

  it("loads only compact operational summaries on first render", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 0 }) } as Response);

    await loadOperations();

    expect(fetchSpy.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/v1/ready",
      "/api/v1/incidents?page=1&page_size=100",
      "/api/v1/planned-operations?page=1&page_size=100",
      "/api/v1/device-health?page=1&page_size=1",
    ]);
  });

  it("filters only incidents explicitly linked to a planned operation", () => {
    expect(filterIncidents(incidents, { ...emptyFilters, planned: "linked" }, new Set(["new-large"])).map(({ id }) => id)).toEqual(["new-large"]);
  });

  it("offers a functional planned-incident filter", () => {
    const html = renderToStaticMarkup(<IncidentFilters incidents={incidents} filters={emptyFilters} onChange={() => {}} />);

    expect(html).toContain('aria-label="Planned"');
  });

  it("requests incident geometry only when a selected id is supplied", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ type: "FeatureCollection", features: [] }) } as Response);

    await loadIncidentGeometry("new-large");

    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/network/incidents/new-large", expect.objectContaining({ headers: { Accept: "application/json" } }));
  });

  const workspaceFetch = () => vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => ({
    ok: true,
    json: async () => String(url).includes("/ready") ? { database: "ready", seed: "ready", worker: "ready", last_processed_at: null, unprocessed_count: 0, oldest_backlog_age_seconds: null }
      : String(url).includes("/incidents?") ? { items: incidents, page: 1, page_size: 100, total: incidents.length }
        : String(url).includes("/planned-operations") ? { items: [], page: 1, page_size: 100, total: 0 }
          : String(url).includes("/device-health") ? { items: [], page: 1, page_size: 1, total: 0 }
            : { type: "FeatureCollection", features: [{ type: "Feature", properties: { incident_id: String(url).split("/").pop() }, geometry: { type: "Point", coordinates: [77, 12] } }] },
  }) as Response);

  it("draws the whole visible queue on the map before anything is selected", async () => {
    const fetchSpy = workspaceFetch();

    render(<OperationsProvider><OperationsPage /></OperationsProvider>);

    await waitFor(() => expect(screen.getByTestId("network-map").getAttribute("data-network-features")).toBe("3"));
    const requested = fetchSpy.mock.calls.map(([url]) => String(url));
    for (const { id } of incidents) expect(requested).toContain(`/api/v1/network/incidents/${id}`);
  });

  it("moves the selected incident out of the background layer when a ticket is clicked", async () => {
    workspaceFetch();

    render(<OperationsProvider><OperationsPage /></OperationsProvider>);
    await waitFor(() => expect(screen.getByTestId("network-map").getAttribute("data-network-features")).toBe("3"));
    fireEvent.click(await screen.findByRole("button", { name: "new-large" }));

    await waitFor(() => expect(screen.getByTestId("network-map").getAttribute("data-selected")).toBe("new-large"));
    await waitFor(() => expect(screen.getByTestId("network-map").getAttribute("data-network-features")).toBe("2"));
  });

  it("keeps the selected ticket in the URL so it survives a route change", async () => {
    workspaceFetch();

    render(<OperationsProvider><OperationsPage /></OperationsProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "new-large" }));

    await waitFor(() => expect(new URLSearchParams(window.location.search).get("incident")).toBe("new-large"));
    // Primary navigation carries the selection, rather than dropping it at the
    // first tab switch.
    expect(screen.getByLabelText("Simulator (demo)").getAttribute("href")).toBe("/simulator?incident=new-large");
  });

  it("resets the queue view without touching any incident", async () => {
    workspaceFetch();

    render(<OperationsProvider><OperationsPage /></OperationsProvider>);
    const reset = await screen.findByRole("button", { name: "Reset queue view" });
    expect(reset.hasAttribute("disabled")).toBe(true);

    fireEvent.change(await screen.findByLabelText("Status"), { target: { value: "detected" } });
    fireEvent.click(await screen.findByRole("button", { name: "new-large" }));
    await waitFor(() => expect(reset.hasAttribute("disabled")).toBe(false));
    fireEvent.click(reset);

    await waitFor(() => expect(new URLSearchParams(window.location.search).get("incident")).toBeNull());
    expect((await screen.findByLabelText("Status") as HTMLSelectElement).value).toBe("");
    // The full queue is back, so nothing was removed.
    expect(await screen.findByRole("button", { name: "resolved" })).toBeTruthy();
  });

  it("never renders geometry from a previously selected incident", () => {
    const geometry = {
      type: "FeatureCollection" as const,
      features: [{ type: "Feature" as const, properties: { incident_id: "old" }, geometry: { type: "Point" as const, coordinates: [77, 12] } }],
    };

    expect(isGeometryForIncident(geometry, "old")).toBe(true);
    expect(isGeometryForIncident(geometry, "new")).toBe(false);
  });

  it("explains each map symbol in words an operator can act on", () => {
    const html = renderToStaticMarkup(<MapLegend />);

    expect(html).toContain("send the crew here");
    expect(html).toContain("Exact span");
    expect(html).toContain("Search corridor");
    expect(html).toContain("wiring unrecorded");
  });

  it("distinguishes a silent pole from one that has no sensor at all", () => {
    const html = renderToStaticMarkup(<MapLegend />);

    // Silence is an absence of information, never evidence of an outage. The map
    // must not let an operator read grey as dark.
    expect(html).toContain("Not reporting");
    expect(html).toContain("never assumed dark");
    expect(html).toContain("No sensor");
    expect(POLE_LABEL.unknown_silent).not.toEqual(POLE_LABEL.uninstrumented);
    expect(POLE_STYLE.confirmed_dark.fill).not.toEqual(POLE_STYLE.unknown_silent.fill);
  });

  it("reaches the API-unavailable state instead of loading forever on a cold-start failure", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));

    render(<OperationsProvider><OperationsPage /></OperationsProvider>);

    expect(await screen.findByText("API unavailable")).toBeTruthy();
    expect(screen.queryByText("Loading operations")).toBeNull();
  });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); window.history.replaceState({}, "", "/operations"); });
