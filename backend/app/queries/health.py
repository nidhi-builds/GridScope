from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.assets import Device, DeviceAssignment, Pole
from app.db.models.incidents import PlannedOperation, ScheduledOutage
from app.db.models.telemetry import PoleEvidenceState, TelemetryEvent


def readiness(session: Session, worker_ready: bool) -> dict:
    seeded = bool(session.scalar(select(Pole.id).limit(1)))
    pending = session.scalar(select(func.count()).select_from(TelemetryEvent).where(TelemetryEvent.processed_at.is_(None))) or 0
    oldest = session.scalar(select(func.min(TelemetryEvent.received_at)).where(TelemetryEvent.processed_at.is_(None)))
    processed = session.scalar(select(func.max(TelemetryEvent.processed_at)))
    return {
        "database": "ready", "seed": "ready" if seeded else "missing", "worker": "ready" if worker_ready else "unavailable",
        "ai": "configured" if get_settings().gemini_api_key else "unconfigured",
        "last_processed_at": processed, "unprocessed_count": pending,
        "oldest_backlog_age_seconds": None if oldest is None else max(0, int((datetime.now(UTC) - oldest).total_seconds())),
    }


def list_planned_operations(session: Session, page: int, page_size: int) -> tuple[list[dict], int]:
    statement = select(PlannedOperation, ScheduledOutage).join(ScheduledOutage, ScheduledOutage.id == PlannedOperation.scheduled_outage_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.execute(statement.order_by(PlannedOperation.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return [{
        "id": str(operation.id), "incident_id": str(operation.incident_id) if operation.incident_id else None,
        "status": operation.status, "scope": outage.scope,
        "scheduled_start": outage.scheduled_start, "scheduled_end": outage.scheduled_end,
        "observed_start": operation.observed_start, "observed_end": operation.observed_end,
        "snapshot_stale": outage.snapshot_stale, "promotion_outcome": operation.promotion_outcome,
        "end_grace_minutes": outage.end_grace_minutes, "source_updated_at": outage.source_updated_at,
    } for operation, outage in rows], total


def list_device_health(session: Session, page: int, page_size: int) -> tuple[list[dict], int]:
    statement = select(Device, Pole, PoleEvidenceState).join(
        DeviceAssignment, DeviceAssignment.device_id == Device.id
    ).join(Pole, Pole.id == DeviceAssignment.pole_id).outerjoin(
        PoleEvidenceState, PoleEvidenceState.pole_id == Pole.id
    ).where(DeviceAssignment.effective_to.is_(None))
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = list(session.execute(statement.order_by(Device.is_online, Device.battery_pct, Device.serial_number).offset((page - 1) * page_size).limit(page_size)))
    delivery = _delivery_counts(session, {device.id for device, _, _ in rows})
    return [{
        "device_id": str(device.id), "serial_number": device.serial_number, "pole_id": str(pole.id),
        "is_online": device.is_online, "battery_pct": device.battery_pct, "rssi_dbm": device.rssi_dbm,
        "evidence_class": state.evidence_class if state else "unknown_silent",
        "device_health": state.device_health if state else ("healthy" if device.is_online else "offline"),
        "mismatch_events": delivery.get((device.id, "quarantined"), 0),
        "stale_replay_events": delivery.get((device.id, "audit_only"), 0),
    } for device, pole, state in rows], total


def _delivery_counts(session: Session, device_ids: set) -> dict[tuple, int]:
    """Count only the page's devices so the ingest table is never scanned whole."""
    if not device_ids:
        return {}
    rows = session.execute(
        select(TelemetryEvent.device_id, TelemetryEvent.processing_state, func.count())
        .where(TelemetryEvent.device_id.in_(device_ids), TelemetryEvent.processing_state.in_(("quarantined", "audit_only")))
        .group_by(TelemetryEvent.device_id, TelemetryEvent.processing_state)
    )
    return {(device_id, state): count for device_id, state, count in rows}
