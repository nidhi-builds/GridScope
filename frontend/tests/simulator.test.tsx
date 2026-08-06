// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SimulatorPage } from "../src/features/simulator/SimulatorPage";
import { OperationsProvider } from "../src/features/operations/OperationsProvider";

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

const incidentDetail = {
  id: "INC-9", fault_class: "span", status: "detected", location_class: "span", affected_count: 4,
  confidence: { level: "high", reasons: ["topology:registry"] },
  navigation: { latitude: 12, longitude: 77 }, pin: { value: "1", source: "registry" },
  feeder_id: "f-1", transformer_id: "dt-1", pole_id: null, updated_at: "2026-08-05T10:00:00Z",
  affected_count_estimated: false,
  boundary: { kind: "span", upstream_pole_id: "P-1", downstream_pole_id: "P-2", geometry: { pole_path: ["P-1", "P-2"] } },
  location_history: [], topology: { source: "registry", calibration_bucket: null },
  evidence: { class_counts: { confirmed_dark: 4 }, items: [], page: 1, page_size: 1, total: 0 },
  schedule_overlap: null, ticket_events: [], ai_explanation: null,
};

function mockApi(started = run, afterRepair = repaired) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const body = url.includes("/simulator/scenarios") ? scenarios
      : url.includes("/events") ? events
        : url.includes("/repair") ? afterRepair
          : url.includes("/simulator/reset") ? { status: "cleared" }
            : url.includes("/api/v1/incidents/") ? incidentDetail
              : url.endsWith("/simulator/runs") && init?.method === "POST" ? started
                : started;
    return { ok: true, status: 200, json: async () => body } as Response;
  });
}

async function start(scenarioKey = "known_span") {
  render(<OperationsProvider><SimulatorPage /></OperationsProvider>);
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

  it("opens the run's incident ticket in place so the fault can be repaired without leaving", async () => {
    mockApi();
    await start();

    fireEvent.click(await screen.findByRole("link", { name: "INC-9 (run RUN-1)" }));

    expect(await screen.findByLabelText("Selected incident ticket")).toBeTruthy();
    // Selection lives in the URL, so it survives a reload and every other tab.
    expect(new URLSearchParams(window.location.search).get("incident")).toBe("INC-9");
  });

  it("restores a ticket selected on another route from the URL alone", async () => {
    mockApi();
    window.history.replaceState({}, "", "/simulator?incident=INC-9");

    render(<OperationsProvider><SimulatorPage /></OperationsProvider>);

    expect(await screen.findByLabelText("Selected incident ticket")).toBeTruthy();
  });

  it("names the poles that reported power back, as the evidence that closes the ticket", async () => {
    const restored = {
      items: [
        ...events.items,
        { id: "E-4", device_id: "D-1", pole_id: "P-2", event_type: "power_restored", device_time: "2026-08-05T10:01:00Z", received_at: "2026-08-05T10:01:02Z", processing_state: "processed", epoch_decision: "in_order" },
        { id: "E-5", device_id: "D-2", pole_id: "P-3", event_type: "power_restored", device_time: "2026-08-05T10:01:01Z", received_at: "2026-08-05T10:01:03Z", processing_state: "processed", epoch_decision: "in_order" },
      ],
      page: 1, page_size: 100, total: 5,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => ({
      ok: true, status: 200,
      json: async () => String(url).includes("/simulator/scenarios") ? scenarios
        : String(url).includes("/events") ? restored
          : String(url).includes("/api/v1/incidents/") ? incidentDetail : run,
    }) as Response);

    await start();

    const proof = await screen.findByLabelText("Restoration telemetry");
    expect(within(proof).getByText("2 poles reported power back after the repair")).toBeTruthy();
    expect(within(proof).getByText("P-2")).toBeTruthy();
    expect(within(proof).getByText("P-3")).toBeTruthy();
    expect(within(proof).getByText(/closes on these events, not on the crew's report/)).toBeTruthy();
  });

  it("hides only the ticket panel, keeping the run and event stream on screen", async () => {
    mockApi();
    await start();
    fireEvent.click(await screen.findByRole("link", { name: "INC-9 (run RUN-1)" }));
    await screen.findByLabelText("Selected incident ticket");

    fireEvent.click(screen.getByRole("button", { name: "Hide this ticket" }));

    await waitFor(() => expect(screen.queryByLabelText("Selected incident ticket")).toBeNull());
    // The run must survive: hiding a ticket is not leaving the simulator.
    expect(screen.getByLabelText("Run comparison")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Generated events" })).toBeTruthy();
    expect(screen.getByLabelText("Scenario controls")).toBeTruthy();
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

afterEach(() => { cleanup(); vi.restoreAllMocks(); window.history.replaceState({}, "", "/operations"); });
