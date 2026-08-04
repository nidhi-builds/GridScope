from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.telemetry.stream_state import StreamEvent, StreamState, advance_stream


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_stale_boot_cannot_reset_current_epoch():
    # Break caught: a replayed boot erases the current sequence epoch.
    current = StreamState(epoch=3, last_sequence=28, last_device_time=NOW, last_received_at=NOW)
    stale_boot = StreamEvent(uuid4(), 0, NOW - timedelta(seconds=1), NOW, "boot")

    decision = advance_stream(current, stale_boot)

    assert decision.action == "audit_only"
    assert decision.next_state.epoch == current.epoch


def test_newer_boot_opens_a_new_epoch():
    current = StreamState(epoch=3, last_sequence=28, last_device_time=NOW, last_received_at=NOW)
    boot = StreamEvent(uuid4(), 0, NOW + timedelta(seconds=1), NOW + timedelta(seconds=1), "boot")

    decision = advance_stream(current, boot)

    assert decision.action == "apply"
    assert decision.reason == "new_epoch"
    assert decision.next_state.epoch == 4
    assert decision.next_state.last_sequence == 0


def test_old_high_sequence_after_boot_is_audit_only():
    current = StreamState(epoch=2, last_sequence=0, last_device_time=NOW, last_received_at=NOW)
    retry = StreamEvent(uuid4(), 90, NOW - timedelta(seconds=1), NOW + timedelta(seconds=1), "heartbeat")

    assert advance_stream(current, retry).action == "audit_only"


def test_higher_sequence_within_epoch_wins_over_timestamp_jitter():
    # Break caught: clock jitter discards a newer sequence in the active epoch.
    current = StreamState(epoch=2, last_sequence=7, last_device_time=NOW, last_received_at=NOW)
    next_event = StreamEvent(uuid4(), 8, NOW - timedelta(seconds=1), NOW + timedelta(seconds=1), "heartbeat")

    assert advance_stream(current, next_event).action == "apply"
