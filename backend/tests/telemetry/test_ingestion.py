from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.db.models.assets import DeviceAssignment
from app.db.models.telemetry import TelemetryEvent
from app.telemetry.ingestion import accept_payload
from app.telemetry.schemas import TelemetryPayload


RECEIVED_AT = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


@pytest.fixture
def session():
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as session:
            yield session
        transaction.rollback()


@pytest.fixture
def payload(session):
    assignment = session.scalar(select(DeviceAssignment).limit(1))
    return TelemetryPayload(
        device_id=assignment.device_id,
        pole_id=assignment.pole_id,
        seq=7,
        ts=RECEIVED_AT,
        event_type="heartbeat",
        energized=True,
        firmware="1.2",
        battery=75.0,
        rssi=-70.0,
    )


def test_exact_retry_is_stored_once(session, payload):
    # Break caught: at-least-once delivery creates duplicate durable inbox rows.
    first = accept_payload(session, payload, RECEIVED_AT)
    second = accept_payload(session, payload, RECEIVED_AT + timedelta(seconds=1))

    assert first.outcome == "accepted"
    assert second.outcome == "duplicate"
    assert session.scalar(select(func.count()).select_from(TelemetryEvent)) == 1


def test_assignment_mismatch_is_quarantined_without_changing_registry(session, payload):
    # Break caught: device swaps rewrite the registry while accepting an event.
    other_assignment = session.scalar(
        select(DeviceAssignment).where(DeviceAssignment.pole_id != payload.pole_id).limit(1)
    )
    mismatch = payload.model_copy(update={"pole_id": other_assignment.pole_id})

    result = accept_payload(session, mismatch, RECEIVED_AT)
    event = session.get(TelemetryEvent, result.event_id)

    assert result.outcome == "quarantined"
    assert event.processing_state == "quarantined"
    assert event.failed_reason == "assignment mismatch"
    assert session.scalar(
        select(DeviceAssignment.pole_id).where(DeviceAssignment.device_id == payload.device_id)
    ) == payload.pole_id
