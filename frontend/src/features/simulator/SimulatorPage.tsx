import { useEffect, useState } from "react";
import { loadRunEvents, loadScenarios, repairRun, resetRuns, startRun } from "../../api/client";
import type { SimulatorEvent, SimulatorRun, SimulatorScenario } from "../../api/types";
import { AppShell } from "../../components/AppShell";
import { StatePanel } from "../../components/StatePanel";
import { EventStream } from "./EventStream";
import { RunComparison } from "./RunComparison";
import { ScenarioControls } from "./ScenarioControls";

const DEFAULT_SEED = 20260803;

export function SimulatorPage() {
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

  const withEvents = async (next: SimulatorRun) => {
    setRun(next);
    setEvents((await loadRunEvents(next.id).catch(() => undefined))?.items ?? []);
  };

  const guard = async (work: () => Promise<void>, failure: string) => {
    setBusy(true);
    setMessage("");
    try {
      await work();
    } catch {
      setMessage(failure);
    } finally {
      setBusy(false);
    }
  };

  const onStart = () => void guard(async () => withEvents(await startRun(scenarioKey, seed)), "The scenario could not be started.");
  const onRepair = () => void guard(async () => run && withEvents(await repairRun(run.id)), "The repair could not be applied.");
  const onReset = () => void guard(async () => {
    await resetRuns();
    setRun(undefined);
    setEvents([]);
    setMessage("Seed state restored; simulator runs were cleared.");
  }, "The simulator could not be reset.");

  const duplicates = Number(run?.actual.effect_evidence?.duplicate?.duplicate_attempts ?? 0);
  return <AppShell>
    <header className="demo-banner"><h1>Simulator</h1><p>Demo view — simulated faults and repairs are not operator workflow.</p></header>
    <ScenarioControls
      scenarios={scenarios} scenarioKey={scenarioKey} seed={seed} busy={busy}
      canRepair={Boolean(run) && !run?.actual.repair_outcome}
      onScenarioChange={setScenarioKey} onSeedChange={setSeed}
      onStart={onStart} onRepair={onRepair} onReset={onReset}
    />
    {message && <StatePanel title="Simulator">{message}</StatePanel>}
    {run
      ? <><RunComparison run={run} /><EventStream events={events} duplicateAttempts={duplicates} /></>
      : <StatePanel title="No simulator run">Choose a scenario and seed, then start a deterministic run.</StatePanel>}
  </AppShell>;
}
