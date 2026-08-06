import type { SimulatorScenario } from "../../api/types";

export function repairBlockedReason(busy: boolean, canRepair: boolean): string {
  if (busy) return "Working…";
  if (canRepair) return "";
  return "Start a scenario first. A run that has already been repaired cannot be repaired again — press Reset to start over.";
}

export function ScenarioControls({ scenarios, scenarioKey, seed, busy, canRepair, onScenarioChange, onSeedChange, onStart, onRepair, onReset }: {
  scenarios: SimulatorScenario[];
  scenarioKey: string;
  seed: number;
  busy: boolean;
  canRepair: boolean;
  onScenarioChange: (key: string) => void;
  onSeedChange: (seed: number) => void;
  onStart: () => void;
  onRepair: () => void;
  onReset: () => void;
}) {
  return <section className="scenario-controls" aria-label="Scenario controls">
    <label htmlFor="scenario">Scenario</label>
    <select id="scenario" value={scenarioKey} onChange={(event) => onScenarioChange(event.target.value)}>
      {scenarios.map((scenario) => <option key={scenario.key} value={scenario.key}>{scenario.label}</option>)}
    </select>
    <label htmlFor="seed">Seed</label>
    <input id="seed" type="number" value={seed} onChange={(event) => onSeedChange(Number(event.target.value))} />
    <button onClick={onStart} disabled={busy || !scenarioKey}>Start scenario</button>
    <button onClick={onRepair} disabled={busy || !canRepair} title={repairBlockedReason(busy, canRepair)}>Repair fault</button>
    <button onClick={onReset} disabled={busy}>Reset</button>
    {/* A disabled button with no reason is the most frustrating control in any
        console. Say why it cannot be pressed. */}
    {repairBlockedReason(busy, canRepair) && <p className="control-hint">{repairBlockedReason(busy, canRepair)}</p>}
  </section>;
}
