import type { OperationsData } from "../api/types";

export function StatusBar({ data, updatedAt, stale }: { data: OperationsData; updatedAt?: Date; stale: boolean }) {
  const investigating = data.incidents.items.filter(({ status }) => status === "acknowledged" || status === "crew_assigned").length;
  return <header className="status-bar">
    <strong>GridScope</strong>
    <span>Ingest: {data.readiness.worker === "ready" ? "healthy" : "unavailable"}</span>
    <span>Active: {data.incidents.total}</span><span>Investigating: {investigating}</span>
    <span>Planned: {data.planned.total}</span><span>Inbox: {data.readiness.oldest_backlog_age_seconds ?? 0}s</span>
    <span className={stale ? "status-stale" : ""}>{stale ? `Showing data from ${updatedAt?.toLocaleTimeString() ?? "earlier"}` : "Live"}</span>
  </header>;
}
