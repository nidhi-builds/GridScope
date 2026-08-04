from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.db.models.assets import DeviceAssignment
from app.db.models.telemetry import DeviceStreamState, TelemetryEvent
from app.telemetry.ingestion import accept_payload
from app.telemetry.schemas import TelemetryPayload
from app.telemetry.worker import process_inbox_batch


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_worker_replays_committed_event_once_in_a_fresh_session():
    # Break caught: a committed inbox row is not replayed exactly once after restart.
    event_id = device_id = None
    try:
        with SessionLocal() as intake:
            assignment = intake.scalar(
                select(DeviceAssignment)
                .outerjoin(DeviceStreamState, DeviceStreamState.device_id == DeviceAssignment.device_id)
                .where(DeviceStreamState.id.is_(None))
                .limit(1)
            )
            payload = TelemetryPayload(
                device_id=assignment.device_id,
                pole_id=assignment.pole_id,
                seq=1,
                ts=NOW,
                event_type="heartbeat",
                energized=True,
            )
            accepted = accept_payload(intake, payload, NOW)
            intake.commit()
            event_id, device_id = accepted.event_id, assignment.device_id

        with SessionLocal.begin() as worker:
            assert worker.get(TelemetryEvent, event_id).processed_at is None
            assert process_inbox_batch(worker, limit=10).processed == 1

        with SessionLocal.begin() as restarted_worker:
            assert restarted_worker.get(TelemetryEvent, event_id).processed_at is not None
            assert process_inbox_batch(restarted_worker, limit=10).claimed == 0
    finally:
        if event_id is not None:
            with SessionLocal.begin() as cleanup:
                cleanup.execute(delete(TelemetryEvent).where(TelemetryEvent.id == event_id))
                cleanup.execute(delete(DeviceStreamState).where(DeviceStreamState.device_id == device_id))


def test_poison_row_does_not_block_the_next_claimed_event():
    # Break caught: one corrupt inbox row prevents a valid event from being replayed.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                assignment = session.scalar(select(DeviceAssignment).limit(1))
                poison = TelemetryEvent(
                    device_id=assignment.device_id,
                    pole_id=assignment.pole_id,
                    fingerprint=uuid4().hex,
                    event_type="heartbeat",
                    payload={},
                    device_time=NOW,
                    received_at=NOW,
                )
                session.add(poison)
                accepted = accept_payload(
                    session,
                    TelemetryPayload(
                        device_id=assignment.device_id,
                        pole_id=assignment.pole_id,
                        seq=2,
                        ts=NOW,
                        event_type="heartbeat",
                        energized=True,
                    ),
                    NOW,
                )

                result = process_inbox_batch(session, limit=10)

                assert result == type(result)(claimed=2, processed=1, failed=1)
                assert session.get(TelemetryEvent, poison.id).processing_state == "retry"
                assert session.get(TelemetryEvent, accepted.event_id).processed_at is not None
        finally:
            transaction.rollback()


def test_retry_does_not_starve_a_later_pending_row_when_limit_is_one():
    # Break caught: selecting the oldest retry forever starves later valid inbox work.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                assignment = session.scalar(select(DeviceAssignment).limit(1))
                poison = TelemetryEvent(
                    device_id=assignment.device_id,
                    pole_id=assignment.pole_id,
                    fingerprint=uuid4().hex,
                    event_type="heartbeat",
                    payload={},
                    device_time=NOW - timedelta(seconds=1),
                    received_at=NOW - timedelta(seconds=1),
                )
                session.add(poison)
                accepted = accept_payload(
                    session,
                    TelemetryPayload(
                        device_id=assignment.device_id,
                        pole_id=assignment.pole_id,
                        seq=3,
                        ts=NOW,
                        event_type="heartbeat",
                        energized=True,
                    ),
                    NOW,
                )

                assert process_inbox_batch(session, limit=1).failed == 1
                assert session.get(TelemetryEvent, poison.id).processing_state == "retry"
                assert process_inbox_batch(session, limit=1).processed == 1
                assert session.get(TelemetryEvent, accepted.event_id).processed_at is not None
        finally:
            transaction.rollback()
