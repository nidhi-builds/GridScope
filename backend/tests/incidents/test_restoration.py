from datetime import UTC, datetime, timedelta
from sqlalchemy import func, select

from app.db.models.assets import DeviceAssignment, Pole
from app.db.models.incidents import IncidentEvidence
from app.db.models.telemetry import TelemetryEvent
from app.db.models.telemetry import DeviceStreamState
from app.db.models.telemetry import PoleEvidenceState
from app.incidents.correlation import IncidentHypothesis, upsert_incident
from app.incidents.restoration import evaluate_restoration
from app.telemetry.ingestion import accept_payload
from app.telemetry.schemas import TelemetryPayload
from app.telemetry.worker import process_inbox_batch
from app.incidents.workflow import transition_ticket


NOW = datetime(2026, 8, 4, 12, tzinfo=UTC)


def _resolved_incident(session):
    pole = session.scalar(select(Pole).where(Pole.pin_code.is_not(None)).limit(1))
    incident = upsert_incident(session, IncidentHypothesis(
        fault_class="span", location_class="span", transformer_id=pole.transformer_id,
        pole_id=pole.id, downstream_pole_id=pole.id, pin_code=pole.pin_code, pin_source="registry",
        affected_count=2, confidence="high", navigation_latitude=12.0, navigation_longitude=77.0,
    ))
    transition_ticket(session, incident.id, "acknowledge", "operator", {})
    transition_ticket(session, incident.id, "assign_crew", "operator", {})
    transition_ticket(session, incident.id, "report_resolved", "operator", {})
    return incident


def test_restoration_requires_thirty_seconds_of_fresh_live_evidence(session):
    incident = _resolved_incident(session)
    live_at = NOW

    early = evaluate_restoration(session, incident.id, live_at, [{"pole_id": incident.pole_id, "event_type": "power_restored", "energized": True, "received_at": live_at}])
    stable = evaluate_restoration(session, incident.id, live_at + timedelta(seconds=30), [{"pole_id": incident.pole_id, "event_type": "power_restored", "energized": True, "received_at": live_at}])

    assert early.verified is False
    assert stable.verified is True
    assert incident.status == "closed"


def test_fresh_dark_contradiction_prevents_restoration(session):
    incident = _resolved_incident(session)

    result = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=31), [
        {"pole_id": incident.pole_id, "event_type": "power_restored", "energized": True, "received_at": NOW},
        {"pole_id": incident.pole_id, "event_type": "power_lost", "energized": False, "received_at": NOW + timedelta(seconds=1)},
    ])

    assert result.verified is False
    assert result.code == "fresh_dark_contradiction"


def test_restoration_requires_direct_boundary_and_each_dark_branch(session):
    transformer_id = session.scalar(
        select(Pole.transformer_id)
        .join(DeviceAssignment)
        .group_by(Pole.transformer_id)
        .having(func.count(func.distinct(Pole.branch_index)) >= 2)
        .limit(1)
    )
    first = session.scalar(select(Pole).join(DeviceAssignment).where(Pole.transformer_id == transformer_id, Pole.pin_code.is_not(None)).limit(1))
    second = session.scalar(
        select(Pole).join(DeviceAssignment).where(
            Pole.transformer_id == first.transformer_id, Pole.branch_index != first.branch_index,
        ).limit(1)
    )
    incident = _resolved_incident(session)
    incident.pole_id, incident.transformer_id = first.id, first.transformer_id
    dark_events = []
    for pole in (first, second):
        assignment = session.scalar(select(DeviceAssignment).where(DeviceAssignment.pole_id == pole.id).limit(1))
        event = TelemetryEvent(
            device_id=assignment.device_id, pole_id=pole.id, fingerprint=f"dark-{pole.id}", event_type="power_lost",
            payload={"energized": False}, device_time=NOW - timedelta(seconds=1), received_at=NOW - timedelta(seconds=1),
        )
        session.add(event)
        dark_events.append(event)
    session.flush()
    for event in dark_events:
        session.add(IncidentEvidence(incident_id=incident.id, telemetry_event_id=event.id, evidence_class="prior_dark"))

    boundary_only = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), [
        {"pole_id": first.id, "event_type": "power_restored", "energized": True, "received_at": NOW},
    ])
    all_branches = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), [
        {"pole_id": first.id, "event_type": "power_restored", "energized": True, "received_at": NOW},
        {"pole_id": second.id, "event_type": "boot", "energized": True, "received_at": NOW},
    ])

    assert boundary_only.code == "branch_restoration_missing"
    assert all_branches.verified is True


def test_heartbeat_does_not_prove_restoration_and_scope_dark_blocks_it(session):
    incident = _resolved_incident(session)
    assignment = session.scalar(select(DeviceAssignment).limit(1))
    incident.pole_id, incident.transformer_id = assignment.pole_id, session.get(Pole, assignment.pole_id).transformer_id
    dark = TelemetryEvent(
        device_id=assignment.device_id, pole_id=assignment.pole_id, fingerprint="credible-dark",
        event_type="power_lost", payload={"energized": False}, device_time=NOW, received_at=NOW,
        processing_state="processed",
    )
    session.add(dark)
    session.flush()
    session.add(PoleEvidenceState(
        pole_id=incident.pole_id, evidence_class="confirmed_dark", source_event_id=dark.id, device_health="healthy", evidence={},
    ))

    result = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), [
        {"pole_id": incident.pole_id, "event_type": "heartbeat", "energized": True, "received_at": NOW},
    ])

    assert result.code == "fresh_dark_contradiction"


def test_unknown_boundary_lowers_confidence_without_blocking_other_direct_restoration(session):
    incident = _resolved_incident(session)
    session.add(PoleEvidenceState(
        pole_id=incident.pole_id, evidence_class="unknown_silent", device_health="silent", evidence={},
    ))

    result = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), [
        {"pole_id": "representative", "event_type": "power_restored", "energized": True, "received_at": NOW},
    ])

    assert result.verified is True
    assert incident.confidence == "low"


def test_stability_starts_at_the_last_required_direct_restoration_proof(session):
    transformer_id = session.scalar(
        select(Pole.transformer_id).join(DeviceAssignment).group_by(Pole.transformer_id)
        .having(func.count(func.distinct(Pole.branch_index)) >= 2).limit(1)
    )
    first = session.scalar(select(Pole).join(DeviceAssignment).where(Pole.transformer_id == transformer_id).limit(1))
    second = session.scalar(
        select(Pole).join(DeviceAssignment).where(Pole.transformer_id == transformer_id, Pole.branch_index != first.branch_index).limit(1)
    )
    incident = _resolved_incident(session)
    incident.pole_id, incident.transformer_id = first.id, transformer_id
    for pole in (first, second):
        assignment = session.scalar(select(DeviceAssignment).where(DeviceAssignment.pole_id == pole.id).limit(1))
        event = TelemetryEvent(
            device_id=assignment.device_id, pole_id=pole.id, fingerprint=f"prior-{pole.id}", event_type="power_lost",
            payload={"energized": False}, device_time=NOW - timedelta(seconds=1), received_at=NOW - timedelta(seconds=1),
        )
        session.add(event)
        session.flush()
        session.add(IncidentEvidence(incident_id=incident.id, telemetry_event_id=event.id, evidence_class="prior_dark"))
    reports = [
        {"pole_id": first.id, "event_type": "power_restored", "energized": True, "received_at": NOW},
        {"pole_id": second.id, "event_type": "boot", "energized": True, "received_at": NOW + timedelta(seconds=20)},
    ]

    pending = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), reports)
    verified = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=50), reports)

    assert pending.code == "stability_pending"
    assert verified.verified is True


def test_unrelated_transformer_branch_dark_does_not_block_restoration(session):
    transformer_id = session.scalar(
        select(Pole.transformer_id).join(DeviceAssignment).group_by(Pole.transformer_id)
        .having(func.count(func.distinct(Pole.branch_index)) >= 2).limit(1)
    )
    boundary = session.scalar(select(Pole).join(DeviceAssignment).where(Pole.transformer_id == transformer_id).limit(1))
    unrelated = session.scalar(
        select(Pole).where(Pole.transformer_id == transformer_id, Pole.branch_index != boundary.branch_index).limit(1)
    )
    incident = _resolved_incident(session)
    incident.pole_id, incident.transformer_id = boundary.id, transformer_id
    session.add(PoleEvidenceState(pole_id=unrelated.id, evidence_class="confirmed_dark", device_health="healthy", evidence={}))

    result = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), [
        {"pole_id": boundary.id, "event_type": "power_restored", "energized": True, "received_at": NOW},
    ])

    assert result.verified is True


def test_dark_after_final_proof_breaks_the_full_stability_window(session):
    incident = _resolved_incident(session)
    assignment = session.scalar(select(DeviceAssignment).limit(1))
    incident.pole_id = assignment.pole_id
    incident.transformer_id = session.get(Pole, assignment.pole_id).transformer_id
    dark = TelemetryEvent(
        device_id=assignment.device_id, pole_id=incident.pole_id, fingerprint="dark-during-stability",
        event_type="power_lost", payload={"energized": False}, device_time=NOW + timedelta(seconds=10),
        received_at=NOW + timedelta(seconds=10), processing_state="processed",
    )
    session.add(dark)
    session.flush()
    session.add(PoleEvidenceState(
        pole_id=assignment.pole_id, evidence_class="confirmed_dark", source_event_id=dark.id,
        device_health="healthy", evidence={},
    ))

    result = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), [
        {"pole_id": incident.pole_id, "event_type": "power_restored", "energized": True, "received_at": NOW},
    ])

    assert result.code == "fresh_dark_contradiction"


def test_only_processed_confirmed_dark_evidence_breaks_stability(session):
    incident = _resolved_incident(session)
    assignment = session.scalar(select(DeviceAssignment).limit(1))
    incident.pole_id, incident.transformer_id = assignment.pole_id, session.get(Pole, assignment.pole_id).transformer_id
    quarantined = TelemetryEvent(
        device_id=assignment.device_id, pole_id=assignment.pole_id, fingerprint="quarantined-dark",
        event_type="power_lost", payload={"energized": False}, device_time=NOW + timedelta(seconds=10),
        received_at=NOW + timedelta(seconds=10), processing_state="quarantined",
    )
    session.add(quarantined)

    accepted = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), [
        {"pole_id": assignment.pole_id, "event_type": "power_restored", "energized": True, "received_at": NOW},
    ])
    assert accepted.verified is True

    incident = _resolved_incident(session)
    incident.pole_id, incident.transformer_id = assignment.pole_id, session.get(Pole, assignment.pole_id).transformer_id
    credible = TelemetryEvent(
        device_id=assignment.device_id, pole_id=assignment.pole_id, fingerprint="processed-dark",
        event_type="power_lost", payload={"energized": False}, device_time=NOW + timedelta(seconds=10),
        received_at=NOW + timedelta(seconds=10), processing_state="processed",
    )
    session.add(credible)
    session.flush()
    session.add(PoleEvidenceState(
        pole_id=assignment.pole_id, evidence_class="confirmed_dark", source_event_id=credible.id,
        device_health="healthy", evidence={},
    ))

    blocked = evaluate_restoration(session, incident.id, NOW + timedelta(seconds=30), [
        {"pole_id": assignment.pole_id, "event_type": "power_restored", "energized": True, "received_at": NOW},
    ])
    assert blocked.code == "fresh_dark_contradiction"


def test_worker_rechecks_a_resolved_incident_after_stable_restoration(session):
    assignment = session.scalar(
        select(DeviceAssignment)
        .join(Pole, Pole.id == DeviceAssignment.pole_id)
        .outerjoin(DeviceStreamState, DeviceStreamState.device_id == DeviceAssignment.device_id)
        .where(Pole.pin_code.is_not(None), DeviceStreamState.id.is_(None)).limit(1)
    )
    incident = _resolved_incident(session)
    incident.pole_id = assignment.pole_id
    incident.transformer_id = session.get(Pole, assignment.pole_id).transformer_id
    accept_payload(session, TelemetryPayload(
        device_id=assignment.device_id, pole_id=assignment.pole_id, seq=1, ts=NOW,
        event_type="power_restored", energized=True,
    ), NOW)

    process_inbox_batch(session, limit=10, now=NOW)
    process_inbox_batch(session, limit=0, now=NOW + timedelta(seconds=30))

    state = session.scalar(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == assignment.pole_id))
    assert incident.status == "closed", (state.evidence_class, state.source_event_id, state.fresh_until)
