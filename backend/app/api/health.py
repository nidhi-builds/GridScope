from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.schemas import ReadyResponse
from app.db import get_session
from app.queries.health import readiness
router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=ReadyResponse)
def ready(request: Request, session: Session = Depends(get_session)) -> ReadyResponse:
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    worker = getattr(request.app.state, "worker", None)
    result = readiness(session, worker is not None and not worker.done())
    if result["seed"] != "ready" or result["worker"] != "ready":
        raise HTTPException(status_code=503, detail=result)
    return ReadyResponse(**result)
