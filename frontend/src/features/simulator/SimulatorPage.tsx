import { useEffect, useState } from "react";
import { loadRun, loadRunEvents, loadScenarios, repairRun, resetRuns, startRun } from "../../api/client";
import type { SimulatorEvent, SimulatorRun, SimulatorScenario } from "../../api/types";
import { AppShell } from "../../components/AppShell";
import { StatePanel } from "../../components/StatePanel";
import { IncidentDetail } from "../incidents/IncidentDetail";
import { useOperations } from "../operations/OperationsProvider";
import { EventStream } from "./EventStream";
import { RunComparison } from "./RunComparison";
import { ScenarioControls } from "./ScenarioControls";

const DEFAULT_SEED = 20260803;
// Routes no longer reload, but a hard refresh still has to find the last run.
const LAST_RUN = "gridscope.simulator.last-run";

export function SimulatorPage() {
  const { selectedIncidentId, selected, select, refresh } = useOperations();
  const [scenarios, setScenarios] = useState<SimulatorScenario[]>([]);
  const [scenarioKey, setScenarioKey] = useState("");
  const [seed, setSeed] = useState(DEFAULT_SEED);
  const [run, setRun] = useState<SimulatorRun>();
  const [events, setEvents] = useState<SimulatorEvent[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void loadScenarios(controller.signal).then((items) => {
      if (controller.signal.aborted) return;
      setScenarios(items);
      setScenarioKey((current) => current || items[0]?.key || "");
    }).catch(() => !controller.signal.aborted && setMessage("Simulator scenarios unavailable."));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const previous = sessionStorage.getItem(LAST_RUN);
    if (!previous) return;
    const controller = new AbortController();
    void loadRun(previous, controller.signal)
      .then(async (restored) => { if (!controller.signal.aborted) await withEvents(restored); })
      .catch(() => sessionStorage.removeItem(LAST_RUN));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const withEvents = async (next: SimulatorRun) => {
    setRun(next);
    sessionStorage.setItem(LAST_RUN, next.id);
    setEvents((await loadRunEvents(next.id).catch(() => undefined))?.items ?? []);
  };

  /**
   * Every control is disabled while an action is in flight. That is only safe if
   * `busy` is guaranteed to clear — a request that never settles (a sleeping
   * free-tier instance, a dropped connection) otherwise locks the entire view
   * with no way out and no explanation.
   */
  const guard = async (work: () => Promise<void>, failure: string) => {
    setBusy(true);
    setMessage("");
    const stuck = window.setTimeout(() => {
      setBusy(false);
      setMessage("That is taking longer than expected — the service may be waking up. Nothing was lost; try again.");
    }, 30_000);
    try {
      await work();
    } catch {
      setMessage(failure);
    } finally {
      window.clearTimeout(stuck);
      setBusy(false);
    }
  };

  const onStart = () => void guard(async () => withEvents(await startRun(scenarioKey, seed)), "The scenario could not be started.");
  const onRepair = () => void guard(async () => run && withEvents(await repairRun(run.id)), "The repair could not be applied.");
  const onReset = () => void guard(async () => {
    await resetRuns();
    sessionStorage.removeItem(LAST_RUN);
    setRun(undefined);
    setEvents([]);
    setMessage("Seed state restored; simulator runs were cleared.");
  }, "The simulator could not be reset.");

  const duplicates = Number(run?.actual?.effect_evidence?.duplicate?.duplicate_attempts ?? 0);
  const canRepair = Boolean(run) && !run?.actual?.repair_outcome;
  return <AppShell>
    <header className="demo-banner"><h1>Simulator</h1><p>Demo view — simulated faults and repairs are not operator workflow.</p></header>
    <ScenarioControls
      scenarios={scenarios} scenarioKey={scenarioKey} seed={seed} busy={busy}
      canRepair={canRepair}
      onScenarioChange={setScenarioKey} onSeedChange={setSeed}
      onStart={onStart} onRepair={onRepair} onReset={onReset}
    />
    {message && <StatePanel title="Simulator">{message}</StatePanel>}
    {/* The ticket you selected in Operations travels with you, so a fault can be
        repaired here and acknowledged there without losing your place. */}
    {selectedIncidentId && <section className="simulator-ticket" aria-label="Selected incident ticket">
      <IncidentDetail incidentId={selectedIncidentId} onChanged={refresh} version={selected?.updated_at} />
      <div className="ticket-actions">
        {/* Repairing belongs next to the ticket you are looking at, not buried in
            the scenario bar at the top of the page. It is still a demo action:
            it restores power in the simulated world, which is what then produces
            the telemetry that closes the ticket. */}
        {canRepair
          ? <button className="ticket-action" onClick={onRepair} disabled={busy}>Repair this fault (demo)</button>
          : <span className="control-hint">{run?.actual?.repair_outcome
            ? "This fault has already been repaired. Press Reset to run it again."
            : "Start a scenario to create a repairable fault."}</span>}
        {/* "Clear ticket" read like a ticket action — dangerously so on a resolved
            ticket, where closing is telemetry's job and never an operator's. This
            only hides the panel. */}
        <button className="panel-dismiss" onClick={() => select(undefined)}>Hide this ticket</button>
      </div>
    </section>}
    {run
      ? <><RunComparison run={run} onSelectIncident={select} selectedIncidentId={selectedIncidentId} /><EventStream events={events} duplicateAttempts={duplicates} repaired={Boolean(run.actual?.repair_outcome)} /></>
      : <StatePanel title="No simulator run">Choose a scenario and seed, then start a deterministic run.</StatePanel>}
  </AppShell>;
}
