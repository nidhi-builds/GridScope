from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Page(BaseModel):
    items: list[dict[str, Any]]
    page: int
    page_size: int
    total: int


class TicketAction(BaseModel):
    actor: str = "operator"
    reason: str = ""
    evidence_ids: list[UUID] = Field(default_factory=list)


class AssignTicket(TicketAction):
    crew_label: str = Field(min_length=1)


class TicketActionResponse(BaseModel):
    code: str
    incident: dict[str, Any]
    ticket_event: dict[str, Any]


class ErrorResponse(BaseModel):
    detail: dict[str, Any]


class ReadyResponse(BaseModel):
    database: str
    seed: str
    worker: str
    last_processed_at: datetime | None
    unprocessed_count: int
    oldest_backlog_age_seconds: int | None
