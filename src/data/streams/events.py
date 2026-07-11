from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from src.models import Bar


class MarketDataEventType(str, Enum):
    BAR = "BAR"
    QUOTE = "QUOTE"
    TRADE = "TRADE"
    HEARTBEAT = "HEARTBEAT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class MarketDataEvent:
    event_type: MarketDataEventType
    symbol: str
    timestamp: datetime
    bar: Optional[Bar] = None
    payload: Dict[str, Any] = field(default_factory=dict)
