from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.assets import Pole, TopologyEdge
from app.db.models.incidents import Incident, IncidentEvidence, TicketEvent
from app.db.models.telemetry import PoleEvidenceState, TelemetryEvent


STABILITY = timedelta(seconds=30)


@dataclass(frozen=True)
class RestorationResult:
    verified: bool
    code: str
    incident: Incident


def evaluate_restoration(session: Session, incident_id: UUID, now: datetime, events: list[Any] | None = None) -> RestorationResult:
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise ValueError("unknown incident")
    if incident.status != "resolved":
        return RestorationResult(False, "not_resolved", incident)
    events = _current_events(session, incident, now) if events is None else events
    if _scope_is_dark(session, incident, now) or any(
        _value(event, "event_type") == "power_lost" and not _value(event, "energized") for event in events
    ):
        return RestorationResult(False, "fresh_dark_contradiction", incident)
    live = [event for event in events if _value(event, "event_type") in {"boot", "power_restored"} and _value(event, "energized") is True]
    if not live:
        return RestorationResult(False, "restoration_evidence_missing", incident)
    live_poles = {_value(event, "pole_id") for event in live}
    degraded = False
    proofs = []
    if incident.pole_id is not None and incident.pole_id not in live_poles:
        if _unavailable(session, incident.pole_id):
            degraded = True
        else:
            return RestorationResult(False, "boundary_restoration_missing", incident)
    elif incident.pole_id is not None:
        proofs.extend(_value(event, "received_at") for event in live if _value(event, "pole_id") == incident.pole_id)
    for branch_poles in _prior_dark_branches(session, incident).values():
        branch_reports = [event for event in live if _value(event, "pole_id") in branch_poles]
        if not branch_reports:
            return RestorationResult(False, "branch_restoration_missing", incident)
        proofs.extend(_value(event, "received_at") for event in branch_reports)
    final_proof = max(proofs or [_value(event, "received_at") for event in live])
    if _fresh_dark_after(session, incident, final_proof, now):
        return RestorationResult(False, "fresh_dark_contradiction", incident)
    if now < final_proof + STABILITY:
        return RestorationResult(False, "stability_pending", incident)
    evidence_ids = [str(value) for value in (_value(event, "id") for event in live) if value]
    if degraded:
        incident.confidence = "low"
        incident.confidence_reasons = [*incident.confidence_reasons, "restoration-reporter-unavailable"]
    _complete_restoration(session, incident, evidence_ids)
    return RestorationResult(True, "verified", incident)


def evaluate_open_restorations(session: Session, now: datetime) -> None:
    for incident_id in session.scalars(select(Incident.id).where(Incident.status == "resolved")):
        evaluate_restoration(session, incident_id, now)


def _current_events(session: Session, incident: Incident, now: datetime) -> list[TelemetryEvent]:
    scope = _scope_poles(session, incident)
    if not scope:
        return []
    states = session.scalars(
        select(PoleEvidenceState).where(
            PoleEvidenceState.pole_id.in_(scope),
            PoleEvidenceState.source_event_id.is_not(None),
            (PoleEvidenceState.fresh_until.is_(None) | (PoleEvidenceState.fresh_until >= now)),
        )
    ) if incident.transformer_id else []
    return [event for state in states if (event := session.get(TelemetryEvent, state.source_event_id))]


def _scope_is_dark(session: Session, incident: Incident, now: datetime) -> bool:
    scope = _scope_poles(session, incident)
    if not scope:
        return False
    return session.scalar(
        select(PoleEvidenceState.id).join(TelemetryEvent, TelemetryEvent.id == PoleEvidenceState.source_event_id).where(
            PoleEvidenceState.pole_id.in_(scope),
            PoleEvidenceState.evidence_class == "confirmed_dark",
            TelemetryEvent.processing_state == "processed",
            TelemetryEvent.event_type == "power_lost",
            TelemetryEvent.payload["energized"].as_boolean().is_(False),
            (PoleEvidenceState.fresh_until.is_(None) | (PoleEvidenceState.fresh_until >= now)),
        )
    ) is not None


def _prior_dark_branches(session: Session, incident: Incident) -> dict[int, set[UUID]]:
    branches: dict[int, set[UUID]] = {}
    for evidence, event, pole in session.execute(
        select(IncidentEvidence, TelemetryEvent, Pole)
        .join(TelemetryEvent, TelemetryEvent.id == IncidentEvidence.telemetry_event_id)
        .join(Pole, Pole.id == TelemetryEvent.pole_id)
        .where(IncidentEvidence.incident_id == incident.id, TelemetryEvent.event_type == "power_lost")
    ):
        if _value(event, "energized") is False:
            branches.setdefault(pole.branch_index, set()).add(pole.id)
    return branches


def _unavailable(session: Session, pole_id: UUID) -> bool:
    state = session.scalar(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == pole_id))
    return state is not None and state.evidence_class in {"unknown_silent", "uninstrumented", "device_suspect"}


def _scope_poles(session: Session, incident: Incident) -> set[UUID]:
    scope = {incident.pole_id} if incident.pole_id else set()
    branches = _prior_dark_branches(session, incident)
    scope.update(pole_id for poles in branches.values() for pole_id in poles)
    if incident.transformer_id and branches:
        scope.update(session.scalars(select(Pole.id).where(
            Pole.transformer_id == incident.transformer_id, Pole.branch_index.in_(branches),
        )))
    if incident.transformer_id and incident.pole_id:
        children: dict[UUID, list[UUID]] = {}
        for parent, child in session.execute(select(TopologyEdge.parent_pole_id, TopologyEdge.child_pole_id).where(
            TopologyEdge.transformer_id == incident.transformer_id, TopologyEdge.is_visible.is_(True),
        )):
            children.setdefault(parent, []).append(child)
        pending = [incident.pole_id]
        while pending:
            pending = [child for parent in pending for child in children.get(parent, []) if child not in scope]
            scope.update(pending)
    return scope


def _fresh_dark_after(session: Session, incident: Incident, since: datetime, now: datetime) -> bool:
    scope = _scope_poles(session, incident)
    return bool(scope and session.scalar(select(PoleEvidenceState.id).join(
        TelemetryEvent, TelemetryEvent.id == PoleEvidenceState.source_event_id,
    ).where(
        PoleEvidenceState.pole_id.in_(scope), PoleEvidenceState.evidence_class == "confirmed_dark",
        TelemetryEvent.processing_state == "processed", TelemetryEvent.event_type == "power_lost",
        TelemetryEvent.received_at >= since, TelemetryEvent.received_at <= now,
        TelemetryEvent.payload["energized"].as_boolean().is_(False),
    )) is not None)


def _complete_restoration(session: Session, incident: Incident, evidence_ids: list[str]) -> None:
    for status, action, reason in (("verified", "verified", "fresh_restoration"), ("closed", "closed", "restoration_stable")):
        before = incident.status
        incident.status = status
        session.add(TicketEvent(
            incident_id=incident.id, event_type=action, from_status=before, to_status=status,
            actor="system", reason=reason, evidence_ids=evidence_ids, occurred_at=datetime.now(UTC),
        ))


def _value(value: Any, name: str):
    if isinstance(value, dict):
        return value.get(name)
    direct = getattr(value, name, None)
    return direct if direct is not None else getattr(value, "payload", {}).get(name)
