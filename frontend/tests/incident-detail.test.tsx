// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IncidentDetail } from "../src/features/incidents/IncidentDetail";
import { loadIncident, ticketAction } from "../src/api/client";

const detail = {
  id: "INC-1", fault_class: "span", status: "crew_assigned", location_class: "corridor", affected_count: 12, affected_count_estimated: true,
  confidence: { level: "medium", reasons: ["Topology is inferred"] }, navigation: { latitude: 12.9, longitude: 77.5 }, pin: { value: "560001", source: "estimated" },
  boundary: { kind: "corridor", upstream_pole_id: "P-1", downstream_pole_id: "P-5", candidate_spans: ["P-1 to P-5"], geometry: { pole_path: ["P-1", "P-2", "P-3", "P-4", "P-5"] } },
  location_history: [{ kind: "span", upstream_pole_id: "P-1", downstream_pole_id: "P-3", candidate_spans: [], geometry: {} }, { kind: "corridor", upstream_pole_id: "P-1", downstream_pole_id: "P-5", candidate_spans: [], geometry: {} }], topology: { source: "inferred", calibration_bucket: "medium" }, evidence: { class_counts: { confirmed_dark: 2, uninstrumented: 3 }, items: [{ id: "E-1", class: "confirmed_dark", event_id: "event-1", event_type: "power_lost", details: {} }], page: 1, page_size: 50, total: 1 }, schedule_overlap: null,
  ticket_events: [{ id: "T-1", type: "assign_crew", from_status: "acknowledged", to_status: "crew_assigned", actor: "operator", reason: "Crew assigned", evidence_ids: [], occurred_at: "2026-08-05T10:00:00Z" }],
  ai_explanation: { status: "fallback", text: { english: "A likely outage needs verification.", kannada: "ಪರಿಶೀಲನೆ ಅಗತ್ಯವಿದೆ." }, fallback_reason: "missing_api_key", generated_at: "2026-08-05T10:00:00Z" },
};

describe("incident detail", () => {
  it("shows corridor uncertainty, evidence, allowed repair action, and its typed rejection", async () => {
    const onAction = vi.fn().mockRejectedValue({ code: "confirmed_dark_remains", incident: detail });
    render(<IncidentDetail detail={detail} onAction={onAction} />);

    expect(screen.getByText("Search corridor")).toBeTruthy();
    expect(screen.getByText(/3 uninstrumented poles/)).toBeTruthy();
    expect(screen.getByText("Hypothesis history")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Report repair" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Report repair" }));
    await waitFor(() => expect(screen.getByText(/still reporting dark/)).toBeTruthy());
    expect(onAction).toHaveBeenCalledWith("report-resolved");
  });

  it("keeps deterministic detail usable when the explanation is fallback or unavailable", () => {
    const { rerender } = render(<IncidentDetail detail={detail} onAction={vi.fn()} />);
    expect(screen.getByText(/AI explanation cannot change incident facts/)).toBeTruthy();
    expect(screen.getByText(/Deterministic fallback/)).toBeTruthy();
    rerender(<IncidentDetail detail={{ ...detail, ai_explanation: null }} onAction={vi.fn()} />);
    expect(screen.getByText("Explanation unavailable")).toBeTruthy();
    expect(screen.getByText("INC-1")).toBeTruthy();
  });

  it("refreshes the selected workspace after an accepted ticket action", async () => {
    const onChanged = vi.fn();
    render(<IncidentDetail detail={{ ...detail, status: "detected" }} onAction={vi.fn().mockResolvedValue({ incident: { ...detail, status: "acknowledged" } })} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(screen.getByText(/acknowledged/)).toBeTruthy();
  });

  it("uses the detail and typed ticket endpoints", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => ({
      ok: String(url).endsWith("/INC-1"),
      json: async () => String(url).endsWith("/INC-1") ? detail : { detail: { code: "invalid_transition", incident: detail } },
    }) as Response);
    await expect(loadIncident("INC-1")).resolves.toMatchObject({ id: "INC-1" });
    await expect(ticketAction("INC-1", "report-resolved")).rejects.toMatchObject({ code: "invalid_transition" });
    expect(fetchSpy.mock.calls.map(([url]) => String(url))).toContain("/api/v1/incidents/INC-1/report-resolved");
  });
});

afterEach(() => { cleanup(); });
