from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID


FUTURE_SKEW = timedelta(seconds=90)
MAX_EVENT_AGE = timedelta(seconds=180)


@dataclass(frozen=True)
class StreamState:
    epoch: int
    last_sequence: int
    last_device_time: datetime
    last_received_at: datetime


@dataclass(frozen=True)
class StreamEvent:
    device_id: UUID
    seq: int
    ts: datetime
    received_at: datetime
    event_type: str


@dataclass(frozen=True)
class StreamDecision:
    action: str
    next_state: StreamState
    reason: str


def advance_stream(state: StreamState | None, event: StreamEvent) -> StreamDecision:
    """Advance only a current per-device event; old evidence remains audit-only."""
    if event.ts > event.received_at + FUTURE_SKEW or event.received_at - event.ts > MAX_EVENT_AGE:
        return StreamDecision("audit_only", state or _initial(event), "outside_realtime_window")
    if state is None:
        epoch = 1 if event.event_type == "boot" and event.seq == 0 else 0
        return StreamDecision("apply", StreamState(epoch, event.seq, event.ts, event.received_at), "initial")
    if event.event_type == "boot" and event.seq == 0:
        if event.ts <= state.last_device_time:
            return StreamDecision("audit_only", state, "stale_boot")
        return StreamDecision("apply", StreamState(state.epoch + 1, 0, event.ts, event.received_at), "new_epoch")
    if event.seq <= state.last_sequence:
        return StreamDecision("audit_only", state, "stale_sequence")
    if state.last_sequence == 0 and event.ts < state.last_device_time:
        return StreamDecision("audit_only", state, "stale_preboot_retry")
    return StreamDecision("apply", StreamState(state.epoch, event.seq, event.ts, event.received_at), "current_epoch")


def _initial(event: StreamEvent) -> StreamState:
    return StreamState(0, -1, event.ts, event.received_at)
