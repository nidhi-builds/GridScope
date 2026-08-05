export type ConfidenceLevel = "high" | "medium" | "low";

export type IncidentSummary = {
  id: string;
  fault_class: string;
  status: string;
  location_class: string;
  affected_count: number;
  confidence: { level: ConfidenceLevel; reasons: string[] };
  navigation: { latitude: number; longitude: number };
  pin: { value: string | null; source: string | null };
  feeder_id: string | null;
  transformer_id: string | null;
  pole_id: string | null;
  updated_at: string;
};

export type Page<T> = { items: T[]; page: number; page_size: number; total: number };

export type Readiness = {
  database: string;
  seed: string;
  worker: string;
  last_processed_at: string | null;
  unprocessed_count: number;
  oldest_backlog_age_seconds: number | null;
};

export type PlannedOperation = { id: string; incident_id: string | null; status: string; scope: string };
export type DeviceHealth = { device_id: string; is_online: boolean; device_health: string };
export type FeatureCollection = { type: "FeatureCollection"; features: GeoJSON.Feature[] };

export type OperationsData = {
  readiness: Readiness;
  incidents: Page<IncidentSummary>;
  planned: Page<PlannedOperation>;
  devices: Page<DeviceHealth>;
};
