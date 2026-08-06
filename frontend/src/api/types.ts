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
  /** Null for a real incident; set when a simulator run created it. */
  simulation_id?: string | null;
};

export type Page<T> = { items: T[]; page: number; page_size: number; total: number };

export type Readiness = {
  database: string;
  seed: string;
  worker: string;
  ai: string;
  last_processed_at: string | null;
  unprocessed_count: number;
  oldest_backlog_age_seconds: number | null;
};

export type PlannedOperation = {
  id: string;
  incident_id: string | null;
  status: string;
  scope: unknown;
  scheduled_start: string;
  scheduled_end: string;
  observed_start: string | null;
  observed_end: string | null;
  end_grace_minutes: number;
  source_updated_at: string;
  snapshot_stale: boolean;
  promotion_outcome: string | null;
};

export type DeviceHealth = {
  device_id: string;
  serial_number: string;
  pole_id: string;
  is_online: boolean;
  battery_pct: number;
  rssi_dbm: number;
  evidence_class: string;
  device_health: string;
  mismatch_events: number;
  stale_replay_events: number;
};

export type SimulatorScenario = {
  key: string;
  label: string;
  expected_incident_count: number;
  expected_classes: string[];
  boundary_kind: string;
  observability: string;
};

export type SimulatorOutcome = {
  incident_count: number;
  classes: string[];
  observability?: string;
};

export type SimulatorRun = {
  id: string;
  scenario: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  truth: { deenergized?: string[]; event_ids?: string[] };
  expected: SimulatorOutcome;
  actual: SimulatorOutcome & {
    outcome?: string;
    accepted_events?: number;
    detection_elapsed_seconds?: number;
    repair_outcome?: string;
    repair_accepted_events?: number;
    restoration_elapsed_seconds?: number;
    generated_effects?: string[];
    effect_evidence?: Record<string, Record<string, unknown>>;
  };
  incident_ids: string[];
};

export type SimulatorEvent = {
  id: string;
  device_id: string | null;
  pole_id: string | null;
  event_type: string;
  device_time: string;
  received_at: string;
  processing_state: string;
  epoch_decision: string | null;
};
export type FeatureCollection = { type: "FeatureCollection"; features: GeoJSON.Feature[] };

export type IncidentBoundary = { kind: string; upstream_pole_id: string | null; downstream_pole_id: string | null; candidate_spans: unknown[]; geometry: { pole_path?: string[] } };

export type IncidentDetail = IncidentSummary & {
  affected_count_estimated: boolean;
  boundary: IncidentBoundary;
  location_history: IncidentBoundary[];
  topology: { source: "registry" | "inferred"; calibration_bucket: string | null };
  evidence: { class_counts: Record<string, number>; items: { id: string; class: string; event_id: string | null; event_type: string | null; details: Record<string, unknown> }[]; page: number; page_size: number; total: number };
  schedule_overlap: { id: string; status: string; observed_start: string | null; observed_end: string | null; promotion_outcome: string | null } | null;
  ticket_events: { id: string; type: string; from_status: string | null; to_status: string | null; actor: string; reason: string; evidence_ids: string[]; occurred_at: string }[];
  ai_explanation: { status: "generated" | "fallback"; text: { english: string; kannada: string }; fallback_reason: string | null; generated_at: string } | null;
};

export type TicketActionResponse = { code: string; incident: IncidentDetail; ticket_event: IncidentDetail["ticket_events"][number] };

export type OperationsData = {
  readiness: Readiness;
  incidents: Page<IncidentSummary>;
  planned: Page<PlannedOperation>;
  devices: Page<DeviceHealth>;
};
