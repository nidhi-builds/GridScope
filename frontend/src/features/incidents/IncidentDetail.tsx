import { useEffect, useState } from "react";
import { loadIncident, ticketAction } from "../../api/client";
import type { IncidentDetail as Detail } from "../../api/types";

type Action = "acknowledge" | "assign" | "report-resolved";
const allowed = (status: string): { label: string; action: Action } | undefined =>
  status === "detected" ? { label: "Acknowledge", action: "acknowledge" }
    : status === "acknowledged" ? { label: "Assign crew", action: "assign" }
      : status === "crew_assigned" ? { label: "Report repair", action: "report-resolved" } : undefined;

export function IncidentDetail({ incidentId, detail: supplied, onAction, onChanged }: { incidentId?: string; detail?: Detail; onAction?: (action: Action) => Promise<unknown> | unknown; onChanged?: () => void }) {
  const [detail, setDetail] = useState<Detail | undefined>(supplied);
  const [message, setMessage] = useState("");
  const [language, setLanguage] = useState<"english" | "kannada">("english");
  useEffect(() => {
    setDetail(supplied); setMessage("");
    if (!incidentId || supplied) return;
    const controller = new AbortController();
    void loadIncident(incidentId, controller.signal).then(setDetail).catch(() => !controller.signal.aborted && setMessage("Incident detail unavailable"));
    return () => controller.abort();
  }, [incidentId, supplied]);
  if (!detail) return incidentId ? <aside className="incident-detail" aria-label="Incident detail">{message || "Loading incident detail..."}</aside> : null;
  const action = allowed(detail.status);
  const repair = async () => {
    if (!action) return;
    setMessage("");
    try {
      const result = await (onAction ? onAction(action.action) : ticketAction(detail.id, action.action)) as { incident?: Detail };
      if (result.incident) setDetail(result.incident);
      onChanged?.();
    } catch (error) {
      const rejected = error as { code?: string; incident?: Detail };
      if (rejected.incident) setDetail(rejected.incident);
      setMessage(rejected.code === "confirmed_dark_remains" ? "Repair rejected: poles are still reporting dark." : `Ticket update rejected: ${rejected.code ?? "unavailable"}.`);
    }
  };
  const path = detail.boundary.geometry.pole_path ?? [];
  return <aside className="incident-detail" aria-label="Incident detail">
    <h2>{detail.id}</h2><p>{detail.fault_class} / {detail.confidence.level} confidence / {detail.status.replace("_", " ")}</p>
    <p>{detail.affected_count}{detail.affected_count_estimated ? " estimated" : ""} affected / PIN {detail.pin.value ?? "unavailable"} ({detail.pin.source ?? "unknown"})</p>
    <p>Navigation: {detail.navigation.latitude}, {detail.navigation.longitude} / Updated {detail.updated_at}</p>
    {detail.confidence.reasons.length > 0 && <p>Confidence reasons: {detail.confidence.reasons.join(" / ")}</p>}
    <h3>{detail.boundary.kind === "corridor" ? "Search corridor" : detail.boundary.kind}</h3>
    {detail.boundary.kind === "corridor" && <p>{Math.max(0, path.length - 2)} uninstrumented poles between {detail.boundary.upstream_pole_id} and {detail.boundary.downstream_pole_id}.</p>}
    {detail.boundary.candidate_spans.length > 0 && <p>Candidate spans: {detail.boundary.candidate_spans.map((span) => typeof span === "string" ? span : JSON.stringify(span)).join(" / ")}</p>}
    {path.length > 0 && <p>Intervening poles: {path.join(" -> ")}</p>}
    {detail.location_history.length > 1 && <><h3>Hypothesis history</h3><ul>{detail.location_history.map((boundary, index) => <li key={`${boundary.kind}-${index}`}>{boundary.kind}: {boundary.upstream_pole_id ?? "unknown"} to {boundary.downstream_pole_id ?? "unknown"}</li>)}</ul></>}
    <p>Topology: {detail.topology.source}{detail.topology.calibration_bucket ? ` (calibration ${detail.topology.calibration_bucket})` : ""}{detail.topology.source === "inferred" ? " (affected count is estimated)" : ""}.</p>
    {detail.schedule_overlap && <p>Scheduled overlap: {detail.schedule_overlap.status}{detail.schedule_overlap.promotion_outcome ? ` (${detail.schedule_overlap.promotion_outcome})` : ""}</p>}
    <h3>Evidence</h3><p>{Object.entries(detail.evidence.class_counts).map(([kind, count]) => `${count} ${kind.replaceAll("_", " ")}`).join(" / ") || "No evidence"}</p><ul>{detail.evidence.items.map((event) => <li key={event.id}>{event.event_type ?? event.class}: {JSON.stringify(event.details)}</li>)}</ul>
    <h3>Ticket history</h3><ul>{detail.ticket_events.map((event) => <li key={event.id}>{event.occurred_at}: {event.reason}</li>)}</ul>
    {action && <button onClick={repair}>{action.label}</button>}{message && <p role="alert">{message}</p>}
    <h3>Explanation</h3>{detail.ai_explanation ? <><p>{detail.ai_explanation.status === "fallback" ? "Deterministic fallback" : "Generated explanation"}</p><button aria-pressed={language === "english"} onClick={() => setLanguage("english")}>English</button><button aria-pressed={language === "kannada"} onClick={() => setLanguage("kannada")}>Kannada</button><p>{detail.ai_explanation.text[language]}</p><p>AI explanation cannot change incident facts or ticket status.</p></> : <><p>Explanation unavailable</p><p>AI explanation cannot change incident facts or ticket status.</p></>}
  </aside>;
}
