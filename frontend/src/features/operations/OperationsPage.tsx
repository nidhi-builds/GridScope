import { useEffect, useState } from "react";
import { ApiError, loadIncidentGeometry } from "../../api/client";
import type { FeatureCollection } from "../../api/types";
import { AppShell } from "../../components/AppShell";
import { StatePanel } from "../../components/StatePanel";
import { StatusBar } from "../../components/StatusBar";
import { IncidentFilters } from "./IncidentFilters";
import { IncidentQueue } from "./IncidentQueue";
import { NetworkMap } from "./NetworkMap";
import { useOperations } from "./OperationsProvider";
import { IncidentDetail } from "../incidents/IncidentDetail";

export function OperationsPage() {
  const { data, updatedAt, error, loading, refresh, selectedIncidentId, selected, select, filters, setFilters, resetQueue, canResetQueue, incidents, overview, network } = useOperations();
  const [geometry, setGeometry] = useState<FeatureCollection>();

  useEffect(() => {
    setGeometry(undefined);
    if (!selectedIncidentId) return;
    const controller = new AbortController();
    void loadIncidentGeometry(selectedIncidentId, controller.signal).then((nextGeometry) => {
      if (!controller.signal.aborted) setGeometry(nextGeometry);
    }).catch((nextError: Error) => {
      if (!controller.signal.aborted && nextError.name !== "AbortError") setGeometry(undefined);
    });
    return () => controller.abort();
  }, [selectedIncidentId]);

  if (loading && !data) return <AppShell><StatePanel title="Loading operations">Connecting to GridScope…</StatePanel></AppShell>;
  if (!data) return <AppShell><StatePanel title={error instanceof ApiError && error.status === 503 ? "Starting GridScope" : "API unavailable"}>The last workspace data is unavailable. Retry when the service is ready.</StatePanel></AppShell>;
  const backlog = (data.readiness?.unprocessed_count ?? 0) > 0;
  return <AppShell><StatusBar data={data} updatedAt={updatedAt} stale={Boolean(error)} />
    {backlog && <StatePanel title="Inbox backlog">{data.readiness?.unprocessed_count} telemetry events await processing.</StatePanel>}
    {error && <StatePanel title="Live updates paused">Showing the last valid data while the API reconnects.</StatePanel>}
    <div className="operations-layout"><aside className="queue-panel"><IncidentFilters incidents={data.incidents?.items ?? []} filters={filters} onChange={setFilters} onReset={resetQueue} canReset={canResetQueue} />{incidents.length ? <IncidentQueue incidents={incidents} selectedIncidentId={selectedIncidentId} onSelect={select} /> : <StatePanel title="No matching incidents">Adjust filters or wait for the next poll.</StatePanel>}<IncidentDetail incidentId={selectedIncidentId} onChanged={refresh} version={selected?.updated_at} /></aside><NetworkMap incident={selected} geometry={geometry} overview={overview} network={network} /></div>
  </AppShell>;
}
