from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.telemetry.ingestion import TelemetryValidationError, accept_payload
from app.telemetry.schemas import TelemetryPayload


router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


def _accept(session: Session, payload: TelemetryPayload) -> dict[str, str | None]:
    try:
        result = accept_payload(session, payload, datetime.now(UTC))
        session.commit()
    except TelemetryValidationError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"outcome": result.outcome, "event_id": str(result.event_id) if result.event_id else None}


@router.post("", status_code=202)
def ingest(payload: TelemetryPayload, session: Session = Depends(get_session)) -> dict[str, str | None]:
    return _accept(session, payload)


@router.post("/batch", status_code=202)
def ingest_batch(payloads: list[TelemetryPayload], session: Session = Depends(get_session)) -> list[dict[str, str | None]]:
    try:
        results = [accept_payload(session, payload, datetime.now(UTC)) for payload in payloads]
        session.commit()
    except TelemetryValidationError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    return [{"outcome": result.outcome, "event_id": str(result.event_id) if result.event_id else None} for result in results]
