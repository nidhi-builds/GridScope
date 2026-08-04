import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.db.models.telemetry import DeviceStreamState, TelemetryEvent
from app.telemetry.stream_state import StreamEvent, StreamState, advance_stream


@dataclass(frozen=True)
class BatchResult:
    claimed: int = 0
    processed: int = 0
    failed: int = 0


def process_inbox_batch(session: Session, limit: int) -> BatchResult:
    rows = list(session.scalars(
        select(TelemetryEvent)
        .where(TelemetryEvent.processed_at.is_(None), TelemetryEvent.processing_state.in_(("pending", "retry")))
        .order_by(TelemetryEvent.processing_state == "retry", TelemetryEvent.received_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ))
    processed = failed = 0
    for row in rows:
        try:
            with session.begin_nested():
                _process_row(session, row)
            processed += 1
        except Exception as error:  # a malformed persisted row must not stall the inbox
            session.execute(
                update(TelemetryEvent)
                .where(TelemetryEvent.id == row.id)
                .values(processing_state="retry", failed_reason=str(error)[:500])
                .execution_options(synchronize_session="fetch")
            )
            failed += 1
    session.flush()
    return BatchResult(len(rows), processed, failed)


def _process_row(session: Session, row: TelemetryEvent) -> None:
    state_row = session.scalar(
        select(DeviceStreamState).where(DeviceStreamState.device_id == row.device_id).with_for_update()
    )
    state = None if state_row is None else StreamState(
        state_row.current_epoch, state_row.last_sequence, state_row.last_device_time, state_row.last_received_at
    )
    data = row.payload
    decision = advance_stream(
        state,
        StreamEvent(row.device_id, data["seq"], row.device_time, row.received_at, row.event_type),
    )
    if decision.action == "apply":
        if state_row is None:
            session.add(DeviceStreamState(
                device_id=row.device_id,
                current_epoch=decision.next_state.epoch,
                last_sequence=decision.next_state.last_sequence,
                last_device_time=decision.next_state.last_device_time,
                last_received_at=decision.next_state.last_received_at,
            ))
        else:
            state_row.current_epoch = decision.next_state.epoch
            state_row.last_sequence = decision.next_state.last_sequence
            state_row.last_device_time = decision.next_state.last_device_time
            state_row.last_received_at = decision.next_state.last_received_at
    row.processing_state = "processed" if decision.action == "apply" else "audit_only"
    row.epoch_decision = decision.reason
    row.processed_at = datetime.now(row.received_at.tzinfo)
    row.failed_reason = None


async def run_worker(stop: asyncio.Event) -> None:
    settings = get_settings()
    while not stop.is_set():
        with SessionLocal.begin() as session:
            process_inbox_batch(session, settings.worker_batch_size)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_ms / 1000)
        except TimeoutError:
            pass
