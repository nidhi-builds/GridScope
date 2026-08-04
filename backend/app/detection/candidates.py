from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.db.models.assets import Pole, TopologyEdge, Transformer
from app.db.models.incidents import PlannedOperation, ScheduledOutage
from app.db.models.telemetry import DetectionCandidate, PoleEvidenceState, TelemetryEvent
from app.detection.classification import classify
from app.detection.localization import BoundaryResult, localize
from app.detection.schedules import ScheduleDecision, match_schedule
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
    boundaries: list[BoundaryResult] = None
    schedule_decision: ScheduleDecision | None = None

    def __post_init__(self):
        if self.incidents is None:
            object.__setattr__(self, "incidents", [])
        if self.boundaries is None:
            object.__setattr__(self, "boundaries", [])


def evaluate_events(
    events: list[Any], graph: NetworkGraph, now: datetime, coverage: Any = None, schedules: Any = ()
) -> CandidateOutcome:
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
    if _has_live_parent(in_window, events, graph, first, now) or _has_consistent_pair(in_window, graph) or _has_independent_branches(in_window, graph):
        boundaries = _boundaries(in_window, events, graph, first, now)
        classification = classify(boundaries, coverage or _coverage_for(events, graph, first, now))
        decision = match_schedule(classification, schedules, now)
        if decision.status == "planned":
            return CandidateOutcome("planned_operation", "planned_outage", defeated_reason="scheduled_match", boundaries=boundaries, schedule_decision=decision)
        return CandidateOutcome("actionable", classification.kind, True, boundaries=boundaries, schedule_decision=decision)
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


def evaluate_candidate(
    candidate_id: UUID, now: datetime, session: Session | None = None, schedules: Any | None = None
) -> CandidateOutcome:
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
        schedule_snapshot = schedules if schedules is not None else list(session.scalars(select(ScheduledOutage)))
        coverage = _coverage_for(events, graph, candidate.first_received_at, now)
        base = evaluate_events(events, graph, now, coverage=coverage)
        if base.classification == "dt":
            coverage.update(_feeder_coverage(session, candidate.transformer_id, candidate.first_received_at))
        outcome = evaluate_events(events, graph, now, coverage=coverage, schedules=schedule_snapshot)
        candidate.status = outcome.candidate_state
        candidate.promotion_outcome = outcome.defeated_reason or (outcome.classification if outcome.actionable else None)
        if outcome.schedule_decision and outcome.schedule_decision.status == "planned":
            session.add(PlannedOperation(
                scheduled_outage_id=outcome.schedule_decision.schedule_id,
                status="matched_stale" if outcome.schedule_decision.confidence_reduced else "matched",
                observed_start=now,
                matched_evidence=[str(event.id) for event in events],
            ))
        if outcome.classification == "device_issue":
            _mark_device_suspect(session, events)
        return outcome
    finally:
        if owns_session:
            session.close()


def evaluate_open_candidates(session: Session, now: datetime, schedules: Any | None = None) -> None:
    for candidate_id in session.scalars(
        select(DetectionCandidate.id).where(DetectionCandidate.status.in_(("investigating", "actionable")))
    ):
        evaluate_candidate(candidate_id, now, session, schedules)


def _graph_for(session: Session, transformer_id: UUID) -> NetworkGraph:
    rows = session.execute(
        select(TopologyEdge.parent_pole_id, TopologyEdge.child_pole_id, TopologyEdge.source, TopologyEdge.calibration_bucket).where(
            TopologyEdge.transformer_id == transformer_id,
            TopologyEdge.is_visible.is_(True),
        )
    ).all()
    edge_pairs = [(row.parent_pole_id, row.child_pole_id) for row in rows]
    children = {child for _, child in edge_pairs}
    graph = NetworkGraph(transformer_id, [(transformer_id, parent) for parent, _ in edge_pairs if parent not in children] + edge_pairs)
    graph.topology_source = "inferred" if any(row.source == "inferred" for row in rows) else ("registry" if rows else "unknown")
    # Task 3 stores ambiguity buckets on edges, not a measured calibration report;
    # remain conservative until a >=90% precision result is supplied to the graph.
    graph.calibration_precision = 0.0
    return graph


def _has_consistent_pair(events: list[Any], graph: NetworkGraph) -> bool:
    return any(
        graph.path(_value(left, "pole_id"), _value(right, "pole_id"))
        or graph.path(_value(right, "pole_id"), _value(left, "pole_id"))
        for index, left in enumerate(events)
        for right in events[index + 1:]
    )


def _has_independent_branches(events: list[Any], graph: NetworkGraph) -> bool:
    branches = {
        path[1] for event in events
        if len(path := graph.path(graph.root_id, _value(event, "pole_id"))) > 1
    }
    return len(branches) >= 2


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


def _boundaries(dark: list[Any], events: list[Any], graph: NetworkGraph, first: datetime, now: datetime) -> list[BoundaryResult]:
    return localize(
        graph,
        {
            "dark": {_value(event, "pole_id") for event in dark},
            "live": {_value(event, "pole_id") for event in _live_events(events, first, now)},
            "topology_source": getattr(graph, "topology_source", "registry"),
            "calibration_precision": getattr(graph, "calibration_precision", 0.0),
        },
    )


def _coverage_for(events: list[Any], graph: NetworkGraph, first: datetime, now: datetime) -> dict[str, dict]:
    """Use directly observed first-level branches; silence never manufactures coverage."""
    dark = set()
    observable = set()
    live = set()
    deadline = min(now, first + HARD_DEADLINE)
    for event in events:
        if not (first <= _value(event, "received_at") <= deadline):
            continue
        path = graph.path(graph.root_id, _value(event, "pole_id"))
        if len(path) < 2:
            continue
        branch = path[1]
        observable.add(branch)
        if _is_dark(event):
            dark.add(branch)
        elif _value(event, "energized") is True:
            live.add(branch)
    return {"dt_branches": {graph.root_id: {"dark": dark, "observable": observable, "live": live}}}


def _feeder_coverage(session: Session, transformer_id: UUID, first_received_at: datetime) -> dict[str, dict]:
    feeder_id = session.scalar(select(Transformer.feeder_id).where(Transformer.id == transformer_id))
    transformer_ids = set(session.scalars(select(Transformer.id).where(Transformer.feeder_id == feeder_id)))
    qualifying = set(session.scalars(
        select(DetectionCandidate.transformer_id).where(
            DetectionCandidate.transformer_id.in_(transformer_ids),
            DetectionCandidate.status == "actionable",
            DetectionCandidate.promotion_outcome == "dt",
            DetectionCandidate.first_received_at >= first_received_at,
            DetectionCandidate.first_received_at <= first_received_at + HARD_DEADLINE,
        )
    ))
    qualifying.add(transformer_id)
    return {"feeder_dts": {feeder_id: {"qualifying": qualifying, "total": len(transformer_ids)}}}


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
