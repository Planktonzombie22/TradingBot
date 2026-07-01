from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Literal, Optional

Action = Literal["BUY", "SELL", "CLOSE", "HOLD"]


@dataclass
class Signal:
    """Strategy output for a single bar: what to do and optional risk parameters."""

    action: Action
    symbol: str
    timestamp: datetime
    strength: float = 1.0
    stop_loss: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def hold(cls, symbol: str, timestamp: datetime) -> "Signal":
        return cls(action="HOLD", symbol=symbol, timestamp=timestamp)
