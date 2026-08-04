import re

from sqlalchemy import DateTime, Uuid, func, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.db import engine
from app.db.models.assets import Device, Feeder, Pole, Substation, Transformer
from app.domain.types import SeedSummary
from app.seed import seed_if_empty


def test_migration_creates_complete_prd_schema_and_operational_indexes():
    # Break caught: a required persistence table, constraint, or hot-path index is omitted.
    inspector = inspect(engine)
    required_tables = {
        "substations",
        "feeders",
        "transformers",
        "poles",
        "topology_edges",
        "devices",
        "device_assignments",
        "telemetry_events",
        "device_stream_state",
        "pole_evidence_state",
        "detection_candidates",
        "scheduled_outages",
        "planned_operations",
        "incidents",
        "incident_boundaries",
        "incident_evidence",
        "ticket_events",
        "simulator_runs",
        "simulated_faults",
        "ai_explanations",
    }
    assert required_tables.issubset(inspector.get_table_names())

    for table_name in required_tables:
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert isinstance(columns["id"]["type"], Uuid), table_name
        assert inspector.get_pk_constraint(table_name)["constrained_columns"] == ["id"], table_name
        assert columns["id"]["nullable"] is False, table_name
        for timestamp_name in ("created_at", "updated_at"):
            assert isinstance(columns[timestamp_name]["type"], DateTime), table_name
            assert columns[timestamp_name]["type"].timezone is True, table_name
            assert columns[timestamp_name]["nullable"] is False, table_name

    jsonb_columns = {
        "telemetry_events": {"payload"},
        "pole_evidence_state": {"evidence"},
        "detection_candidates": {"evidence_event_ids"},
        "scheduled_outages": {"scope"},
        "planned_operations": {"matched_evidence"},
        "incidents": {"confidence_reasons"},
        "incident_boundaries": {"candidate_spans", "geometry"},
        "incident_evidence": {"evidence"},
        "ticket_events": {"evidence_ids"},
        "simulator_runs": {"truth", "expected_results", "actual_results"},
        "simulated_faults": {"target", "truth"},
        "ai_explanations": {"validated_text", "usage"},
    }
    for table_name, names in jsonb_columns.items():
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert all(isinstance(columns[name]["type"], JSONB) for name in names), table_name
        assert all(columns[name]["nullable"] is False for name in names), table_name

    expected_foreign_keys = {
        ("feeders", "substation_id", "substations", "id"),
        ("transformers", "feeder_id", "feeders", "id"),
        ("poles", "transformer_id", "transformers", "id"),
        ("poles", "parent_pole_id", "poles", "id"),
        ("topology_edges", "transformer_id", "transformers", "id"),
        ("topology_edges", "parent_pole_id", "poles", "id"),
        ("topology_edges", "child_pole_id", "poles", "id"),
        ("device_assignments", "device_id", "devices", "id"),
        ("device_assignments", "pole_id", "poles", "id"),
        ("telemetry_events", "device_id", "devices", "id"),
        ("telemetry_events", "pole_id", "poles", "id"),
        ("device_stream_state", "device_id", "devices", "id"),
        ("pole_evidence_state", "pole_id", "poles", "id"),
        ("pole_evidence_state", "source_event_id", "telemetry_events", "id"),
        ("detection_candidates", "transformer_id", "transformers", "id"),
        ("incidents", "feeder_id", "feeders", "id"),
        ("incidents", "transformer_id", "transformers", "id"),
        ("incidents", "pole_id", "poles", "id"),
        ("incidents", "simulation_id", "simulator_runs", "id"),
        ("planned_operations", "scheduled_outage_id", "scheduled_outages", "id"),
        ("planned_operations", "incident_id", "incidents", "id"),
        ("incident_boundaries", "incident_id", "incidents", "id"),
        ("incident_boundaries", "upstream_pole_id", "poles", "id"),
        ("incident_boundaries", "downstream_pole_id", "poles", "id"),
        ("incident_evidence", "incident_id", "incidents", "id"),
        ("incident_evidence", "telemetry_event_id", "telemetry_events", "id"),
        ("ticket_events", "incident_id", "incidents", "id"),
        ("simulated_faults", "simulator_run_id", "simulator_runs", "id"),
        ("ai_explanations", "incident_id", "incidents", "id"),
    }
    actual_foreign_keys = set()
    for table_name in required_tables:
        for foreign_key in inspector.get_foreign_keys(table_name):
            actual_foreign_keys.update(
                (table_name, local, foreign_key["referred_table"], remote)
                for local, remote in zip(
                    foreign_key["constrained_columns"], foreign_key["referred_columns"]
                )
            )
    assert actual_foreign_keys == expected_foreign_keys

    expected_nullable_columns = {
        "substations": set(),
        "feeders": set(),
        "transformers": set(),
        "poles": {"pin_code", "parent_pole_id", "seq_on_line"},
        "topology_edges": {"calibration_bucket"},
        "devices": {"next_heartbeat_offset_seconds"},
        "device_assignments": {"effective_to"},
        "telemetry_events": {
            "device_id",
            "pole_id",
            "processed_at",
            "failed_reason",
            "epoch_decision",
        },
        "device_stream_state": set(),
        "pole_evidence_state": {"source_event_id", "fresh_until"},
        "detection_candidates": {"promotion_outcome"},
        "scheduled_outages": set(),
        "planned_operations": {
            "incident_id",
            "observed_start",
            "observed_end",
            "promotion_outcome",
        },
        "incidents": {"feeder_id", "transformer_id", "pole_id", "simulation_id"},
        "incident_boundaries": {"upstream_pole_id", "downstream_pole_id"},
        "incident_evidence": set(),
        "ticket_events": {"from_status", "to_status"},
        "simulator_runs": {"finished_at"},
        "simulated_faults": {"repaired_at"},
        "ai_explanations": {"model", "latency_ms", "fallback_reason"},
    }
    for table_name, expected in expected_nullable_columns.items():
        actual = {
            column["name"]
            for column in inspector.get_columns(table_name)
            if column["nullable"]
        }
        assert actual == expected, table_name

    with engine.connect() as connection:
        index_names = set(
            connection.execute(
                text("select indexname from pg_indexes where schemaname = 'public'")
            ).scalars()
        )
        constraints = dict(
            connection.execute(
                text(
                    "select conname, pg_get_constraintdef(oid) "
                    "from pg_constraint where connamespace = 'public'::regnamespace"
                )
            ).all()
        )

    assert {
        "uq_telemetry_events_fingerprint",
        "uq_incidents_active_correlation",
        "ix_telemetry_events_processing",
        "ix_incidents_status_updated",
        "ix_device_assignments_effective",
        "ix_topology_edges_transformer_parent",
    }.issubset(index_names)
    incident_check = constraints["ck_incidents_status"]
    evidence_check = constraints["ck_pole_evidence_state_class"]
    assert "status" in incident_check
    assert set(re.findall(r"'([^']+)'", incident_check)) == {
        "detected",
        "acknowledged",
        "crew_assigned",
        "resolved",
        "verified",
        "closed",
    }
    assert "evidence_class" in evidence_check
    assert set(re.findall(r"'([^']+)'", evidence_check)) == {
        "confirmed_live",
        "confirmed_dark",
        "unknown_silent",
        "uninstrumented",
        "device_suspect",
    }


def test_seed_if_empty_returns_existing_counts_without_duplicates():
    # Break caught: a restart inserts a second copy of the deterministic asset registry.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("truncate table substations, devices cascade"))
            with Session(bind=connection) as session:
                assert session.scalar(select(func.count()).select_from(Substation)) == 0
                assert session.scalar(select(func.count()).select_from(Feeder)) == 0
                assert session.scalar(select(func.count()).select_from(Transformer)) == 0
                assert session.scalar(select(func.count()).select_from(Pole)) == 0
                assert session.scalar(select(func.count()).select_from(Device)) == 0

                first = seed_if_empty(session, seed=20260803)
                second = seed_if_empty(session, seed=20260803)

                assert first == SeedSummary(4, 12, 60, 4200, 3822)
                assert second == first
                assert session.scalar(select(func.count()).select_from(Substation)) == 4
                assert session.scalar(select(func.count()).select_from(Feeder)) == 12
                assert session.scalar(select(func.count()).select_from(Transformer)) == 60
                assert session.scalar(select(func.count()).select_from(Pole)) == 4200
                assert session.scalar(select(func.count()).select_from(Device)) == 3822
        finally:
            transaction.rollback()
