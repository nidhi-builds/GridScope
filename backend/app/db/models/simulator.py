from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class SimulatorRun(TimestampMixin, Base):
    __tablename__ = "simulator_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    seed: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    truth: Mapped[dict] = mapped_column(JSONB, default=dict)
    expected_results: Mapped[dict] = mapped_column(JSONB, default=dict)
    actual_results: Mapped[dict] = mapped_column(JSONB, default=dict)


class SimulatedFault(TimestampMixin, Base):
    __tablename__ = "simulated_faults"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    simulator_run_id: Mapped[UUID] = mapped_column(ForeignKey("simulator_runs.id"))
    fault_class: Mapped[str] = mapped_column(String(32))
    target: Mapped[dict] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    repaired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    truth: Mapped[dict] = mapped_column(JSONB)
