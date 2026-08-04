from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.db.models.assets import DeviceAssignment, Pole, TopologyEdge, Transformer

from app.db.models.incidents import Incident, IncidentBoundary, IncidentEvidence, TicketEvent
from app.db.models.simulator import SimulatorRun
from app.db.models.telemetry import DetectionCandidate, DeviceStreamState, TelemetryEvent
from app.incidents.correlation import IncidentHypothesis, upsert_incident
from app.telemetry.ingestion import accept_payload
from app.telemetry.schemas import TelemetryPayload
from app.telemetry.worker import process_inbox_batch


NOW = datetime(2026, 8, 4, 12, tzinfo=UTC)


def _hypothesis(session, **changes):
    pole = session.scalar(select(Pole).where(Pole.pin_code.is_not(None)).limit(1))
    values = {
        "fault_class": "span",
        "location_class": "corridor",
        "transformer_id": pole.transformer_id,
        "downstream_pole_id": pole.id,
        "pin_code": pole.pin_code,
        "pin_source": "registry",
        "affected_count": 10,
        "confidence": "medium",
        "navigation_latitude": 12.0,
        "navigation_longitude": 77.0,
    }
    values.update(changes)
    return IncidentHypothesis(**values)


def _event(session):
    assignment = session.scalar(select(DeviceAssignment).limit(1))
    event = TelemetryEvent(
        device_id=assignment.device_id, pole_id=assignment.pole_id, fingerprint=uuid4().hex,
        event_type="power_lost", payload={}, device_time=NOW, received_at=NOW,
    )
    session.add(event)
    session.flush()
    return event


def test_repeated_boundary_evidence_creates_one_active_incident(session):
    hypothesis = _hypothesis(session, evidence_ids=[_event(session).id])

    first = upsert_incident(session, hypothesis)
    second = upsert_incident(session, hypothesis)

    assert first.id == second.id
    assert session.scalars(select(Incident)).all() == [first]
    assert len(session.scalars(select(IncidentEvidence)).all()) == 1


def test_corridor_refinement_keeps_incident_and_appends_boundary_history(session):
    corridor = _hypothesis(session)
    exact = _hypothesis(
        session,
        upstream_pole_id=corridor.upstream_pole_id,
        downstream_pole_id=corridor.downstream_pole_id,
        location_class="span",
    )

    incident = upsert_incident(session, corridor)
    refined = upsert_incident(session, exact)

    assert refined.id == incident.id
    assert refined.location_class == "span"
    assert [boundary.boundary_type for boundary in session.scalars(select(IncidentBoundary)).all()] == ["corridor", "span"]
    assert session.scalar(select(TicketEvent.event_type).where(TicketEvent.incident_id == incident.id)) == "location_refined"


def test_feeder_rollup_audits_the_open_dt_incident_without_deleting_it(session):
    transformer = session.scalar(select(Transformer).limit(1))
    dt = upsert_incident(session, _hypothesis(session, fault_class="dt", feeder_id=transformer.feeder_id))
    feeder = upsert_incident(session, _hypothesis(
        session, fault_class="feeder", transformer_id=None, feeder_id=transformer.feeder_id,
        downstream_pole_id=None, pole_id=None,
    ))

    event = session.scalar(select(TicketEvent).where(TicketEvent.incident_id == dt.id))
    assert session.get(Incident, dt.id).status == "detected"
    assert event.event_type == "superseded_by_feeder"
    assert event.reason == f"superseded_by:{feeder.id}"


def test_simulated_feeder_rollup_closes_lower_incident_with_audit(session):
    transformer = session.scalar(select(Transformer).limit(1))
    run = SimulatorRun(seed=1, scenario="rollup", status="completed", started_at=NOW, finished_at=NOW, truth={})
    session.add(run)
    session.flush()
    lower = upsert_incident(session, _hypothesis(
        session, fault_class="corridor", feeder_id=transformer.feeder_id, simulation_id=run.id,
    ))
    feeder = upsert_incident(session, _hypothesis(
        session, fault_class="feeder", transformer_id=None, feeder_id=transformer.feeder_id,
        downstream_pole_id=None, pole_id=None, simulation_id=run.id,
    ))

    event = session.scalar(select(TicketEvent).where(TicketEvent.incident_id == lower.id))
    assert session.get(Incident, lower.id).status == "closed"
    assert (event.event_type, event.from_status, event.to_status) == ("superseded_by_feeder", "detected", "closed")
    assert event.reason == f"superseded_by:{feeder.id}"


def test_post_close_relapse_creates_auditable_linked_incident(session):
    original = upsert_incident(session, _hypothesis(session))
    original.status = "closed"

    relapse = upsert_incident(session, _hypothesis(session))

    assert relapse.id != original.id
    assert session.scalar(select(TicketEvent.reason).where(TicketEvent.incident_id == relapse.id)) == f"relapse_of:{original.id}"


def test_real_worker_feeder_promotion_uses_one_feeder_scoped_incident(session, monkeypatch):
    import app.detection.candidates as candidates

    parent_assignment, child_assignment = aliased(DeviceAssignment), aliased(DeviceAssignment)
    parent, child = session.execute(
        select(parent_assignment, child_assignment)
        .join(TopologyEdge, TopologyEdge.parent_pole_id == parent_assignment.pole_id)
        .join(child_assignment, child_assignment.pole_id == TopologyEdge.child_pole_id)
        .join(Transformer, Transformer.id == TopologyEdge.transformer_id)
        .where(TopologyEdge.is_visible.is_(True), TopologyEdge.source == "registry")
        .order_by(TopologyEdge.id).limit(1)
    ).one()
    feeder_id = session.get(Transformer, session.get(Pole, child.pole_id).transformer_id).feeder_id
    sibling_transformer = session.scalar(select(Transformer.id).where(
        Transformer.feeder_id == feeder_id, Transformer.id != session.get(Pole, child.pole_id).transformer_id,
    ).limit(1))
    dt = upsert_incident(session, _hypothesis(session, fault_class="dt", transformer_id=sibling_transformer, feeder_id=feeder_id))
    session.add(DetectionCandidate(
        transformer_id=sibling_transformer, scope_key=f"dt:{sibling_transformer}", first_received_at=NOW,
        expires_at=NOW + timedelta(seconds=45), status="actionable", promotion_outcome="dt",
    ))
    evaluate = candidates.evaluate_events
    calls = []
    def classify_as_feeder(*args, **kwargs):
        base = evaluate(*args, **kwargs)
        calls.append(base)
        return candidates.CandidateOutcome(
            "actionable", "dt" if len(calls) == 1 else "feeder", True, boundaries=base.boundaries,
        )
    monkeypatch.setattr(candidates, "evaluate_events", classify_as_feeder)
    monkeypatch.setattr(candidates, "_feeder_coverage", lambda *args: {"feeder_dts": {feeder_id: {"qualifying": {session.get(Pole, child.pole_id).transformer_id}, "total": 1}}})
    for assignment, event_type, energized in ((child, "power_lost", False), (parent, "heartbeat", True)):
        accept_payload(session, TelemetryPayload(
            device_id=assignment.device_id, pole_id=assignment.pole_id, seq=1, ts=NOW,
            event_type=event_type, energized=energized,
        ), NOW)

    process_inbox_batch(session, limit=10, now=NOW + timedelta(seconds=30))

    feeder = session.scalar(select(Incident).where(Incident.fault_class == "feeder"))
    assert feeder.feeder_id == feeder_id
    assert feeder.transformer_id is None and feeder.pole_id is None
    assert feeder.correlation_key == f"feeder:{feeder_id}:None"
    assert session.scalar(select(TicketEvent.event_type).where(TicketEvent.incident_id == dt.id)) == "superseded_by_feeder"


def test_actionable_candidate_is_promoted_once_by_the_worker(session):
    parent_assignment, child_assignment = aliased(DeviceAssignment), aliased(DeviceAssignment)
    parent_state, child_state = aliased(DeviceStreamState), aliased(DeviceStreamState)
    child_pole = aliased(Pole)
    parent, child = session.execute(
        select(parent_assignment, child_assignment)
        .join(TopologyEdge, TopologyEdge.parent_pole_id == parent_assignment.pole_id)
        .join(child_assignment, child_assignment.pole_id == TopologyEdge.child_pole_id)
        .join(child_pole, child_pole.id == child_assignment.pole_id)
        .outerjoin(parent_state, parent_state.device_id == parent_assignment.device_id)
        .outerjoin(child_state, child_state.device_id == child_assignment.device_id)
        .where(
            TopologyEdge.is_visible.is_(True), TopologyEdge.source == "registry", child_pole.pin_code.is_not(None),
            parent_state.id.is_(None), child_state.id.is_(None),
        )
        .order_by(TopologyEdge.id)
        .limit(1)
    ).one()
    for assignment, event_type, energized in ((child, "power_lost", False), (parent, "heartbeat", True)):
        accept_payload(session, TelemetryPayload(
            device_id=assignment.device_id, pole_id=assignment.pole_id, seq=1, ts=NOW,
            event_type=event_type, energized=energized,
        ), NOW)

    process_inbox_batch(session, limit=10, now=NOW + timedelta(seconds=30))

    candidate = session.scalar(select(DetectionCandidate))
    assert candidate.status == "promoted", (candidate.status, candidate.evidence_event_ids, candidate.promotion_outcome)
    assert len(session.scalars(select(Incident)).all()) == 1
