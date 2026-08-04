from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models.assets import Pole, TopologyEdge, Transformer
from app.db.models.incidents import AIExplanation, Incident, IncidentBoundary, IncidentEvidence, PlannedOperation, TicketEvent
from app.db.models.telemetry import TelemetryEvent


def list_incidents(session: Session, page: int, page_size: int, **filters) -> tuple[list[dict], int]:
    statement = select(Incident)
    for name in ("status", "fault_class", "confidence", "feeder_id", "transformer_id"):
        if value := filters.get(name):
            statement = statement.where(getattr(Incident, name) == value)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = list(session.scalars(statement.order_by(
        case((Incident.status == "detected", 0), else_=1), Incident.affected_count.desc(), Incident.updated_at.desc()
    ).offset((page - 1) * page_size).limit(page_size)))
    topology = _topologies(session, [row.transformer_id for row in rows])
    return [_summary(incident, topology.get(incident.transformer_id)) for incident in rows], total


def incident_detail(session: Session, incident_id: UUID, evidence_page: int = 1, evidence_page_size: int = 50) -> dict | None:
    incident = session.get(Incident, incident_id)
    if incident is None:
        return None
    boundary_rows = list(session.scalars(select(IncidentBoundary).where(
        IncidentBoundary.incident_id == incident.id
    ).order_by(IncidentBoundary.created_at)))
    boundary = _boundary(boundary_rows[-1] if boundary_rows else None)
    evidence_counts = dict(session.execute(select(IncidentEvidence.evidence_class, func.count()).where(
        IncidentEvidence.incident_id == incident.id
    ).group_by(IncidentEvidence.evidence_class)).all())
    evidence_total = sum(evidence_counts.values())
    evidence = list(session.execute(select(IncidentEvidence, TelemetryEvent.event_type).outerjoin(
        TelemetryEvent, TelemetryEvent.id == IncidentEvidence.telemetry_event_id
    ).where(IncidentEvidence.incident_id == incident.id).order_by(IncidentEvidence.created_at).offset(
        (evidence_page - 1) * evidence_page_size
    ).limit(evidence_page_size)))
    events = list(session.scalars(select(TicketEvent).where(TicketEvent.incident_id == incident.id).order_by(TicketEvent.occurred_at)))
    operation = session.scalar(select(PlannedOperation).where(PlannedOperation.incident_id == incident.id))
    explanation = session.scalar(select(AIExplanation).where(AIExplanation.incident_id == incident.id).order_by(AIExplanation.created_at.desc()))
    topology = _topologies(session, [incident.transformer_id]).get(incident.transformer_id, _empty_topology())
    return {
        **_summary(incident, topology),
        "boundary": boundary,
        "location_history": [_boundary(row) for row in boundary_rows],
        "evidence": {"class_counts": evidence_counts, "items": [_evidence(row, event_type) for row, event_type in evidence], "page": evidence_page, "page_size": evidence_page_size, "total": evidence_total},
        "schedule_overlap": _operation(operation) if operation else None,
        "topology": topology,
        "ticket_events": [_ticket(event) for event in events],
        "ai_explanation": None if explanation is None else {
            "status": "fallback" if explanation.fallback_reason else "generated",
            "text": explanation.validated_text, "fallback_reason": explanation.fallback_reason,
        },
    }


def _summary(incident: Incident, topology: dict | None = None) -> dict:
    topology = topology or _empty_topology()
    return {
        "id": str(incident.id), "fault_class": incident.fault_class, "status": incident.status,
        "location_class": incident.location_class, "affected_count": incident.affected_count,
        "affected_count_estimated": topology["source"] == "inferred",
        "confidence": {"level": incident.confidence, "reasons": incident.confidence_reasons},
        "navigation": {"latitude": incident.navigation_latitude, "longitude": incident.navigation_longitude},
        "pin": {"value": incident.pin_code, "source": incident.pin_source},
        "feeder_id": _uuid(incident.feeder_id), "transformer_id": _uuid(incident.transformer_id),
        "pole_id": _uuid(incident.pole_id), "updated_at": incident.updated_at,
    }


def _latest_boundary(session: Session, incident_id: UUID) -> IncidentBoundary | None:
    return session.scalar(select(IncidentBoundary).where(IncidentBoundary.incident_id == incident_id).order_by(IncidentBoundary.created_at.desc()))


def _boundary(row: IncidentBoundary | None) -> dict:
    if row is None:
        return {"kind": "transformer", "upstream_pole_id": None, "downstream_pole_id": None, "candidate_spans": [], "geometry": {}}
    return {
        "kind": "transformer" if row.boundary_type == "dt" else row.boundary_type,
        "upstream_pole_id": _uuid(row.upstream_pole_id), "downstream_pole_id": _uuid(row.downstream_pole_id),
        "candidate_spans": row.candidate_spans, "geometry": row.geometry,
    }


def _topologies(session: Session, transformer_ids: list[UUID | None]) -> dict[UUID, dict]:
    ids = [item for item in transformer_ids if item is not None]
    if not ids:
        return {}
    rows = session.execute(select(
        TopologyEdge.transformer_id,
        func.bool_or(TopologyEdge.source == "inferred"),
        func.min(TopologyEdge.calibration_bucket),
    ).where(TopologyEdge.transformer_id.in_(ids), TopologyEdge.is_visible.is_(True)).group_by(TopologyEdge.transformer_id))
    return {transformer_id: {"source": "inferred" if inferred else "registry", "calibration_bucket": bucket} for transformer_id, inferred, bucket in rows}


def _empty_topology() -> dict:
    return {"source": "registry", "calibration_bucket": None}


def _evidence(row: IncidentEvidence, event_type: str | None) -> dict:
    return {"id": str(row.id), "class": row.evidence_class, "event_id": str(row.telemetry_event_id), "event_type": event_type, "details": row.evidence}


def _ticket(row: TicketEvent) -> dict:
    return {"id": str(row.id), "type": row.event_type, "from_status": row.from_status, "to_status": row.to_status, "actor": row.actor, "reason": row.reason, "evidence_ids": row.evidence_ids, "occurred_at": row.occurred_at}


def _operation(row: PlannedOperation) -> dict:
    return {"id": str(row.id), "status": row.status, "observed_start": row.observed_start, "observed_end": row.observed_end, "promotion_outcome": row.promotion_outcome}


def _uuid(value: UUID | None) -> str | None:
    return str(value) if value else None


def incident_feature_collection(session: Session, incident_id: UUID) -> dict | None:
    incident = session.get(Incident, incident_id)
    if incident is None:
        return None
    boundary = _latest_boundary(session, incident_id)
    kind = "feeder" if incident.location_class == "feeder" else _boundary(boundary)["kind"]
    if kind == "transformer" and incident.transformer_id:
        return _asset_collection(session, incident, select(Transformer).where(Transformer.id == incident.transformer_id))
    if kind == "feeder" and incident.feeder_id:
        return _asset_collection(session, incident, select(Transformer).where(Transformer.feeder_id == incident.feeder_id))
    ids = (boundary.geometry.get("pole_path", []) if boundary else [])
    poles = {str(pole.id): pole for pole in session.scalars(select(Pole).where(Pole.id.in_(ids))) if ids}
    coordinates = [[poles[item].longitude, poles[item].latitude] for item in ids if item in poles]
    if not coordinates and incident.pole_id:
        pole = session.get(Pole, incident.pole_id)
        coordinates = [[pole.longitude, pole.latitude]] if pole else []
    geometry = {"type": "LineString", "coordinates": coordinates} if len(coordinates) > 1 else {
        "type": "Point", "coordinates": coordinates[0] if coordinates else [incident.navigation_longitude, incident.navigation_latitude]
    }
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"incident_id": str(incident.id), "boundary": kind}, "geometry": geometry}]}


def _asset_collection(session: Session, incident: Incident, transformer_statement) -> dict:
    transformers = list(session.scalars(transformer_statement))
    poles = list(session.scalars(select(Pole).where(Pole.transformer_id.in_([row.id for row in transformers]))))
    features = [
        _asset_feature(incident, "transformer", row.id, row.code, row.latitude, row.longitude)
        for row in transformers
    ] + [
        _asset_feature(incident, "pole", row.id, row.code, row.latitude, row.longitude)
        for row in poles
    ]
    return {"type": "FeatureCollection", "features": features}


def _asset_feature(incident: Incident, asset: str, asset_id: UUID, code: str, latitude: float, longitude: float) -> dict:
    return {"type": "Feature", "properties": {"incident_id": str(incident.id), "asset": asset, "id": str(asset_id), "code": code}, "geometry": {"type": "Point", "coordinates": [longitude, latitude]}}
