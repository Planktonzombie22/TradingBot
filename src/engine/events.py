from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class EngineEventType(str, Enum):
    STARTED = "STARTED"
    STOPPED = "STOPPED"
    CONTROL = "CONTROL"
    HALT = "HALT"
    MARKET_DATA = "MARKET_DATA"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"
    ERROR = "ERROR"


@dataclass(frozen=True)
class EngineEvent:
    event_type: EngineEventType
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = field(default_factory=dict)
