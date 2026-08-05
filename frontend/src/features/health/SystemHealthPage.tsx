import { useCallback, useEffect, useState } from "react";
import { loadReadiness } from "../../api/client";
import { useVisiblePolling } from "../../api/polling";
import type { Readiness } from "../../api/types";
import { AppShell } from "../../components/AppShell";
import { StatePanel } from "../../components/StatePanel";

const TILE_PROBE = "https://a.tile.openstreetmap.org/0/0/0.png";

export function SystemHealthPage({ readiness, error }: { readiness?: Readiness; error?: Error }) {
  const load = useCallback((signal: AbortSignal) => readiness ? Promise.resolve(readiness) : loadReadiness(signal), [readiness]);
  const polled = useVisiblePolling(load, 15_000);
  const data = readiness ?? polled.data;
  const failure = error ?? (data ? undefined : polled.error);
  const [tiles, setTiles] = useState("checking");

  useEffect(() => {
    let active = true;
    void fetch(TILE_PROBE, { method: "GET", mode: "no-cors" })
      .then(() => active && setTiles("reachable"))
      .catch(() => active && setTiles("unreachable"));
    return () => { active = false; };
  }, []);

  return <AppShell>
    <header className="secondary-header"><h1>System health</h1><p>Platform readiness for the operator console.</p></header>
    <ul className="system-health">
      <li>API: {failure ? "unreachable" : "reachable"}</li>
      <li>Database: {data?.database ?? "unknown"}</li>
      <li>Seed: {data?.seed ?? "unknown"}</li>
      <li>Worker: {data?.worker ?? "unknown"}</li>
      <li>Backlog: {data?.unprocessed_count ?? 0} events, oldest {data?.oldest_backlog_age_seconds ?? 0}s</li>
      <li>Last processed: {data?.last_processed_at ?? "never"}</li>
      <li>Map tiles: {tiles}</li>
      <li>AI explanations: {data?.ai ?? "unknown"}</li>
    </ul>
    {failure && <StatePanel title="API unavailable">Readiness could not be read; the values above are the last known state.</StatePanel>}
  </AppShell>;
}
