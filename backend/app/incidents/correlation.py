from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.assets import Pole
from app.db.models.incidents import Incident, IncidentBoundary, IncidentEvidence, TicketEvent
from app.db.models.telemetry import TelemetryEvent
from app.ai.service import queue_explanation


@dataclass(frozen=True)
class IncidentHypothesis:
    fault_class: str
    location_class: str
    transformer_id: UUID | None
    downstream_pole_id: UUID | None
    pin_code: str
    pin_source: str
    affected_count: int
    confidence: str
    navigation_latitude: float
    navigation_longitude: float
    feeder_id: UUID | None = None
    pole_id: UUID | None = None
    upstream_pole_id: UUID | None = None
    confidence_reasons: list[str] = field(default_factory=list)
    evidence_ids: list[UUID] = field(default_factory=list)
    candidate_spans: list = field(default_factory=list)
    geometry: dict = field(default_factory=dict)
    simulation_id: UUID | None = None

    @property
    def correlation_key(self) -> str:
        key = f"{self.fault_class}:{self.transformer_id or self.feeder_id}:{self.downstream_pole_id or self.pole_id}"
        return f"sim:{self.simulation_id}:{key}" if self.simulation_id else key


def upsert_incident(session: Session, hypothesis: IncidentHypothesis) -> Incident:
    """Create one active incident per fault boundary; evidence/history only append."""
    incident = session.scalar(
        select(Incident).where(Incident.correlation_key == hypothesis.correlation_key, Incident.status != "closed").with_for_update()
    )
    opened = incident is None
    predecessor = None
    material_change = False
    if opened:
        predecessor = session.scalar(
            select(Incident).where(Incident.correlation_key == hypothesis.correlation_key, Incident.status == "closed")
            .order_by(Incident.updated_at.desc())
        )
        incident = Incident(
            correlation_key=hypothesis.correlation_key, fault_class=hypothesis.fault_class,
            location_class=hypothesis.location_class, feeder_id=hypothesis.feeder_id,
            transformer_id=hypothesis.transformer_id, pole_id=hypothesis.pole_id,
            pin_code=hypothesis.pin_code, pin_source=hypothesis.pin_source,
            affected_count=hypothesis.affected_count, confidence=hypothesis.confidence,
            confidence_reasons=hypothesis.confidence_reasons,
            navigation_latitude=hypothesis.navigation_latitude, navigation_longitude=hypothesis.navigation_longitude,
            simulation_id=hypothesis.simulation_id,
        )
        session.add(incident)
        session.flush()
    else:
        material_change = (incident.location_class, incident.confidence) != (hypothesis.location_class, hypothesis.confidence)
        incident.location_class = hypothesis.location_class
        incident.affected_count = hypothesis.affected_count
        incident.confidence = hypothesis.confidence
        incident.confidence_reasons = hypothesis.confidence_reasons
        incident.navigation_latitude = hypothesis.navigation_latitude
        incident.navigation_longitude = hypothesis.navigation_longitude
    _append_boundary(session, incident, hypothesis)
    _append_evidence(session, incident, hypothesis)
    if opened and predecessor:
        _audit(session, incident, "relapse_of", f"relapse_of:{predecessor.id}")
        _audit(session, predecessor, "relapse_detected", f"relapse_detected:{incident.id}")
    if opened and hypothesis.fault_class == "feeder":
        _roll_up(session, incident)
    if opened or material_change:
        queue_explanation(session, incident)
    return incident


def _append_boundary(session: Session, incident: Incident, hypothesis: IncidentHypothesis) -> None:
    latest = session.scalar(
        select(IncidentBoundary).where(IncidentBoundary.incident_id == incident.id).order_by(IncidentBoundary.created_at.desc())
    )
    current = (hypothesis.location_class, hypothesis.upstream_pole_id, hypothesis.downstream_pole_id)
    if latest and (latest.boundary_type, latest.upstream_pole_id, latest.downstream_pole_id) == current:
        return
    session.add(IncidentBoundary(
        incident_id=incident.id, boundary_type=hypothesis.location_class,
        upstream_pole_id=hypothesis.upstream_pole_id, downstream_pole_id=hypothesis.downstream_pole_id,
        candidate_spans=hypothesis.candidate_spans, geometry=hypothesis.geometry,
    ))
    if latest and latest.boundary_type == "corridor" and hypothesis.location_class == "span":
        _audit(session, incident, "location_refined", "corridor_to_span")


def _append_evidence(session: Session, incident: Incident, hypothesis: IncidentHypothesis) -> None:
    existing = set(session.scalars(select(IncidentEvidence.telemetry_event_id).where(IncidentEvidence.incident_id == incident.id)))
    for event_id in hypothesis.evidence_ids:
        if event_id not in existing:
            event = session.get(TelemetryEvent, event_id)
            pole = session.get(Pole, event.pole_id) if event and event.pole_id else None
            dark = event and event.event_type == "power_lost" and event.payload.get("energized") is False
            session.add(IncidentEvidence(
                incident_id=incident.id, telemetry_event_id=event_id,
                evidence_class="prior_dark" if dark else "candidate",
                evidence={"pole_id": str(event.pole_id), "branch_index": pole.branch_index} if dark and pole else {},
            ))


def _roll_up(session: Session, feeder: Incident) -> None:
    for incident in session.scalars(
        select(Incident).where(
            Incident.id != feeder.id, Incident.fault_class != "feeder", Incident.feeder_id == feeder.feeder_id,
            Incident.status != "closed", Incident.simulation_id == feeder.simulation_id,
        )
    ):
        previous_status = incident.status
        if feeder.simulation_id and incident.simulation_id == feeder.simulation_id:
            incident.status = "closed"
        _audit(session, incident, "superseded_by_feeder", f"superseded_by:{feeder.id}", previous_status, incident.status)
        _audit(session, feeder, "rolls_up_dt", f"rolls_up:{incident.id}")


def _audit(
    session: Session, incident: Incident, action: str, reason: str, from_status: str | None = None, to_status: str | None = None,
) -> None:
    session.add(TicketEvent(
        incident_id=incident.id, event_type=action, from_status=from_status or incident.status, to_status=to_status or incident.status,
        actor="system", reason=reason, evidence_ids=[], occurred_at=datetime.now(UTC),
    ))
