from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, aliased

from app.config import get_settings
from app.db import SessionLocal, engine
from app.db.models.assets import DeviceAssignment, Pole, TopologyEdge, Transformer
from app.db.models.telemetry import DetectionCandidate, DeviceStreamState, PoleEvidenceState, TelemetryEvent
from app.detection.candidates import _feeder_coverage, evaluate_candidate
from app.telemetry.ingestion import accept_payload
from app.telemetry.schemas import TelemetryPayload
from app.telemetry import worker as worker_module
from app.telemetry.worker import process_inbox_batch, run_worker
from app.schedules.feed import ScheduleSnapshot


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_db_feeder_coverage_aggregates_qualified_dt_candidates():
    # Break caught: isolated DT candidates can never reach feeder scope in the worker path.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                feeder_id = session.scalar(select(Transformer.feeder_id).group_by(Transformer.feeder_id).limit(1))
                transformer_ids = list(session.scalars(select(Transformer.id).where(Transformer.feeder_id == feeder_id).limit(3)))
                for transformer_id in transformer_ids:
                    session.add(DetectionCandidate(transformer_id=transformer_id, scope_key=f"dt:{transformer_id}", first_received_at=NOW, expires_at=NOW, status="actionable", promotion_outcome="dt", evidence_event_ids=["dark-1", "dark-2"]))
                session.flush()

                coverage = _feeder_coverage(session, transformer_ids[0], NOW)

                assert coverage["feeder_dts"][feeder_id]["qualifying"] == set(transformer_ids)
        finally:
            transaction.rollback()


def test_db_feeder_coverage_excludes_old_and_late_dt_candidates():
    # Break caught: separate DT incidents outside one 45-second window manufacture a feeder outage.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                feeder_id = session.scalar(
                    select(Transformer.feeder_id).group_by(Transformer.feeder_id).having(func.count() >= 3).limit(1)
                )
                transformer_ids = list(session.scalars(select(Transformer.id).where(Transformer.feeder_id == feeder_id).limit(3)))
                session.execute(delete(DetectionCandidate).where(DetectionCandidate.transformer_id.in_(transformer_ids)))
                for transformer_id, first in zip(transformer_ids, (NOW, NOW - timedelta(seconds=46), NOW + timedelta(seconds=46))):
                    session.add(DetectionCandidate(transformer_id=transformer_id, scope_key=f"dt:{transformer_id}", first_received_at=first, expires_at=first, status="actionable", promotion_outcome="dt", evidence_event_ids=["dark-1", "dark-2"]))
                session.flush()

                coverage = _feeder_coverage(session, transformer_ids[0], NOW)

                assert coverage["feeder_dts"][feeder_id]["qualifying"] == {transformer_ids[0]}
        finally:
            transaction.rollback()


def test_worker_passes_lifespan_schedule_snapshot_to_candidate_evaluation(monkeypatch):
    # Break caught: operational detection re-queries schedule rows and loses the cache stale flag.
    captured = []
    monkeypatch.setattr("app.telemetry.worker.evaluate_open_candidates", lambda session, now, schedules: captured.append(schedules))
    snapshot = ScheduleSnapshot((), NOW, stale=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                process_inbox_batch(session, limit=0, now=NOW, schedules=snapshot)
            assert captured == [snapshot]
        finally:
            transaction.rollback()


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
                cleanup.execute(delete(PoleEvidenceState).where(PoleEvidenceState.source_event_id == event_id))
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


def test_current_dark_replay_creates_one_evidence_state_and_candidate():
    # Break caught: accepted replay advances only stream state and never detection state.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                assignment = session.scalar(
                    select(DeviceAssignment)
                    .outerjoin(DeviceStreamState, DeviceStreamState.device_id == DeviceAssignment.device_id)
                    .limit(1)
                )
                accepted = accept_payload(
                    session,
                    TelemetryPayload(
                        device_id=assignment.device_id,
                        pole_id=assignment.pole_id,
                        seq=1,
                        ts=NOW,
                        event_type="power_lost",
                        energized=False,
                    ),
                    NOW,
                )

                assert process_inbox_batch(session, limit=10).processed == 1

                evidence = session.scalar(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == assignment.pole_id))
                transformer_id = session.get(Pole, assignment.pole_id).transformer_id
                candidates = list(session.scalars(
                    select(DetectionCandidate).where(DetectionCandidate.transformer_id == transformer_id)
                ))
                assert evidence.evidence_class == "confirmed_dark"
                assert evidence.source_event_id == accepted.event_id
                assert len(candidates) == 1
                assert candidates[0].evidence_event_ids == [str(accepted.event_id)]
        finally:
            transaction.rollback()


def test_worker_retains_the_accepted_pre_fault_live_time():
    # Break caught: evidence serialization replaces the live event time with database update time.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                assignment = session.scalar(
                    select(DeviceAssignment)
                    .outerjoin(DeviceStreamState, DeviceStreamState.device_id == DeviceAssignment.device_id)
                    .limit(1)
                )
                for seq, event_type, energized in ((1, "heartbeat", True), (2, "power_lost", False)):
                    accept_payload(
                        session,
                        TelemetryPayload(
                            device_id=assignment.device_id,
                            pole_id=assignment.pole_id,
                            seq=seq,
                            ts=NOW + timedelta(seconds=seq - 1),
                            event_type=event_type,
                            energized=energized,
                        ),
                        NOW + timedelta(seconds=seq - 1),
                    )

                assert process_inbox_batch(session, limit=10).processed == 2

                evidence = session.scalar(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == assignment.pole_id))
                assert evidence.evidence["pre_fault_live_at"] == NOW.isoformat()
        finally:
            transaction.rollback()


def test_worker_expires_persisted_heartbeat_to_silent_not_dark():
    # Break caught: durable evidence never transitions to unknown after heartbeat expiry.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                assignment = session.scalar(select(DeviceAssignment).limit(1))
                state = PoleEvidenceState(
                    pole_id=assignment.pole_id,
                    evidence_class="confirmed_live",
                    device_health="healthy",
                    fresh_until=NOW + timedelta(minutes=15),
                    evidence={"device_id": str(assignment.device_id), "observed_at": NOW.isoformat()},
                )
                session.add(state)

                process_inbox_batch(session, limit=0, now=NOW + timedelta(minutes=16))

                assert state.evidence_class == "unknown_silent"
                assert state.device_health == "silent"
                assert state.evidence["prior_evidence_class"] == "confirmed_live"
        finally:
            transaction.rollback()


def test_device_issue_marks_dark_evidence_suspect_with_provenance():
    # Break caught: an expired isolated dark report remains consumable as direct outage evidence.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                assignment = session.scalar(
                    select(DeviceAssignment)
                    .outerjoin(DeviceStreamState, DeviceStreamState.device_id == DeviceAssignment.device_id)
                    .limit(1)
                )
                accepted = accept_payload(
                    session,
                    TelemetryPayload(
                        device_id=assignment.device_id,
                        pole_id=assignment.pole_id,
                        seq=1,
                        ts=NOW,
                        event_type="power_lost",
                        energized=False,
                    ),
                    NOW,
                )
                process_inbox_batch(session, limit=10)
                candidate = session.scalar(select(DetectionCandidate))

                outcome = evaluate_candidate(candidate.id, NOW + timedelta(seconds=120), session)
                evidence = session.scalar(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == assignment.pole_id))

                assert outcome.classification == "device_issue"
                assert evidence.evidence_class == "device_suspect"
                assert evidence.source_event_id == accepted.event_id
                assert evidence.evidence["prior_evidence_class"] == "confirmed_dark"
                assert evidence.evidence["source_event_id"] == str(accepted.event_id)
        finally:
            transaction.rollback()


def test_live_child_device_issue_marks_the_dark_parent_suspect():
    # Break caught: a live-child contradiction leaves its dark parent as actionable evidence.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                parent = aliased(DeviceAssignment)
                child = aliased(DeviceAssignment)
                pair = session.execute(
                    select(parent, child)
                    .join(TopologyEdge, TopologyEdge.parent_pole_id == parent.pole_id)
                    .join(child, child.pole_id == TopologyEdge.child_pole_id)
                    .where(TopologyEdge.is_visible.is_(True))
                    .limit(1)
                ).one()
                dark, live = pair
                dark_event = accept_payload(
                    session,
                    TelemetryPayload(
                        device_id=dark.device_id,
                        pole_id=dark.pole_id,
                        seq=1,
                        ts=NOW,
                        event_type="power_lost",
                        energized=False,
                    ),
                    NOW,
                )
                accept_payload(
                    session,
                    TelemetryPayload(
                        device_id=live.device_id,
                        pole_id=live.pole_id,
                        seq=1,
                        ts=NOW + timedelta(seconds=1),
                        event_type="heartbeat",
                        energized=True,
                    ),
                    NOW + timedelta(seconds=1),
                )
                process_inbox_batch(session, limit=10)
                candidate = session.scalar(select(DetectionCandidate))

                outcome = evaluate_candidate(candidate.id, NOW + timedelta(seconds=30), session)
                evidence = session.scalar(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == dark.pole_id))

                assert outcome.defeated_reason == "fresh_live_child"
                assert evidence.evidence_class == "device_suspect"
                assert evidence.source_event_id == dark_event.event_id
        finally:
            transaction.rollback()


def test_worker_never_runs_its_batch_on_the_event_loop(monkeypatch):
    """Blocking the loop froze every request for the length of each batch and
    capped sustained ingest at ~53 req/s against a database doing ~900 tps."""
    import asyncio
    import threading

    stop = asyncio.Event()
    observed: dict[str, int] = {}

    def fake_batch(session, limit, now=None, schedules=None, simulator_run_id=None):
        observed["worker_thread"] = threading.get_ident()
        stop.set()
        return None

    monkeypatch.setattr(worker_module, "process_inbox_batch", fake_batch)
    asyncio.run(run_worker(stop))

    assert observed["worker_thread"] != threading.get_ident()


def test_worker_keeps_draining_while_batches_come_back_full(monkeypatch):
    """Sleeping the poll interval after a full batch capped drain at one batch per
    3s, leaving 11,161 events unprocessed 60s after a 60s load run."""
    import asyncio

    from app.telemetry.worker import BatchResult

    stop = asyncio.Event()
    batch_size = get_settings().worker_batch_size
    claimed_per_call = [batch_size, batch_size, 0]
    slept: list[float] = []

    def fake_batch(session, limit, now=None, schedules=None, simulator_run_id=None):
        remaining = claimed_per_call.pop(0)
        if not claimed_per_call:
            stop.set()
        return BatchResult(claimed=remaining, processed=remaining, failed=0)

    async def fake_wait_for(awaitable, timeout):
        slept.append(timeout)
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(worker_module, "process_inbox_batch", fake_batch)
    monkeypatch.setattr(worker_module.asyncio, "wait_for", fake_wait_for)
    asyncio.run(run_worker(stop))

    # Two full batches ran back to back; only the empty batch waited.
    assert claimed_per_call == []
    assert slept == [get_settings().poll_interval_ms / 1000]
