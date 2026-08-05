from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.ai.client import GeminiRequestError
from app.ai.service import create_explanation
from app.config import Settings
from app.db.models.assets import Device, Pole, TopologyEdge
from app.db.models.incidents import AIExplanation, Incident, IncidentBoundary, IncidentEvidence, ScheduledOutage, TicketEvent
from app.db.models.simulator import SimulatedFault, SimulatorRun
from app.db.models.telemetry import DetectionCandidate, TelemetryEvent
from app.seed import seed_if_empty
from app.simulator.scenarios import SCENARIOS
from app.simulator.service import repair_run, reset_runs, start_run


def _offline_requester(facts, settings):
    """Force the deterministic fallback so the test never calls a real model."""
    raise GeminiRequestError("offline")


EFFECT_FIELDS = {
    "device_death": {"device_unavailable": {"device_id"}, "live_downstream": {"event_ids"}},
    "dt_fault": {"dt_scope_fault": {"transformer_id", "deenergized_pole_ids", "loss_event_ids"}},
    "feeder_fault": {"feeder_scope_fault": {"feeder_id", "transformer_ids", "loss_event_ids"}},
    "firmware_12_silence": {"firmware_12_silence": {"silent_device_id", "attempted_loss_event_ids"}},
    "inferred_span": {"inferred_topology": {"topology_source", "calibration_bucket", "loss_event_ids"}},
    "known_span": {"known_topology": {"topology_source", "target_edge", "loss_event_ids"}},
    "missing_endpoints": {"missing_endpoints": {"suppressed_endpoint_pole_ids", "loss_event_ids"}},
    "noise_baseline": {"offline_baseline": {"offline_device_id"}, "heartbeat_noise": {"event_ids"}},
    "planned_outage": {"planned_schedule": {"schedule_ids"}, "schedule_variants": {"variants"}},
    "real_fault_during_schedule": {"unmatched_schedule": {"schedule_ids", "fault_transformer_id"}, "span_fault": {"loss_event_ids"}},
    "reboot_replay": {"reboot": {"boot_event_ids"}, "stale_replay": {"audit_event_ids", "audit_decisions"}},
    "repair_relapse": {"repair": {"closed_incident_id", "restoration_event_ids"}, "relapse": {"incident_id", "relapse_of"}},
    "same_path_faults": {"same_path_faults": {"first_loss_event_ids", "second_loss_event_ids"}},
    "three_branch_faults": {"independent_branches": {"target_edges", "loss_event_ids"}},
    "tier_one": {"tier_one_expiry": {"expired_candidate_id"}, "tier_one_promotion": {"promoted_incident_id", "loss_event_ids"}},
    "transport_noise": {"duplicate": {"duplicate_attempts"}, "out_of_order": {"audit_event_ids", "audit_decisions"}, "retry": {"retried_payload_ids"}},
    "weak_inferred": {"weak_inferred_topology": {"topology_source", "calibration_bucket", "loss_event_ids"}},
}


def test_start_run_persists_truth_and_only_public_telemetry(session):
    run = start_run(session, "known_span", 7)

    assert run.status == "completed"
    assert run.expected_results["incident_count"] == 1
    assert run.actual_results["accepted_events"] >= 0
    assert session.scalar(select(SimulatedFault).where(SimulatedFault.simulator_run_id == run.id))


def test_known_span_records_observed_incident_outcome(session):
    run = start_run(session, "known_span", 7)

    assert run.actual_results["outcome"] == "matched"
    assert run.actual_results["incident_count"] == 1
    assert session.scalar(select(Incident.simulation_id)) == run.id


def test_repair_marks_fault_and_uses_same_run(session):
    run = start_run(session, "known_span", 7)
    repaired = repair_run(session, run.id)

    fault = session.scalar(select(SimulatedFault).where(SimulatedFault.simulator_run_id == run.id))
    assert repaired.id == run.id
    assert fault.repaired_at is not None


def test_repair_is_processed_through_the_worker_and_verifies_the_run_incident(session):
    run = start_run(session, "known_span", 7)

    repaired = repair_run(session, run.id)

    incident = session.scalar(select(Incident).where(Incident.simulation_id == run.id))
    assert incident.status == "closed"
    assert repaired.actual_results["repair_outcome"] == "verified"
    assert repaired.actual_results["restoration_elapsed_seconds"] <= 120


def test_unobservable_run_reports_label_without_fabricating_success(session):
    run = start_run(session, "firmware_12_silence", 7)

    assert run.actual_results["outcome"] == "unobservable"
    assert run.actual_results["accepted_events"] == 0


def test_masked_topology_does_not_crash_a_dt_run(session):
    run = start_run(session, "dt_fault", 20260803)

    assert run.actual_results["outcome"] in {"matched", "mismatch"}


def test_existing_deterministic_seed_backfills_inferred_span_topology(session):
    """An upgraded local seed must retain a public inferred graph for this preset."""
    seed_if_empty(session, 20260803)

    assert session.scalar(
        select(func.count()).select_from(TopologyEdge).where(TopologyEdge.source == "inferred")
    ) > 0


def test_inferred_span_reports_a_corridor_until_precision_is_calibrated(session):
    seed_if_empty(session, 20260803)

    run = start_run(session, "inferred_span", 20260803)

    assert run.actual_results["outcome"] == "matched"
    assert run.actual_results["classes"] == ("corridor",)


def test_dt_fault_is_one_transformer_incident(session):
    run = start_run(session, "dt_fault", 20260803)

    assert run.actual_results["incident_count"] == 1
    assert run.actual_results["classes"] == ("dt",)


def test_feeder_fault_closes_run_scoped_lower_boundary_incidents(session):
    run = start_run(session, "feeder_fault", 20260803)

    active = list(session.scalars(
        select(Incident).where(Incident.simulation_id == run.id, Incident.status != "closed")
    ))
    assert [(incident.fault_class, incident.status) for incident in active] == [("feeder", "detected")]


def test_three_branch_faults_emit_one_span_incident_per_independent_branch(session):
    run = start_run(session, "three_branch_faults", 20260803)

    assert run.actual_results["outcome"] == "matched"
    assert run.actual_results["incident_count"] == 3
    assert run.actual_results["classes"] == ("span", "span", "span")


def test_reset_removes_ai_explanations_attached_to_simulated_incidents(session):
    """Reset predates the AI explanation table; a generated explanation must not pin an incident."""
    run = start_run(session, "known_span", 20260803)
    incident = session.scalar(select(Incident).where(Incident.simulation_id == run.id))
    assert incident is not None
    create_explanation(session, incident, Settings(_env_file=None), _offline_requester)
    assert session.scalar(select(func.count()).select_from(AIExplanation).where(AIExplanation.incident_id == incident.id)) == 1

    reset_runs(session)

    assert session.scalar(select(func.count()).select_from(AIExplanation)) == 0
    assert session.scalar(select(func.count()).select_from(Incident).where(Incident.simulation_id == run.id)) == 0


def test_reset_restores_future_anchor_stream_state_before_next_run(session):
    start_run(session, "inferred_span", 20260803)
    reset_runs(session)

    run = start_run(session, "known_span", 20260803)

    assert run.actual_results["outcome"] == "matched"
    assert run.actual_results["classes"] == ("span",)


def test_every_observable_preset_reaches_a_compared_outcome(session):
    for definition in SCENARIOS.values():
        reset_runs(session)
        run = start_run(session, definition.key, 20260803)

        assert run.actual_results["outcome"] == (
            "unobservable" if definition.observability == "unobservable" else "matched"
        ), f"{definition.key}: {run.actual_results}"
        assert set(run.actual_results["generated_effects"]) == set(definition.effects)
        evidence = run.actual_results["effect_evidence"]
        assert set(evidence) == set(definition.effects), f"{definition.key}: {run.actual_results}"
        for effect, fields in EFFECT_FIELDS[definition.key].items():
            assert fields <= set(evidence[effect]), f"{definition.key}/{effect}: {evidence[effect]}"


def test_simulator_never_reuses_or_mutates_a_real_open_incident(session):
    real = session.scalar(select(Incident).where(Incident.simulation_id.is_(None), Incident.status != "closed"))
    if real is None:
        pytest.skip("seed did not provide a real open incident")
    before = (real.id, real.updated_at, real.status)

    run = start_run(session, "known_span", 20260803)
    session.flush()

    session.refresh(real)
    assert (real.id, real.updated_at, real.status) == before
    assert all(incident.simulation_id == run.id for incident in session.scalars(select(Incident).where(Incident.simulation_id == run.id)))


def test_reset_restores_device_availability_and_removes_run_schedules(session):
    death = start_run(session, "device_death", 20260803)
    device_id = next(iter(death.truth["device_online_before"]))
    planned = start_run(session, "planned_outage", 20260803)

    reset_runs(session)

    assert session.get(Device, device_id).is_online is True
    assert session.scalar(select(func.count()).select_from(ScheduledOutage).where(ScheduledOutage.external_id.like(f"sim:{planned.id}:%"))) == 0


def test_repair_relapse_closes_then_links_a_new_publicly_processed_incident(session):
    run = start_run(session, "repair_relapse", 20260803)

    incidents = list(session.scalars(select(Incident).where(Incident.simulation_id == run.id)))
    events = list(session.scalars(select(TicketEvent).where(TicketEvent.incident_id.in_([item.id for item in incidents]))))
    closed = next(item for item in incidents if item.status == "closed")
    relapse = next(item for item in incidents if item.status == "detected")

    assert sorted(item.status for item in incidents) == ["closed", "detected"]
    assert any(event.incident_id == relapse.id and event.reason == f"relapse_of:{closed.id}" for event in events)
    assert any(event.incident_id == closed.id and event.reason == f"relapse_detected:{relapse.id}" for event in events)
    assert run.actual_results["effect_evidence"]["repair"]["closed_incident_id"] == str(closed.id)
    assert run.actual_results["effect_evidence"]["relapse"]["incident_id"] == str(relapse.id)


def test_simulator_schedule_worker_and_reset_do_not_touch_real_candidate_or_incident(session):
    pole = session.scalar(select(Pole).where(Pole.pin_code.is_not(None)).limit(1))
    real_candidate = DetectionCandidate(
        transformer_id=pole.transformer_id, scope_key=f"dt:{pole.transformer_id}",
        first_received_at=datetime.now(UTC) - timedelta(minutes=2),
        expires_at=datetime.now(UTC) - timedelta(minutes=1), status="investigating", evidence_event_ids=[],
    )
    real_incident = Incident(
        correlation_key=f"real-isolation:{uuid4()}", fault_class="span", status="detected", location_class="span",
        transformer_id=pole.transformer_id, feeder_id=None, pole_id=pole.id, pin_code="999999", pin_source="test",
        affected_count=1, confidence="medium", confidence_reasons=[], navigation_latitude=0, navigation_longitude=0,
    )
    telemetry = TelemetryEvent(
        device_id=session.scalar(select(Device.id).limit(1)), pole_id=pole.id, fingerprint=uuid4().hex,
        event_type="heartbeat", payload={"seq": 99}, device_time=datetime.now(UTC), received_at=datetime.now(UTC),
    )
    session.add_all((real_candidate, real_incident, telemetry))
    session.flush()
    boundary = IncidentBoundary(incident_id=real_incident.id, boundary_type="span", upstream_pole_id=None, downstream_pole_id=pole.id, candidate_spans=[[str(pole.id)]], geometry={"real": True})
    evidence = IncidentEvidence(incident_id=real_incident.id, telemetry_event_id=telemetry.id, evidence_class="candidate", evidence={"real": True})
    session.add_all((boundary, evidence))
    session.flush()
    before = (real_candidate.status, real_incident.status, boundary.candidate_spans, evidence.evidence)

    start_run(session, "planned_outage", 20260803)
    reset_runs(session)
    session.refresh(real_candidate)
    session.refresh(real_incident)
    session.refresh(boundary)
    session.refresh(evidence)

    assert (real_candidate.status, real_incident.status, boundary.candidate_spans, evidence.evidence) == before
