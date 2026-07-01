from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

Side = Literal["LONG", "SHORT"]


@dataclass
class Position:
    """Open exposure in a single symbol."""

    symbol: str
    side: Side
    shares: float
    entry_price: float
    entry_time: datetime
    stop_loss: Optional[float] = None

    @property
    def is_long(self) -> bool:
        return self.side == "LONG"

    @property
    def is_short(self) -> bool:
        return self.side == "SHORT"
