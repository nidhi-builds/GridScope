import { useEffect, useState } from "react";
import { loadIncident, repairRun, ticketAction } from "../../api/client";
import type { IncidentDetail as Detail } from "../../api/types";

type Action = "acknowledge" | "assign" | "report-resolved";
const allowed = (status: string): { label: string; action: Action } | undefined =>
  status === "detected" ? { label: "Acknowledge", action: "acknowledge" }
    : status === "acknowledged" ? { label: "Assign crew", action: "assign" }
      : status === "crew_assigned" ? { label: "Report repair", action: "report-resolved" } : undefined;

/** Plain-language equivalents. Operators should never read a machine token. */
const STATUS: Record<string, string> = {
  detected: "New — not yet acknowledged", acknowledged: "Acknowledged", crew_assigned: "Crew assigned",
  resolved: "Repair reported — awaiting telemetry", verified: "Restoration verified", closed: "Closed",
};
const FAULT: Record<string, string> = {
  span: "Fault on one span of line", corridor: "Fault somewhere along a corridor",
  dt: "Whole transformer area is out", feeder: "Whole feeder is out", device_issue: "Sensor problem, not an outage",
};
const EVIDENCE: Record<string, string> = {
  confirmed_dark: "poles confirmed without power", confirmed_live: "poles confirmed with power",
  unknown_silent: "poles not reporting (no information)", uninstrumented: "poles with no sensor",
  device_suspect: "poles whose sensor is unreliable",
};
const TICKET: Record<string, string> = {
  acknowledge: "Acknowledged by operator", assign_crew: "Crew assigned", report_resolved: "Repair reported by crew",
  verified: "Restoration verified from telemetry", closed: "Ticket closed", rejected: "Action rejected",
};

/** `topology-ambiguity:0.00` means nothing at 2 a.m. These do. */
function explainReason(code: string): string | null {
  const [key, value] = code.split(":");
  switch (key) {
    case "topology": return value === "registry"
      ? "Wiring for this transformer is on record, so the span is exact"
      : "Wiring here was never recorded, so the location is a corridor, not a point";
    case "boundary": return value === "exact" ? "Fault narrowed to a single span" : "Fault narrowed to a corridor only";
    case "direct-dark": return `${value} poles reported loss of power directly`;
    case "downstream-coverage": return `${Math.round(Number(value) * 100)}% of poles below the fault have a working sensor`;
    case "silent": return `${value} poles stopped reporting — treated as unknown, not as an outage`;
    case "no-post-onset-live": return "No pole upstream confirmed power after the fault began";
    case "unknown-or-offline": return `${value} poles could not be checked`;
    case "live-contradiction": return "A pole inside the affected area still reports power";
    case "schedule-overlap": return "Overlaps planned work — treat with care";
    default: return null;
  }
}

const shortId = (value?: string | null) => value ? value.slice(0, 8) : "unknown";
const when = (value?: string | null) => value ? new Date(value).toLocaleString() : "unknown";

export function IncidentDetail({ incidentId, detail: supplied, onAction, onChanged, version, allowDemoRepair = false }: { incidentId?: string; detail?: Detail; onAction?: (action: Action) => Promise<unknown> | unknown; onChanged?: () => void; version?: string; allowDemoRepair?: boolean }) {
  const [detail, setDetail] = useState<Detail | undefined>(supplied);
  const [message, setMessage] = useState("");
  const [language, setLanguage] = useState<"english" | "kannada">("english");
  const [working, setWorking] = useState(false);
  useEffect(() => {
    // `version` is the incident's updated_at from the polled queue. Without it
    // the panel fetched once and then went stale: restoration is verified by
    // telemetry, so an operator watching this panel would never see the ticket
    // move from "repair reported" to "closed" that it promises will happen.
    setMessage("");
    if (!incidentId || supplied) { setDetail(supplied); return; }
    const controller = new AbortController();
    void loadIncident(incidentId, controller.signal).then(setDetail).catch(() => !controller.signal.aborted && setMessage("Incident detail unavailable"));
    return () => controller.abort();
  }, [incidentId, supplied, version]);
  if (!detail) return incidentId ? <aside className="incident-detail" aria-label="Incident detail">{message || "Loading incident detail..."}</aside> : null;
  // A malformed payload must degrade to a message, not tear down the workspace.
  // Losing the queue and the map because one detail response was wrong is the
  // worst possible failure in a control room.
  if (!detail.boundary?.geometry || !detail.confidence) return <aside className="incident-detail" aria-label="Incident detail">Incident detail unavailable</aside>;
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
  /** Restore power in the simulated world, then let the normal pipeline close it. */
  const fixFault = async () => {
    if (!detail.simulation_id) return;
    setWorking(true);
    setMessage("");
    try {
      await repairRun(detail.simulation_id);
      setDetail(await loadIncident(detail.id));
      onChanged?.();
    } catch {
      setMessage("The simulated repair could not be applied.");
    } finally {
      setWorking(false);
    }
  };
  const path = detail.boundary.geometry.pole_path ?? [];
  const corridor = detail.boundary.kind === "corridor";
  // A feeder or transformer outage has no upstream/downstream pole: the whole
  // group below the asset is out. Printing "between pole unknown and pole
  // unknown" sent a crew looking for a span that does not exist.
  const scope = detail.boundary.kind === "feeder" || detail.fault_class === "feeder" ? "feeder"
    : detail.boundary.kind === "transformer" || detail.fault_class === "dt" ? "dt"
      : undefined;
  const span = Boolean(detail.boundary.upstream_pole_id && detail.boundary.downstream_pole_id);
  const reasons = (detail.confidence.reasons ?? []).map(explainReason).filter(Boolean) as string[];
  const uninstrumented = Math.max(0, path.length - 2);
  return <aside className="incident-detail" aria-label="Incident detail">
    <h2>{FAULT[detail.fault_class] ?? detail.fault_class}</h2>
    <div className="detail-headline">
      <span className={`badge ${detail.confidence.level}`}>{detail.confidence.level} confidence</span>
      <span className="badge status">{STATUS[detail.status] ?? detail.status}</span>
    </div>

    {/* The one thing a crew is dispatched on. Everything else is supporting
        detail, so this gets the top of the panel and the visual weight. */}
    <div className="detail-where">
      <span className="detail-where-label">{scope ? "What is out" : corridor ? "Where to search" : "Where the fault is"}</span>
      {scope === "feeder"
        ? <p><b>The whole feeder is out</b> — {detail.affected_count} poles below it.
          Start at the feeder source; this is not a single span.</p>
        : scope === "dt"
          ? <p><b>The whole transformer area is out</b> — {detail.affected_count} poles below it.
            Check the transformer before walking the line.</p>
          : !span
            ? <p><b>Not narrowed to a span yet</b>. Use the coordinates below and the map.</p>
            : corridor
              ? <p><b>Between pole {shortId(detail.boundary.upstream_pole_id)} and pole {shortId(detail.boundary.downstream_pole_id)}</b>
                {uninstrumented > 0 ? `, with ${uninstrumented} pole${uninstrumented === 1 ? "" : "s"} in between that have no sensor` : ""}.
                The wiring here was never recorded, so the system cannot narrow it further.</p>
              : <p><b>On the span between pole {shortId(detail.boundary.upstream_pole_id)} and pole {shortId(detail.boundary.downstream_pole_id)}</b>.</p>}
    </div>

    <div className="detail-facts">
      <div><span className="label">Send crew to</span><span>{detail.navigation.latitude}, {detail.navigation.longitude}</span></div>
      <div><span className="label">Poles affected</span><span>{detail.affected_count}{detail.affected_count_estimated ? " (estimated — wiring not fully recorded)" : ""}</span></div>
      <div><span className="label">Area PIN</span><span>{detail.pin.value ?? "not on record"}</span></div>
    </div>

    <div className="ticket-actions">
      {action && <button className="ticket-action" onClick={repair} disabled={working}>{action.label}</button>}
      {/* Demo-only, and confined to the simulator route. Operations is the
          operator's workspace: injecting a repair into the simulated world is
          not something that should be reachable from a real ticket queue. */}
      {allowDemoRepair && detail.simulation_id && detail.status !== "closed" && detail.status !== "verified" &&
        <button className="demo-action" onClick={fixFault} disabled={working}>Repair this fault (demo)</button>}
    </div>
    {message && <p role="alert">{message}</p>}
    {/* Stated up front, not only once the ticket reaches "resolved". */}
    {!action && detail.status === "detected" ? null : <p className="detail-note">
      {detail.status === "resolved" ? "Repair reported. Waiting for the affected poles to report power and hold it for 30 seconds. No manual close."
        : detail.status === "verified" ? "Restoration confirmed by telemetry. Closing."
          : detail.status === "closed" ? "Closed on restoration telemetry, not on an operator claim."
            : "Closes on telemetry only: after a reported repair the poles must report power and hold it for 30 seconds."}
    </p>}

    {/* Everything below is evidence for the review call, not for the dispatch
        decision, so it is collapsed by default. */}
    <details className="detail-more"><summary>Why the system thinks this</summary>
      {reasons.length > 0 && <ul className="reason-list">{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
      <p>Wiring source: {detail.topology.source === "registry" ? "on record" : "estimated from pole positions"}
        {detail.topology.calibration_bucket ? ` (match quality: ${detail.topology.calibration_bucket})` : ""}.</p>
      {detail.schedule_overlap && <p>Overlaps planned work ({detail.schedule_overlap.status}
        {detail.schedule_overlap.promotion_outcome ? `, ${detail.schedule_overlap.promotion_outcome}` : ""}).</p>}
      {path.length > 1 && <p>Line to walk: {path.map(shortId).join(" → ")}</p>}
    </details>

    <details className="detail-more"><summary>Evidence</summary>
      <p>{Object.entries(detail.evidence?.class_counts ?? {}).map(([kind, count]) => `${count} ${EVIDENCE[kind] ?? kind.replaceAll("_", " ")}`).join(" · ") || "No evidence recorded"}</p>
      {(detail.location_history ?? []).length > 1 && <>
        <p className="label">How the estimate changed</p>
        <ul className="detail-list">{detail.location_history.map((boundary, index) => <li key={`${boundary.kind}-${index}`}>
          {index === 0 ? "First" : "Then"}: {boundary.kind === "span" ? "single span" : boundary.kind} between {shortId(boundary.upstream_pole_id)} and {shortId(boundary.downstream_pole_id)}
        </li>)}</ul>
      </>}
    </details>

    <details className="detail-more"><summary>Ticket history</summary>
      <ul className="detail-list">{(detail.ticket_events ?? []).map((event) => <li key={event.id}>
        {when(event.occurred_at)} — {TICKET[event.type] ?? event.type.replaceAll("_", " ")}
        {event.reason && !TICKET[event.type] ? `: ${event.reason}` : ""}
      </li>)}</ul>
      <p className="detail-reference">Reference <b>{detail.id}</b> · updated {when(detail.updated_at)}</p>
    </details>

    <details className="detail-more"><summary>Explanation</summary>
    {detail.ai_explanation ? <>
      <p>{detail.ai_explanation.status === "fallback" ? "Deterministic fallback" : "Generated explanation"}</p>
      <button aria-pressed={language === "english"} onClick={() => setLanguage("english")}>English</button>
      <button aria-pressed={language === "kannada"} onClick={() => setLanguage("kannada")}>Kannada</button>
      <p>{detail.ai_explanation.text[language]}</p>
      <p>AI explanation cannot change incident facts or ticket status.</p>
    </> : <><p>Explanation unavailable</p><p>AI explanation cannot change incident facts or ticket status.</p></>}
    </details>
  </aside>;
}
