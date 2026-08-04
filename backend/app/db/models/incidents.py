from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin
from app.domain.types import IncidentStatus


class ScheduledOutage(TimestampMixin, Base):
    __tablename__ = "scheduled_outages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    scope: Mapped[dict] = mapped_column(JSONB)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    start_grace_minutes: Mapped[int] = mapped_column(Integer, default=20)
    end_grace_minutes: Mapped[int] = mapped_column(Integer, default=40)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot_stale: Mapped[bool] = mapped_column(Boolean, default=False)


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "status in ('detected','acknowledged','crew_assigned','resolved','verified','closed')",
            name="ck_incidents_status",
        ),
        Index("ix_incidents_status_updated", "status", "updated_at"),
        Index(
            "uq_incidents_active_correlation",
            "correlation_key",
            unique=True,
            postgresql_where=text("status <> 'closed'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    correlation_key: Mapped[str] = mapped_column(String(160))
    fault_class: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default=IncidentStatus.DETECTED)
    location_class: Mapped[str] = mapped_column(String(24))
    feeder_id: Mapped[UUID | None] = mapped_column(ForeignKey("feeders.id"))
    transformer_id: Mapped[UUID | None] = mapped_column(ForeignKey("transformers.id"))
    pole_id: Mapped[UUID | None] = mapped_column(ForeignKey("poles.id"))
    pin_code: Mapped[str] = mapped_column(String(12))
    pin_source: Mapped[str] = mapped_column(String(32))
    affected_count: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(16))
    confidence_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    navigation_latitude: Mapped[float] = mapped_column(Float)
    navigation_longitude: Mapped[float] = mapped_column(Float)
    simulation_id: Mapped[UUID | None] = mapped_column(ForeignKey("simulator_runs.id"))


class PlannedOperation(TimestampMixin, Base):
    __tablename__ = "planned_operations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    scheduled_outage_id: Mapped[UUID] = mapped_column(ForeignKey("scheduled_outages.id"))
    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"))
    status: Mapped[str] = mapped_column(String(32))
    observed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matched_evidence: Mapped[list] = mapped_column(JSONB, default=list)
    promotion_outcome: Mapped[str | None] = mapped_column(String(32))


class IncidentBoundary(TimestampMixin, Base):
    __tablename__ = "incident_boundaries"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id"))
    boundary_type: Mapped[str] = mapped_column(String(24))
    upstream_pole_id: Mapped[UUID | None] = mapped_column(ForeignKey("poles.id"))
    downstream_pole_id: Mapped[UUID | None] = mapped_column(ForeignKey("poles.id"))
    candidate_spans: Mapped[list] = mapped_column(JSONB, default=list)
    geometry: Mapped[dict] = mapped_column(JSONB, default=dict)


class IncidentEvidence(TimestampMixin, Base):
    __tablename__ = "incident_evidence"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id"))
    telemetry_event_id: Mapped[UUID] = mapped_column(ForeignKey("telemetry_events.id"))
    evidence_class: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)


class TicketEvent(TimestampMixin, Base):
    __tablename__ = "ticket_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id"))
    event_type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str | None] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AIExplanation(TimestampMixin, Base):
    __tablename__ = "ai_explanations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id"))
    prompt_version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    validated_text: Mapped[dict] = mapped_column(JSONB)
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
