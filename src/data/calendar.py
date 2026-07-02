from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Set
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketSessionCalendar:
    """Minimal US equities session calendar.

    This handles weekdays and regular trading hours. Holiday coverage can be
    expanded later by adding dates to `holidays`.
    """

    timezone: str = "America/New_York"
    open_time: time = time(9, 30)
    close_time: time = time(16, 0)
    holidays: Set[str] = field(default_factory=set)

    def is_open_at(self, timestamp: datetime) -> bool:
        local = timestamp.astimezone(ZoneInfo(self.timezone)) if timestamp.tzinfo else timestamp.replace(tzinfo=ZoneInfo(self.timezone))
        if local.weekday() >= 5:
            return False
        if local.date().isoformat() in self.holidays:
            return False
        return self.open_time <= local.time() <= self.close_time
