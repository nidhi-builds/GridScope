import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { APIRequestContext, Page } from "@playwright/test";

export type SimulatorRun = {
  id: string;
  scenario: string;
  truth: { deenergized?: string[]; event_ids?: string[] };
  expected: { incident_count: number; classes: string[]; observability?: string };
  actual: Record<string, unknown> & { outcome?: string; repair_outcome?: string };
  incident_ids: string[];
};

const RESULTS = resolve(process.cwd(), "performance/results");

/** Restore the deterministic seed so one spec cannot inherit another's incidents. */
export async function resetSimulator(request: APIRequestContext): Promise<void> {
  const response = await request.post("/api/v1/simulator/reset");
  if (!response.ok()) throw new Error(`simulator reset failed: ${response.status()}`);
}

export async function startScenario(request: APIRequestContext, scenarioKey: string, seed = 20260803): Promise<SimulatorRun> {
  const response = await request.post("/api/v1/simulator/runs", { data: { scenario_key: scenarioKey, seed } });
  if (!response.ok()) throw new Error(`scenario ${scenarioKey} failed: ${response.status()} ${await response.text()}`);
  return response.json() as Promise<SimulatorRun>;
}

export async function repairRun(request: APIRequestContext, runId: string): Promise<SimulatorRun> {
  const response = await request.post(`/api/v1/simulator/runs/${runId}/repair`);
  if (!response.ok()) throw new Error(`repair failed: ${response.status()}`);
  return response.json() as Promise<SimulatorRun>;
}

export async function incidentDetail(request: APIRequestContext, incidentId: string): Promise<Record<string, any>> {
  const response = await request.get(`/api/v1/incidents/${incidentId}`);
  if (!response.ok()) throw new Error(`incident ${incidentId} failed: ${response.status()}`);
  return response.json();
}

export async function countIncidents(request: APIRequestContext): Promise<number> {
  const response = await request.get("/api/v1/incidents?page=1&page_size=100");
  return ((await response.json()) as { total: number }).total;
}

/** Open the queue row for one incident and return its detail panel. */
export async function selectIncident(page: Page, incidentId: string) {
  await page.goto("/operations");
  const row = page.getByRole("button", { name: incidentId, exact: true });
  await row.waitFor({ state: "visible" });
  await row.click();
  return page.getByRole("complementary", { name: "Incident detail" });
}

/**
 * Raw measurements are written verbatim. A missed target is reported, never
 * rounded away or re-run until it passes.
 */
export function recordMetrics(file: string, payload: Record<string, unknown>): void {
  const target = resolve(RESULTS, file);
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, `${JSON.stringify({ recorded_at: new Date().toISOString(), ...payload }, null, 2)}\n`);
}

export function percentile(values: number[], fraction: number): number {
  if (!values.length) return Number.NaN;
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(sorted.length - 1, Math.ceil(fraction * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}
