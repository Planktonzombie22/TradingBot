from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Set
from zoneinfo import ZoneInfo


class MarketSession(str, Enum):
    CLOSED = "CLOSED"
    PRE_MARKET = "PRE_MARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"


@dataclass(frozen=True)
class MarketSessionPolicy:
    allow_pre_market: bool = False
    allow_regular: bool = True
    allow_after_hours: bool = False


@dataclass(frozen=True)
class MarketSessionCalendar:
    """Minimal US equities session calendar.

    This handles regular, pre-market, after-hours, holidays, and early closes.
    A full exchange-calendar dependency can replace this boundary later without
    changing callers.
    """

    timezone: str = "America/New_York"
    pre_market_open_time: time = time(4, 0)
    open_time: time = time(9, 30)
    close_time: time = time(16, 0)
    after_hours_close_time: time = time(20, 0)
    holidays: Set[str] = field(default_factory=set)
    early_closes: dict[str, time] = field(default_factory=dict)

    def is_open_at(self, timestamp: datetime) -> bool:
        return self.session_at(timestamp) == MarketSession.REGULAR

    def is_tradable_at(self, timestamp: datetime, policy: MarketSessionPolicy | None = None) -> bool:
        policy = policy or MarketSessionPolicy()
        session = self.session_at(timestamp)
        if session == MarketSession.PRE_MARKET:
            return policy.allow_pre_market
        if session == MarketSession.REGULAR:
            return policy.allow_regular
        if session == MarketSession.AFTER_HOURS:
            return policy.allow_after_hours
        return False

    def session_at(self, timestamp: datetime) -> MarketSession:
        local = self._localize(timestamp)
        if local.weekday() >= 5:
            return MarketSession.CLOSED
        if local.date().isoformat() in self.holidays:
            return MarketSession.CLOSED

        local_time = local.time()
        close_time = self.early_closes.get(local.date().isoformat(), self.close_time)
        if self.pre_market_open_time <= local_time < self.open_time:
            return MarketSession.PRE_MARKET
        if self.open_time <= local_time <= close_time:
            return MarketSession.REGULAR
        if close_time < local_time <= self.after_hours_close_time:
            return MarketSession.AFTER_HOURS
        return MarketSession.CLOSED

    def _localize(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo:
            return timestamp.astimezone(ZoneInfo(self.timezone))
        return timestamp.replace(tzinfo=ZoneInfo(self.timezone))
