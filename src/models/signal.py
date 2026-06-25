from dataclasses import dataclass, field
from typing import Literal, Dict, Any
from datetime import datetime, timezone

Action = Literal["BUY", "SELL", "HOLD"]

@dataclass
class Signal:
    action: Action
    symbol: str
    strength: float = 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    meta: Dict[str, Any] = field(default_factory=dict)
