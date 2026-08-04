from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import Explanation, IncidentExplanationFacts
from app.db.models.incidents import Incident, IncidentBoundary


def facts_from_incident(session: Session, incident: Incident) -> IncidentExplanationFacts:
    boundary = session.scalar(select(IncidentBoundary).where(
        IncidentBoundary.incident_id == incident.id
    ).order_by(IncidentBoundary.created_at.desc()))
    asset_ids = tuple(sorted(str(value) for value in (incident.feeder_id, incident.transformer_id, incident.pole_id) if value))
    boundary_ids = tuple(dict.fromkeys(str(value) for value in (
        boundary.upstream_pole_id if boundary else None, boundary.downstream_pole_id if boundary else None,
    ) if value))
    reasons = tuple(str(reason) for reason in incident.confidence_reasons)
    return IncidentExplanationFacts(
        incident_id=str(incident.id), fault_class=incident.fault_class, location_class=incident.location_class,
        affected_count=incident.affected_count, confidence=incident.confidence, status=incident.status,
        asset_ids=asset_ids, boundary_ids=boundary_ids, confidence_reasons=reasons,
        unknowns=tuple(reason for reason in reasons if "unknown" in reason or "silent" in reason),
        navigation=(incident.navigation_latitude, incident.navigation_longitude), pin_code=incident.pin_code,
    )


def render_fallback(facts: IncidentExplanationFacts) -> Explanation:
    location = facts.location_class.replace("_", " ")
    english = (
        f"{facts.fault_class.title()} incident at {location}; {facts.affected_count} affected pole(s). "
        f"Confidence is {facts.confidence}; ticket status is {facts.status}."
    )
    kannada = (
        f"{location} ನಲ್ಲಿ {facts.fault_class} ಘಟನೆ; {facts.affected_count} ಕಂಬ(ಗಳು) ಪರಿಣಾಮಗೊಂಡಿವೆ. "
        f"ವಿಶ್ವಾಸ ಮಟ್ಟ {facts.confidence}; ಟಿಕೆಟ್ ಸ್ಥಿತಿ {facts.status}."
    )
    return Explanation(english, kannada)
