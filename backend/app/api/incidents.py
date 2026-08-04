from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.schemas import AssignTicket, ErrorResponse, Page, TicketAction, TicketActionResponse
from app.db import get_session
from app.incidents.workflow import transition_ticket
from app.queries.incidents import incident_detail, list_incidents


router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("", response_model=Page)
def incidents(
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), status: str | None = None,
    fault_class: str | None = None, confidence: str | None = None, feeder_id: UUID | None = None,
    transformer_id: UUID | None = None, session: Session = Depends(get_session),
) -> Page:
    items, total = list_incidents(session, page, page_size, status=status, fault_class=fault_class, confidence=confidence, feeder_id=feeder_id, transformer_id=transformer_id)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/{incident_id}")
def incident(
    incident_id: UUID, evidence_page: int = Query(1, ge=1), evidence_page_size: int = Query(50, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    result = incident_detail(session, incident_id, evidence_page, evidence_page_size)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "incident_not_found"})
    return result


_TICKET_ERRORS = {404: {"model": ErrorResponse, "description": "Incident not found"}, 409: {"model": ErrorResponse, "description": "Invalid transition"}}


@router.post("/{incident_id}/acknowledge", response_model=TicketActionResponse, responses=_TICKET_ERRORS)
def acknowledge(incident_id: UUID, payload: TicketAction, session: Session = Depends(get_session)) -> dict:
    return _transition(session, incident_id, "acknowledge", payload.model_dump(mode="json"))


@router.post("/{incident_id}/assign", response_model=TicketActionResponse, responses=_TICKET_ERRORS)
def assign(incident_id: UUID, payload: AssignTicket, session: Session = Depends(get_session)) -> dict:
    data = payload.model_dump(mode="json")
    data["reason"] = data["reason"] or f"assigned:{payload.crew_label}"
    return _transition(session, incident_id, "assign_crew", data)


@router.post("/{incident_id}/report-resolved", response_model=TicketActionResponse, responses=_TICKET_ERRORS)
def report_resolved(incident_id: UUID, payload: TicketAction, session: Session = Depends(get_session)) -> dict:
    return _transition(session, incident_id, "report_resolved", payload.model_dump(mode="json"))


def _transition(session: Session, incident_id: UUID, action: str, payload: dict) -> dict:
    try:
        result = transition_ticket(session, incident_id, action, payload["actor"], payload)
    except ValueError as error:
        raise HTTPException(status_code=404, detail={"code": "incident_not_found"}) from error
    detail = incident_detail(session, result.incident.id)
    response = {"code": result.code, "incident": detail, "ticket_event": {
        "id": str(result.audit_event.id), "type": result.audit_event.event_type, "from_status": result.audit_event.from_status,
        "to_status": result.audit_event.to_status, "actor": result.audit_event.actor, "reason": result.audit_event.reason,
        "evidence_ids": result.audit_event.evidence_ids, "occurred_at": result.audit_event.occurred_at,
    }}
    session.commit()
    if not result.accepted:
        raise HTTPException(status_code=409, detail=jsonable_encoder(response))
    return response
