from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class Substation(TimestampMixin, Base):
    __tablename__ = "substations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class Feeder(TimestampMixin, Base):
    __tablename__ = "feeders"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    substation_id: Mapped[UUID] = mapped_column(ForeignKey("substations.id"))
    code: Mapped[str] = mapped_column(String(32), unique=True)


class Transformer(TimestampMixin, Base):
    __tablename__ = "transformers"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    feeder_id: Mapped[UUID] = mapped_column(ForeignKey("feeders.id"))
    code: Mapped[str] = mapped_column(String(32), unique=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class Pole(TimestampMixin, Base):
    __tablename__ = "poles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    transformer_id: Mapped[UUID] = mapped_column(ForeignKey("transformers.id"))
    code: Mapped[str] = mapped_column(String(32), unique=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    pin_code: Mapped[str | None] = mapped_column(String(12))
    parent_pole_id: Mapped[UUID | None] = mapped_column(ForeignKey("poles.id"))
    branch_index: Mapped[int] = mapped_column(Integer)
    seq_on_line: Mapped[int | None] = mapped_column(Integer)


class TopologyEdge(TimestampMixin, Base):
    __tablename__ = "topology_edges"
    __table_args__ = (
        Index("ix_topology_edges_transformer_parent", "transformer_id", "parent_pole_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    transformer_id: Mapped[UUID] = mapped_column(ForeignKey("transformers.id"))
    parent_pole_id: Mapped[UUID] = mapped_column(ForeignKey("poles.id"))
    child_pole_id: Mapped[UUID] = mapped_column(ForeignKey("poles.id"))
    source: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, default=1)
    distance_m: Mapped[float] = mapped_column(Float)
    ambiguity_score: Mapped[float] = mapped_column(Float, default=0.0)
    calibration_bucket: Mapped[str | None] = mapped_column(String(32))
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    serial_number: Mapped[str] = mapped_column(String(64), unique=True)
    firmware: Mapped[str] = mapped_column(String(32))
    battery_pct: Mapped[float] = mapped_column(Float)
    rssi_dbm: Mapped[float] = mapped_column(Float)
    is_online: Mapped[bool] = mapped_column(Boolean)
    heartbeat_interval_seconds: Mapped[int] = mapped_column(Integer)
    next_heartbeat_offset_seconds: Mapped[int | None] = mapped_column(Integer)


class DeviceAssignment(TimestampMixin, Base):
    __tablename__ = "device_assignments"
    __table_args__ = (
        Index("ix_device_assignments_effective", "device_id", "effective_from", "effective_to"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id"))
    pole_id: Mapped[UUID] = mapped_column(ForeignKey("poles.id"))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
