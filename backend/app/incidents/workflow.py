from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.incidents import Incident, TicketEvent
from app.db.models.telemetry import PoleEvidenceState


@dataclass(frozen=True)
class TransitionResult:
    accepted: bool
    code: str
    incident: Incident
    audit_event: TicketEvent


_ACTIONS = {
    "acknowledge": ("detected", "acknowledged"),
    "assign_crew": ("acknowledged", "crew_assigned"),
    "report_resolved": ("crew_assigned", "resolved"),
}


def transition_ticket(session: Session, incident_id: UUID, action: str, actor: str, payload: dict) -> TransitionResult:
    incident = session.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
    if incident is None:
        raise ValueError("unknown incident")
    expected = _ACTIONS.get(action)
    if action == "report_resolved" and (payload.get("confirmed_dark") or _has_confirmed_dark(payload) or _incident_is_dark(session, incident)):
        return _record(session, incident, False, "confirmed_dark_remains", "resolution_rejected", actor, payload)
    if expected is None or incident.status != expected[0]:
        return _record(session, incident, False, "invalid_transition", f"{action}_rejected", actor, payload)
    before, after = expected
    incident.status = after
    return _record(session, incident, True, "ok", action, actor, payload, before, after)


def _has_confirmed_dark(payload: dict) -> bool:
    return bool(payload.get("dark_evidence_ids"))


def _incident_is_dark(session: Session, incident: Incident) -> bool:
    return incident.pole_id is not None and session.scalar(
        select(PoleEvidenceState.id).where(
            PoleEvidenceState.pole_id == incident.pole_id,
            PoleEvidenceState.evidence_class == "confirmed_dark",
        )
    ) is not None


def _record(session: Session, incident: Incident, accepted: bool, code: str, event_type: str, actor: str, payload: dict, before=None, after=None) -> TransitionResult:
    event = _event(session, incident, event_type, actor, payload.get("reason", code), payload.get("evidence_ids", []), before, after)
    return TransitionResult(accepted, code, incident, event)


def _event(session: Session, incident: Incident, event_type: str, actor: str, reason: str, evidence_ids: list, before: str | None, after: str | None) -> TicketEvent:
    event = TicketEvent(
        incident_id=incident.id, event_type=event_type, from_status=before, to_status=after,
        actor=actor, reason=reason, evidence_ids=[str(value) for value in evidence_ids], occurred_at=datetime.now(UTC),
    )
    session.add(event)
    session.flush()
    return event
