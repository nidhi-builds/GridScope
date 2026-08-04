from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin
from app.domain.types import EvidenceClass


class TelemetryEvent(TimestampMixin, Base):
    __tablename__ = "telemetry_events"
    __table_args__ = (
        Index("uq_telemetry_events_fingerprint", "fingerprint", unique=True),
        Index("ix_telemetry_events_processing", "processed_at", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"))
    pole_id: Mapped[UUID | None] = mapped_column(ForeignKey("poles.id"))
    fingerprint: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB)
    device_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_state: Mapped[str] = mapped_column(String(24), default="pending")
    failed_reason: Mapped[str | None] = mapped_column(String)
    epoch_decision: Mapped[str | None] = mapped_column(String(32))


class DeviceStreamState(TimestampMixin, Base):
    __tablename__ = "device_stream_state"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id"), unique=True)
    current_epoch: Mapped[int] = mapped_column(Integer)
    last_sequence: Mapped[int] = mapped_column(Integer)
    last_device_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PoleEvidenceState(TimestampMixin, Base):
    __tablename__ = "pole_evidence_state"
    __table_args__ = (
        CheckConstraint(
            "evidence_class in ('confirmed_live','confirmed_dark','unknown_silent','uninstrumented','device_suspect')",
            name="ck_pole_evidence_state_class",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    pole_id: Mapped[UUID] = mapped_column(ForeignKey("poles.id"), unique=True)
    evidence_class: Mapped[str] = mapped_column(String(32), default=EvidenceClass.UNKNOWN_SILENT)
    source_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("telemetry_events.id"))
    fresh_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_health: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)


class DetectionCandidate(TimestampMixin, Base):
    __tablename__ = "detection_candidates"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    transformer_id: Mapped[UUID] = mapped_column(ForeignKey("transformers.id"))
    scope_key: Mapped[str] = mapped_column(String(128))
    tier: Mapped[int] = mapped_column(Integer, default=1)
    first_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_event_ids: Mapped[list] = mapped_column(JSONB, default=list)
    promotion_outcome: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="investigating")
