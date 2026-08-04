from datetime import UTC, datetime, timedelta

from app.detection.classification import FaultClassification
from app.detection.schedules import match_schedule
from app.schedules.feed import DatabaseScheduleFeed, ScheduleCache, ScheduleSnapshot
from app.schedules.mock import MockScheduleFeed


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
CLASSIFICATION = FaultClassification("dt", transformer_id="DT1", feeder_id="F1")
SCHEDULE = {"id": "S1", "scope": {"transformer_id": "DT1"}, "scheduled_start": NOW, "scheduled_end": NOW + timedelta(hours=1)}


def test_matching_schedule_suppresses_only_after_its_start():
    # Break caught: future maintenance suppresses a real present-time fault.
    before = match_schedule(CLASSIFICATION, [SCHEDULE], NOW - timedelta(seconds=1))
    during = match_schedule(CLASSIFICATION, [SCHEDULE], NOW + timedelta(minutes=10))

    assert before.status == "unmatched"
    assert during.status == "planned"


def test_schedule_cache_keeps_last_success_without_extending_window():
    # Break caught: a failed refresh erases or prolongs a previously valid feed snapshot.
    cache = ScheduleCache()
    cache.store(ScheduleSnapshot((SCHEDULE,), NOW, version=1), NOW)
    cache.record_failure(NOW + timedelta(minutes=1))

    assert cache.current.stale is True
    assert cache.current.schedules == (SCHEDULE,)
    assert match_schedule(CLASSIFICATION, cache.current, NOW + timedelta(hours=1, minutes=41)).status == "overrun"
    assert cache.snapshots[-1].version == 1


def test_schedule_scope_requires_equivalent_dt_or_feeder_classification():
    # Break caught: a span inside planned DT work is incorrectly suppressed.
    span = FaultClassification("span", transformer_id="DT1", feeder_id="F1")
    feeder = FaultClassification("feeder", feeder_id="F1")

    assert match_schedule(span, [SCHEDULE], NOW + timedelta(minutes=1)).status == "unmatched"
    assert match_schedule(feeder, [{**SCHEDULE, "scope": {"feeder_id": "F1"}}], NOW + timedelta(minutes=1)).status == "planned"


def test_database_feed_snapshots_task_two_rows_without_a_live_network_call():
    # Break caught: lifespan polling uses an empty mock instead of persisted scheduled outages.
    feed = DatabaseScheduleFeed(loader=lambda: [SCHEDULE])

    snapshot = feed.fetch()

    assert snapshot.schedules == (SCHEDULE,)
    assert snapshot.version == 1
