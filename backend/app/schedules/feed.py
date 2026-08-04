import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class ScheduleSnapshot:
    schedules: tuple[Any, ...]
    fetched_at: datetime
    version: int = 0
    stale: bool = False


class ScheduleFeed(Protocol):
    def fetch(self) -> ScheduleSnapshot: ...


@dataclass
class DatabaseScheduleFeed:
    """Small adapter over Task 2's durable schedule rows."""
    loader: Callable[[], list[Any]] | None = None
    version: int = 0

    def fetch(self) -> ScheduleSnapshot:
        if self.loader:
            rows = self.loader()
        else:
            from app.db import SessionLocal
            from app.db.models.incidents import ScheduledOutage
            with SessionLocal() as session:
                rows = [
                    {
                        "id": row.id, "external_id": row.external_id, "scope": row.scope,
                        "scheduled_start": row.scheduled_start, "scheduled_end": row.scheduled_end,
                        "end_grace_minutes": row.end_grace_minutes,
                    }
                    for row in session.query(ScheduledOutage).all()
                ]
        self.version += 1
        return ScheduleSnapshot(tuple(rows), datetime.now().astimezone(), self.version)


@dataclass
class ScheduleCache:
    current: ScheduleSnapshot | None = None
    last_success_at: datetime | None = None
    snapshots: list[ScheduleSnapshot] = field(default_factory=list)

    def store(self, snapshot: ScheduleSnapshot, now: datetime) -> None:
        version = snapshot.version or ((self.current.version + 1) if self.current else 1)
        self.current = replace(snapshot, version=version, stale=False)
        self.last_success_at = now
        self.snapshots.append(self.current)

    def record_failure(self, now: datetime) -> None:
        if self.current:
            self.current = replace(self.current, stale=True)


async def poll_schedule_feed(feed: ScheduleFeed, cache: ScheduleCache, stop: asyncio.Event, interval_seconds: float = 60) -> None:
    while not stop.is_set():
        now = datetime.now().astimezone()
        try:
            cache.store(feed.fetch(), now)
        except Exception:
            cache.record_failure(now)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
