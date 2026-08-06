import type { DeviceHealth, FeatureCollection, IncidentDetail, IncidentSummary, OperationsData, Page, PlannedOperation, Readiness, SimulatorEvent, SimulatorRun, SimulatorScenario, TicketActionResponse } from "./types";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const baseUrl = import.meta.env.VITE_API_BASE ?? "";

export async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${baseUrl}/api/v1${path}`, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string | { code?: string } } | null;
    const detail = typeof body?.detail === "string" ? body.detail : body?.detail?.code;
    throw new ApiError(response.status, detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function loadOperations(signal?: AbortSignal): Promise<OperationsData> {
  return Promise.all([
    request<Readiness>("/ready", signal),
    request<Page<IncidentSummary>>("/incidents?page=1&page_size=100", signal),
    request<Page<PlannedOperation>>("/planned-operations?page=1&page_size=100", signal),
    request<Page<DeviceHealth>>("/device-health?page=1&page_size=1", signal),
  ]).then(([readiness, incidents, planned, devices]) => ({ readiness, incidents, planned, devices }));
}

export function loadIncidentGeometry(incidentId: string, signal?: AbortSignal): Promise<FeatureCollection> {
  return request<FeatureCollection>(`/network/incidents/${encodeURIComponent(incidentId)}`, signal);
}

/** The whole live network: poles with their current state, plus recorded wiring. */
export function loadNetwork(signal?: AbortSignal): Promise<FeatureCollection> {
  return request<FeatureCollection>("/network/poles", signal);
}

export function loadIncident(incidentId: string, signal?: AbortSignal): Promise<IncidentDetail> {
  return request<IncidentDetail>(`/incidents/${encodeURIComponent(incidentId)}`, signal);
}

export function loadReadiness(signal?: AbortSignal): Promise<Readiness> {
  return request<Readiness>("/ready", signal);
}

export function loadPlannedOperations(signal?: AbortSignal): Promise<Page<PlannedOperation>> {
  return request<Page<PlannedOperation>>("/planned-operations?page=1&page_size=100", signal);
}

export function loadDeviceHealth(signal?: AbortSignal): Promise<Page<DeviceHealth>> {
  return request<Page<DeviceHealth>>("/device-health?page=1&page_size=100", signal);
}

export function loadScenarios(signal?: AbortSignal): Promise<SimulatorScenario[]> {
  return request<SimulatorScenario[]>("/simulator/scenarios", signal);
}

export function loadRun(runId: string, signal?: AbortSignal): Promise<SimulatorRun> {
  return request<SimulatorRun>(`/simulator/runs/${encodeURIComponent(runId)}`, signal);
}

export function loadRunEvents(runId: string, signal?: AbortSignal): Promise<Page<SimulatorEvent>> {
  // Restoration events are appended last, so a short page hides exactly the
  // events that prove the ticket closed on telemetry. 500 is the endpoint's max.
  return request<Page<SimulatorEvent>>(`/simulator/runs/${encodeURIComponent(runId)}/events?page=1&page_size=500`, signal);
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${baseUrl}/api/v1${path}`, {
    method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(response.status, failure?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function startRun(scenarioKey: string, seed: number): Promise<SimulatorRun> {
  return post<SimulatorRun>("/simulator/runs", { scenario_key: scenarioKey, seed });
}

export function repairRun(runId: string): Promise<SimulatorRun> {
  return post<SimulatorRun>(`/simulator/runs/${encodeURIComponent(runId)}/repair`);
}

export function resetRuns(): Promise<{ status: string }> {
  return post<{ status: string }>("/simulator/reset");
}

export async function ticketAction(incidentId: string, action: "acknowledge" | "assign" | "report-resolved"): Promise<TicketActionResponse> {
  const payload = action === "assign" ? { actor: "operator", crew_label: "crew-1" } : { actor: "operator" };
  const response = await fetch(`${baseUrl}/api/v1/incidents/${encodeURIComponent(incidentId)}/${action}`, { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const body = await response.json().catch(() => null) as TicketActionResponse | { detail?: TicketActionResponse } | null;
  if (!response.ok) throw ((body as { detail?: TicketActionResponse } | null)?.detail ?? body ?? new ApiError(response.status, `Request failed (${response.status})`));
  return body as TicketActionResponse;
}
