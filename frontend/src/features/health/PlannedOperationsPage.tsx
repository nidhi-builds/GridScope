import { useCallback } from "react";
import { loadPlannedOperations } from "../../api/client";
import { useVisiblePolling } from "../../api/polling";
import type { Page, PlannedOperation } from "../../api/types";
import { AppShell } from "../../components/AppShell";
import { StatePanel } from "../../components/StatePanel";

export function PlannedOperationsPage({ page }: { page?: Page<PlannedOperation> }) {
  const load = useCallback((signal: AbortSignal) => page ? Promise.resolve(page) : loadPlannedOperations(signal), [page]);
  const { data: polled, loading } = useVisiblePolling(load, 15_000);
  const data = page ?? polled;

  if (!data) return <AppShell><StatePanel title={loading ? "Loading planned operations" : "Planned operations unavailable"}>Planned work is not a fault ticket; retry when the API is ready.</StatePanel></AppShell>;
  return <AppShell>
    <header className="secondary-header"><h1>Planned operations</h1><p>Planned work is not a fault ticket and never enters the incident queue.</p></header>
    {data.items.length
      ? <ul className="planned-list">{data.items.map((operation) => <li key={operation.id}>
        <h2>{operation.status}</h2>
        <p>Scope: {JSON.stringify(operation.scope)}</p>
        <p>Published {operation.scheduled_start} to {operation.scheduled_end}</p>
        <p>Observed {operation.observed_start ?? "not started"} to {operation.observed_end ?? "running"}</p>
        <p>{operation.end_grace_minutes} minute end grace after the published end</p>
        <p>Schedule source updated {operation.source_updated_at}{operation.snapshot_stale ? " — Schedule snapshot is stale" : ""}</p>
        <p>Promotion: {operation.promotion_outcome ?? "not promoted"}</p>
        {operation.incident_id && <p>Linked incident: {operation.incident_id}</p>}
      </li>)}</ul>
      : <StatePanel title="No planned operations">Nothing is scheduled in the current window.</StatePanel>}
  </AppShell>;
}
