import type { SimulatorScenario } from "../../api/types";

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
    <button onClick={onRepair} disabled={busy || !canRepair}>Repair fault</button>
    <button onClick={onReset} disabled={busy}>Reset</button>
  </section>;
}
