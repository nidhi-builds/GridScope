from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class TelemetryPayload(BaseModel):
    device_id: UUID
    pole_id: UUID
    seq: int = Field(ge=0)
    ts: datetime
    event_type: Literal["heartbeat", "boot", "power_lost", "power_restored"]
    energized: bool
    firmware: str | None = None
    battery: float | None = Field(default=None, ge=0, le=100)
    rssi: float | None = None

    @field_validator("ts")
    @classmethod
    def timestamp_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ts must include a UTC offset")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def event_must_match_power_state(self):
        expected = {"heartbeat": True, "boot": True, "power_lost": False, "power_restored": True}
        if self.energized != expected[self.event_type]:
            raise ValueError("energized is incompatible with event_type")
        return self
