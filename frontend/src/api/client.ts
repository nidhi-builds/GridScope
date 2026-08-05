import type { DeviceHealth, FeatureCollection, IncidentSummary, OperationsData, Page, PlannedOperation, Readiness } from "./types";

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
