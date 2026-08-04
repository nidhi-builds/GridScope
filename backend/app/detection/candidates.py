from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.db.models.assets import Pole, TopologyEdge
from app.db.models.telemetry import DetectionCandidate, PoleEvidenceState, TelemetryEvent
from app.topology.graph import NetworkGraph


SETTLE_WINDOW = timedelta(seconds=30)
HARD_DEADLINE = timedelta(seconds=45)
CANDIDATE_TIMEOUT = timedelta(seconds=120)


@dataclass(frozen=True)
class CandidateOutcome:
    candidate_state: str
    classification: str | None = None
    actionable: bool = False
    defeated_reason: str | None = None
    incidents: list = None

    def __post_init__(self):
        if self.incidents is None:
            object.__setattr__(self, "incidents", [])


def evaluate_events(events: list[Any], graph: NetworkGraph, now: datetime) -> CandidateOutcome:
    """Evaluate a DT's received evidence without creating an incident."""
    dark = [event for event in events if _is_dark(event)]
    if not dark:
        return CandidateOutcome("investigating", defeated_reason="no_direct_dark")
    first = min(_value(event, "received_at") for event in dark)
    if any(_value(event, "processing_state") == "quarantined" for event in events):
        return CandidateOutcome("defeated", defeated_reason="assignment_quarantine")
    if any(_value(event, "epoch_decision") == "outside_realtime_window" for event in events):
        return CandidateOutcome("defeated", defeated_reason="stale_evidence")
    if now < first + SETTLE_WINDOW:
        return CandidateOutcome("investigating")
    in_window = [event for event in dark if _value(event, "received_at") <= first + HARD_DEADLINE]
    if _has_live_child(in_window, events, graph, first, now):
        return CandidateOutcome("device_health", "device_issue", defeated_reason="fresh_live_child")
    if _has_live_parent(in_window, events, graph, first, now):
        return CandidateOutcome("actionable", actionable=True)
    if _has_consistent_pair(in_window, graph):
        return CandidateOutcome("actionable", actionable=True)
    if now >= first + CANDIDATE_TIMEOUT:
        return CandidateOutcome("device_health", "device_issue", defeated_reason="isolated_sensor_behavior")
    return CandidateOutcome("investigating")


def attach_candidate(session: Session, event: TelemetryEvent) -> DetectionCandidate | None:
    """Attach current evidence to the active DT candidate, opening only for dark."""
    pole = session.get(Pole, event.pole_id)
    candidate = session.scalar(
        select(DetectionCandidate)
        .where(
            DetectionCandidate.transformer_id == pole.transformer_id,
            DetectionCandidate.status.in_(("investigating", "actionable")),
        )
        .order_by(DetectionCandidate.first_received_at)
        .with_for_update()
    )
    if candidate is None:
        if not _is_dark(event):
            return None
        candidate = DetectionCandidate(
            transformer_id=pole.transformer_id,
            scope_key=f"dt:{pole.transformer_id}",
            first_received_at=event.received_at,
            expires_at=event.received_at + CANDIDATE_TIMEOUT,
            evidence_event_ids=[str(event.id)],
        )
        session.add(candidate)
    elif str(event.id) not in candidate.evidence_event_ids:
        candidate.evidence_event_ids = [*candidate.evidence_event_ids, str(event.id)]
    return candidate


def evaluate_candidate(candidate_id: UUID, now: datetime, session: Session | None = None) -> CandidateOutcome:
    """Persist the Tier-1 outcome; callers may pass their transaction session."""
    owns_session = session is None
    session = session or SessionLocal()
    try:
        candidate = session.get(DetectionCandidate, candidate_id)
        if candidate is None:
            raise ValueError("unknown candidate")
        event_ids = [UUID(value) for value in candidate.evidence_event_ids]
        events = list(session.scalars(select(TelemetryEvent).where(TelemetryEvent.id.in_(event_ids))))
        graph = _graph_for(session, candidate.transformer_id)
        outcome = evaluate_events(events, graph, now)
        candidate.status = outcome.candidate_state
        candidate.promotion_outcome = outcome.defeated_reason or ("actionable" if outcome.actionable else None)
        if outcome.classification == "device_issue":
            _mark_device_suspect(session, events)
        return outcome
    finally:
        if owns_session:
            session.close()


def evaluate_open_candidates(session: Session, now: datetime) -> None:
    for candidate_id in session.scalars(
        select(DetectionCandidate.id).where(DetectionCandidate.status.in_(("investigating", "actionable")))
    ):
        evaluate_candidate(candidate_id, now, session)


def _graph_for(session: Session, transformer_id: UUID) -> NetworkGraph:
    edges = session.execute(
        select(TopologyEdge.parent_pole_id, TopologyEdge.child_pole_id).where(
            TopologyEdge.transformer_id == transformer_id,
            TopologyEdge.is_visible.is_(True),
        )
    ).all()
    return NetworkGraph(transformer_id, edges)


def _has_consistent_pair(events: list[Any], graph: NetworkGraph) -> bool:
    return any(
        graph.path(_value(left, "pole_id"), _value(right, "pole_id"))
        or graph.path(_value(right, "pole_id"), _value(left, "pole_id"))
        for index, left in enumerate(events)
        for right in events[index + 1:]
    )


def _has_live_parent(dark: list[Any], events: list[Any], graph: NetworkGraph, first: datetime, now: datetime) -> bool:
    live = _live_events(events, first, now)
    return any(
        _value(candidate, "pole_id") in set(graph.graph.predecessors(_value(event, "pole_id")))
        for event in dark
        for candidate in live
    )


def _has_live_child(dark: list[Any], events: list[Any], graph: NetworkGraph, first: datetime, now: datetime) -> bool:
    live = _live_events(events, first, now)
    return any(
        _value(candidate, "pole_id") in set(graph.graph.successors(_value(event, "pole_id")))
        for event in dark
        for candidate in live
    )


def _live_events(events: list[Any], first: datetime, now: datetime) -> list[Any]:
    deadline = min(now, first + HARD_DEADLINE)
    return [
        event for event in events
        if _value(event, "event_type") in {"heartbeat", "boot", "power_restored"}
        and _value(event, "energized") is True
        and first <= _value(event, "received_at") <= deadline
    ]


def _is_dark(event: Any) -> bool:
    return _value(event, "event_type") == "power_lost" and _value(event, "energized") is False


def _mark_device_suspect(session: Session, events: list[TelemetryEvent]) -> None:
    for event in events:
        if not _is_dark(event):
            continue
        evidence = session.scalar(
            select(PoleEvidenceState)
            .where(PoleEvidenceState.pole_id == event.pole_id, PoleEvidenceState.source_event_id == event.id)
            .with_for_update()
        )
        if evidence is None:
            continue
        evidence.evidence = {
            **evidence.evidence,
            "prior_evidence_class": evidence.evidence_class,
            "source_event_id": str(evidence.source_event_id),
        }
        evidence.evidence_class = "device_suspect"
        evidence.device_health = "device_issue"


def _value(event: Any, name: str) -> Any:
    value = getattr(event, name, None)
    if value is not None:
        return value
    payload = getattr(event, "payload", {})
    return payload.get(name) if isinstance(payload, dict) else None
