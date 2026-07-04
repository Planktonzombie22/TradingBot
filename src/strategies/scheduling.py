from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from src.data.calendar import MarketSessionCalendar, MarketSessionPolicy


@dataclass(frozen=True)
class StrategySchedule:
    """Runtime scheduling policy for a strategy/symbol/timeframe pair."""

    symbols: Sequence[str]
    timeframe: str
    warmup_bars: int = 0
    session_policy: MarketSessionPolicy = field(default_factory=MarketSessionPolicy)

    def should_run(
        self,
        symbol: str,
        timestamp: datetime,
        available_bars: int,
        calendar: MarketSessionCalendar | None = None,
    ) -> bool:
        if symbol not in set(self.symbols):
            return False
        if available_bars < self.warmup_bars:
            return False
        calendar = calendar or MarketSessionCalendar()
        return calendar.is_tradable_at(timestamp, self.session_policy)

    def to_schema(self) -> dict:
        return {
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "warmup_bars": self.warmup_bars,
            "session_policy": {
                "allow_pre_market": self.session_policy.allow_pre_market,
                "allow_regular": self.session_policy.allow_regular,
                "allow_after_hours": self.session_policy.allow_after_hours,
            },
        }
