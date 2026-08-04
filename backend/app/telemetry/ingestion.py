from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.assets import Device, DeviceAssignment, Pole
from app.db.models.telemetry import TelemetryEvent
from app.telemetry.fingerprint import fingerprint
from app.telemetry.schemas import TelemetryPayload


class TelemetryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AcceptResult:
    outcome: str
    event_id: UUID | None = None


def accept_payload(session: Session, payload: TelemetryPayload, received_at: datetime) -> AcceptResult:
    """Validate and append one event; the caller owns the enclosing commit."""
    if session.get(Device, payload.device_id) is None:
        raise TelemetryValidationError("unknown device")
    if session.get(Pole, payload.pole_id) is None:
        raise TelemetryValidationError("unknown pole")

    assignment = session.scalar(
        select(DeviceAssignment).where(
            DeviceAssignment.device_id == payload.device_id,
            DeviceAssignment.effective_from <= received_at,
            or_(DeviceAssignment.effective_to.is_(None), DeviceAssignment.effective_to > received_at),
        )
    )
    mismatched = assignment is None or assignment.pole_id != payload.pole_id
    values = {
        "device_id": payload.device_id,
        "pole_id": payload.pole_id,
        "fingerprint": fingerprint(payload),
        "event_type": payload.event_type,
        "payload": payload.model_dump(mode="json"),
        "device_time": payload.ts,
        "received_at": received_at,
        "processing_state": "quarantined" if mismatched else "pending",
        "failed_reason": "assignment mismatch" if mismatched else None,
        "epoch_decision": "quarantined" if mismatched else None,
    }
    event_id = session.execute(
        insert(TelemetryEvent)
        .values(values)
        .on_conflict_do_nothing(index_elements=[TelemetryEvent.fingerprint])
        .returning(TelemetryEvent.id)
    ).scalar_one_or_none()
    if event_id is None:
        return AcceptResult("duplicate")
    session.flush()
    return AcceptResult("quarantined" if mismatched else "accepted", event_id)
