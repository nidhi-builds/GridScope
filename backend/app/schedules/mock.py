from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.schedules.feed import ScheduleSnapshot


@dataclass
class MockScheduleFeed:
    schedules: tuple[Any, ...] = ()
    now: datetime | None = None
    error: Exception | None = None
    version: int = 1

    def fetch(self) -> ScheduleSnapshot:
        if self.error:
            raise self.error
        if self.now is None:
            raise RuntimeError("mock schedule feed requires a deterministic timestamp")
        return ScheduleSnapshot(self.schedules, self.now, self.version)
