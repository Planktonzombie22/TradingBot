from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.models.position import Side


@dataclass
class Trade:
    """Completed or in-progress round trip."""

    symbol: str
    side: Side
    entry_time: datetime
    entry_price: float
    shares: float
    entry_equity: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_equity: Optional[float] = None
    pnl: Optional[float] = None

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    def close(self, exit_time: datetime, exit_price: float) -> "Trade":
        pnl = self.shares * (exit_price - self.entry_price)
        return Trade(
            symbol=self.symbol,
            side=self.side,
            entry_time=self.entry_time,
            entry_price=self.entry_price,
            shares=self.shares,
            entry_equity=self.entry_equity,
            exit_time=exit_time,
            exit_price=exit_price,
            exit_equity=self.entry_equity + pnl,
            pnl=pnl,
        )
