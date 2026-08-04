from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.schemas import Page
from app.db import get_session
from app.queries.health import list_device_health, list_planned_operations


router = APIRouter(prefix="/api/v1", tags=["operations"])


@router.get("/planned-operations", response_model=Page)
def planned_operations(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), session: Session = Depends(get_session)) -> Page:
    items, total = list_planned_operations(session, page, page_size)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/device-health", response_model=Page)
def device_health(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), session: Session = Depends(get_session)) -> Page:
    items, total = list_device_health(session, page, page_size)
    return Page(items=items, page=page, page_size=page_size, total=total)
