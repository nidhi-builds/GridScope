from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> dict[str, str]:
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"database": "ready"}
