from sqlalchemy import select

from app.db.models.assets import Pole
from app.db.models.incidents import TicketEvent
from app.db.models.telemetry import PoleEvidenceState
from app.incidents.correlation import IncidentHypothesis, upsert_incident
from app.incidents import workflow
from app.incidents.workflow import transition_ticket


def _incident(session):
    pole = session.scalar(select(Pole).where(Pole.pin_code.is_not(None)).limit(1))
    return upsert_incident(session, IncidentHypothesis(
        fault_class="span", location_class="span", transformer_id=pole.transformer_id, pole_id=pole.id,
        downstream_pole_id=pole.id, pin_code=pole.pin_code, pin_source="registry",
        affected_count=2, confidence="high", navigation_latitude=12.0, navigation_longitude=77.0,
    ))


def test_ticket_actions_follow_the_only_valid_operator_path(session):
    incident = _incident(session)

    assert transition_ticket(session, incident.id, "acknowledge", "operator", {}).accepted
    assert transition_ticket(session, incident.id, "assign_crew", "operator", {}).accepted
    assert transition_ticket(session, incident.id, "report_resolved", "operator", {}).accepted
    assert transition_ticket(session, incident.id, "verified", "operator", {}).accepted is False
    assert incident.status == "resolved"


def test_invalid_resolution_is_recorded_but_rejected(session):
    incident = _incident(session)
    transition_ticket(session, incident.id, "acknowledge", "operator", {})
    transition_ticket(session, incident.id, "assign_crew", "operator", {})
    session.add(PoleEvidenceState(
        pole_id=incident.pole_id, evidence_class="confirmed_dark", device_health="healthy", evidence={},
    ))

    result = transition_ticket(session, incident.id, "report_resolved", "operator", {})

    assert result.accepted is False
    assert result.code == "confirmed_dark_remains"
    assert result.incident.status == "crew_assigned"
    assert result.audit_event.action == "resolution_rejected"
    assert len(session.query(TicketEvent).all()) == 3


def test_workflow_exposes_no_arbitrary_verified_or_closed_transition():
    assert not hasattr(workflow, "_system_transition")
