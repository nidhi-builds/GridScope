import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.db.models.telemetry import DeviceStreamState, PoleEvidenceState, TelemetryEvent
from app.detection.candidates import attach_candidate, evaluate_open_candidates
from app.detection.evidence import PoleEvidence, apply_event, expire_heartbeat
from app.incidents.restoration import evaluate_open_restorations
from app.schedules.feed import ScheduleSnapshot
from app.telemetry.stream_state import StreamEvent, StreamState, advance_stream


@dataclass(frozen=True)
class BatchResult:
    claimed: int = 0
    processed: int = 0
    failed: int = 0


def process_inbox_batch(
    session: Session, limit: int, now: datetime | None = None, schedules=None, simulator_run_id: UUID | None = None,
) -> BatchResult:
    query = (
        select(TelemetryEvent)
        .where(TelemetryEvent.processed_at.is_(None), TelemetryEvent.processing_state.in_(("pending", "retry")))
        .order_by(TelemetryEvent.processing_state == "retry", TelemetryEvent.received_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if simulator_run_id:
        query = query.where(TelemetryEvent.payload["simulator_run_id"].astext == str(simulator_run_id))
    rows = list(session.scalars(query))
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
    if now is not None:
        _expire_evidence(session, now)
        if simulator_run_id:
            evaluate_open_candidates(session, now, schedules, f"sim:{simulator_run_id}:")
        else:
            evaluate_open_candidates(session, now, schedules)
        evaluate_open_restorations(session, now, simulator_run_id)
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
        _apply_detection(session, row)
    row.processing_state = "processed" if decision.action == "apply" else "audit_only"
    row.epoch_decision = decision.reason
    row.processed_at = datetime.now(row.received_at.tzinfo)
    row.failed_reason = None


def _apply_detection(session: Session, row: TelemetryEvent) -> None:
    state_row = session.scalar(
        select(PoleEvidenceState).where(PoleEvidenceState.pole_id == row.pole_id).with_for_update()
    )
    previous = _to_evidence(state_row) if state_row else None
    decision = apply_event(previous, row, row.received_at)
    evidence = decision.evidence
    values = {
        "evidence_class": evidence.evidence_class,
        "source_event_id": evidence.source_event_id,
        "fresh_until": evidence.fresh_until,
        "device_health": evidence.device_health,
        "evidence": {
            "device_id": str(evidence.device_id) if evidence.device_id else None,
            "observed_at": evidence.observed_at.isoformat(),
            "pre_fault_live_at": evidence.pre_fault_live_at.isoformat() if evidence.pre_fault_live_at else None,
            "simulator_run_id": row.payload.get("simulator_run_id"),
        },
    }
    if state_row is None:
        session.add(PoleEvidenceState(pole_id=row.pole_id, **values))
    else:
        for name, value in values.items():
            setattr(state_row, name, value)
    attach_candidate(session, row)


def _to_evidence(state: PoleEvidenceState) -> PoleEvidence:
    pre_fault_live_at = state.evidence.get("pre_fault_live_at")
    return PoleEvidence(
        state.pole_id,
        UUID(state.evidence["device_id"]) if state.evidence.get("device_id") else None,
        state.evidence_class,
        state.device_health,
        datetime.fromisoformat(state.evidence["observed_at"]) if state.evidence.get("observed_at") else state.updated_at,
        state.source_event_id,
        state.fresh_until,
        datetime.fromisoformat(pre_fault_live_at) if pre_fault_live_at else None,
    )


def _expire_evidence(session: Session, now: datetime) -> None:
    states = session.scalars(
        select(PoleEvidenceState)
        .where(
            PoleEvidenceState.fresh_until.is_not(None),
            PoleEvidenceState.fresh_until < now,
            PoleEvidenceState.evidence_class.in_(("confirmed_live", "confirmed_dark")),
        )
        .with_for_update()
    )
    for state in states:
        decision = expire_heartbeat(_to_evidence(state), now)
        evidence = decision.evidence
        prior_evidence_class = state.evidence_class
        state.evidence_class = evidence.evidence_class
        state.device_health = evidence.device_health
        state.fresh_until = evidence.fresh_until
        state.evidence = {
            **state.evidence,
            "prior_evidence_class": prior_evidence_class,
            "source_event_id": str(state.source_event_id) if state.source_event_id else None,
        }


def _drain_once(batch_size: int, schedule_cache=None) -> BatchResult:
    with SessionLocal.begin() as session:
        now = datetime.now(UTC)
        schedules = schedule_cache.current if schedule_cache else None
        if schedule_cache and schedules is None:
            schedules = ScheduleSnapshot((), now, stale=True)
        return process_inbox_batch(session, batch_size, now, schedules)


async def run_worker(stop: asyncio.Event, schedule_cache=None) -> None:
    settings = get_settings()
    while not stop.is_set():
        # The batch is blocking database work. Running it directly on the event
        # loop froze every in-flight request for the length of each batch, which
        # capped sustained ingest far below what the database can absorb.
        result = await asyncio.to_thread(_drain_once, settings.worker_batch_size, schedule_cache)
        # A full batch means the inbox still has work. Sleeping the poll interval
        # anyway capped drain at one batch per interval, so a burst took minutes
        # to clear while thousands of events sat unprocessed.
        if result is not None and result.claimed >= settings.worker_batch_size:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_ms / 1000)
        except TimeoutError:
            pass
