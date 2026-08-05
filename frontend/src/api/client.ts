import type { DeviceHealth, FeatureCollection, IncidentDetail, IncidentSummary, OperationsData, Page, PlannedOperation, Readiness, TicketActionResponse } from "./types";

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

export function loadIncident(incidentId: string, signal?: AbortSignal): Promise<IncidentDetail> {
  return request<IncidentDetail>(`/incidents/${encodeURIComponent(incidentId)}`, signal);
}

export async function ticketAction(incidentId: string, action: "acknowledge" | "assign" | "report-resolved"): Promise<TicketActionResponse> {
  const payload = action === "assign" ? { actor: "operator", crew_label: "crew-1" } : { actor: "operator" };
  const response = await fetch(`${baseUrl}/api/v1/incidents/${encodeURIComponent(incidentId)}/${action}`, { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const body = await response.json().catch(() => null) as TicketActionResponse | { detail?: TicketActionResponse } | null;
  if (!response.ok) throw ((body as { detail?: TicketActionResponse } | null)?.detail ?? body ?? new ApiError(response.status, `Request failed (${response.status})`));
  return body as TicketActionResponse;
}
