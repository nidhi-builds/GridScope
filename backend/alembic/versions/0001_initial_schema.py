"""Initial GridScope persistence schema.

Revision ID: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DDL = """
CREATE TABLE substations (
    id UUID PRIMARY KEY, code VARCHAR(32) NOT NULL UNIQUE,
    latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE feeders (
    id UUID PRIMARY KEY, substation_id UUID NOT NULL REFERENCES substations(id),
    code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE transformers (
    id UUID PRIMARY KEY, feeder_id UUID NOT NULL REFERENCES feeders(id), code VARCHAR(32) NOT NULL UNIQUE,
    latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE poles (
    id UUID PRIMARY KEY, transformer_id UUID NOT NULL REFERENCES transformers(id),
    code VARCHAR(32) NOT NULL UNIQUE, latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL,
    pin_code VARCHAR(12), parent_pole_id UUID REFERENCES poles(id), branch_index INTEGER NOT NULL, seq_on_line INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE topology_edges (
    id UUID PRIMARY KEY, transformer_id UUID NOT NULL REFERENCES transformers(id),
    parent_pole_id UUID NOT NULL REFERENCES poles(id), child_pole_id UUID NOT NULL REFERENCES poles(id),
    source VARCHAR(32) NOT NULL, version INTEGER NOT NULL DEFAULT 1, distance_m DOUBLE PRECISION NOT NULL,
    ambiguity_score DOUBLE PRECISION NOT NULL DEFAULT 0, calibration_bucket VARCHAR(32),
    is_visible BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_topology_edges_transformer_parent ON topology_edges(transformer_id, parent_pole_id);
CREATE TABLE devices (
    id UUID PRIMARY KEY, serial_number VARCHAR(64) NOT NULL UNIQUE, firmware VARCHAR(32) NOT NULL,
    battery_pct DOUBLE PRECISION NOT NULL, rssi_dbm DOUBLE PRECISION NOT NULL, is_online BOOLEAN NOT NULL,
    heartbeat_interval_seconds INTEGER NOT NULL, next_heartbeat_offset_seconds INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE device_assignments (
    id UUID PRIMARY KEY, device_id UUID NOT NULL REFERENCES devices(id), pole_id UUID NOT NULL REFERENCES poles(id),
    effective_from TIMESTAMPTZ NOT NULL, effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_device_assignments_effective ON device_assignments(device_id, effective_from, effective_to);
CREATE TABLE telemetry_events (
    id UUID PRIMARY KEY, device_id UUID REFERENCES devices(id), pole_id UUID REFERENCES poles(id),
    fingerprint VARCHAR(128) NOT NULL, event_type VARCHAR(32) NOT NULL, payload JSONB NOT NULL,
    device_time TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL, processed_at TIMESTAMPTZ,
    processing_state VARCHAR(24) NOT NULL DEFAULT 'pending', failed_reason TEXT, epoch_decision VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_telemetry_events_fingerprint ON telemetry_events(fingerprint);
CREATE INDEX ix_telemetry_events_processing ON telemetry_events(processed_at, received_at);
CREATE TABLE device_stream_state (
    id UUID PRIMARY KEY, device_id UUID NOT NULL UNIQUE REFERENCES devices(id), current_epoch INTEGER NOT NULL,
    last_sequence INTEGER NOT NULL, last_device_time TIMESTAMPTZ NOT NULL, last_received_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE pole_evidence_state (
    id UUID PRIMARY KEY, pole_id UUID NOT NULL UNIQUE REFERENCES poles(id),
    evidence_class VARCHAR(32) NOT NULL DEFAULT 'unknown_silent', source_event_id UUID REFERENCES telemetry_events(id),
    fresh_until TIMESTAMPTZ, device_health VARCHAR(32) NOT NULL, evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_pole_evidence_state_class CHECK (
        evidence_class IN ('confirmed_live','confirmed_dark','unknown_silent','uninstrumented','device_suspect')
    )
);
CREATE TABLE detection_candidates (
    id UUID PRIMARY KEY, transformer_id UUID NOT NULL REFERENCES transformers(id), scope_key VARCHAR(128) NOT NULL,
    tier INTEGER NOT NULL DEFAULT 1, first_received_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
    evidence_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb, promotion_outcome VARCHAR(32),
    status VARCHAR(24) NOT NULL DEFAULT 'investigating',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE simulator_runs (
    id UUID PRIMARY KEY, seed INTEGER NOT NULL, scenario VARCHAR(48) NOT NULL, status VARCHAR(24) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ, truth JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_results JSONB NOT NULL DEFAULT '{}'::jsonb, actual_results JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE scheduled_outages (
    id UUID PRIMARY KEY, external_id VARCHAR(64) NOT NULL UNIQUE, scope JSONB NOT NULL,
    scheduled_start TIMESTAMPTZ NOT NULL, scheduled_end TIMESTAMPTZ NOT NULL,
    start_grace_minutes INTEGER NOT NULL DEFAULT 20, end_grace_minutes INTEGER NOT NULL DEFAULT 40,
    source_updated_at TIMESTAMPTZ NOT NULL, snapshot_stale BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE incidents (
    id UUID PRIMARY KEY, correlation_key VARCHAR(160) NOT NULL, fault_class VARCHAR(32) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'detected', location_class VARCHAR(24) NOT NULL,
    feeder_id UUID REFERENCES feeders(id), transformer_id UUID REFERENCES transformers(id), pole_id UUID REFERENCES poles(id),
    pin_code VARCHAR(12) NOT NULL, pin_source VARCHAR(32) NOT NULL, affected_count INTEGER NOT NULL,
    confidence VARCHAR(16) NOT NULL, confidence_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    navigation_latitude DOUBLE PRECISION NOT NULL, navigation_longitude DOUBLE PRECISION NOT NULL,
    simulation_id UUID REFERENCES simulator_runs(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_incidents_status CHECK (
        status IN ('detected','acknowledged','crew_assigned','resolved','verified','closed')
    )
);
CREATE INDEX ix_incidents_status_updated ON incidents(status, updated_at);
CREATE UNIQUE INDEX uq_incidents_active_correlation ON incidents(correlation_key) WHERE status <> 'closed';
CREATE TABLE planned_operations (
    id UUID PRIMARY KEY, scheduled_outage_id UUID NOT NULL REFERENCES scheduled_outages(id),
    incident_id UUID REFERENCES incidents(id), status VARCHAR(32) NOT NULL,
    observed_start TIMESTAMPTZ, observed_end TIMESTAMPTZ,
    matched_evidence JSONB NOT NULL DEFAULT '[]'::jsonb, promotion_outcome VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE incident_boundaries (
    id UUID PRIMARY KEY, incident_id UUID NOT NULL REFERENCES incidents(id), boundary_type VARCHAR(24) NOT NULL,
    upstream_pole_id UUID REFERENCES poles(id), downstream_pole_id UUID REFERENCES poles(id),
    candidate_spans JSONB NOT NULL DEFAULT '[]'::jsonb, geometry JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE incident_evidence (
    id UUID PRIMARY KEY, incident_id UUID NOT NULL REFERENCES incidents(id),
    telemetry_event_id UUID NOT NULL REFERENCES telemetry_events(id), evidence_class VARCHAR(32) NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE ticket_events (
    id UUID PRIMARY KEY, incident_id UUID NOT NULL REFERENCES incidents(id), event_type VARCHAR(32) NOT NULL,
    from_status VARCHAR(24), to_status VARCHAR(24), actor VARCHAR(64) NOT NULL, reason TEXT NOT NULL,
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb, occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE simulated_faults (
    id UUID PRIMARY KEY, simulator_run_id UUID NOT NULL REFERENCES simulator_runs(id), fault_class VARCHAR(32) NOT NULL,
    target JSONB NOT NULL, occurred_at TIMESTAMPTZ NOT NULL, repaired_at TIMESTAMPTZ, truth JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE ai_explanations (
    id UUID PRIMARY KEY, incident_id UUID NOT NULL REFERENCES incidents(id), prompt_version VARCHAR(32) NOT NULL,
    model VARCHAR(64), validated_text JSONB NOT NULL, usage JSONB NOT NULL DEFAULT '{}'::jsonb,
    latency_ms INTEGER, fallback_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def upgrade() -> None:
    for statement in _DDL.split(";\n"):
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "ai_explanations",
        "simulated_faults",
        "ticket_events",
        "incident_evidence",
        "incident_boundaries",
        "planned_operations",
        "incidents",
        "scheduled_outages",
        "simulator_runs",
        "detection_candidates",
        "pole_evidence_state",
        "device_stream_state",
        "telemetry_events",
        "device_assignments",
        "devices",
        "topology_edges",
        "poles",
        "transformers",
        "feeders",
        "substations",
    ):
        op.drop_table(table)
