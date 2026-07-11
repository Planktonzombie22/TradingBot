from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo


class EndOfDayAction(str, Enum):
    HOLD = "HOLD"
    CANCEL_OPEN_ORDERS = "CANCEL_OPEN_ORDERS"
    FLATTEN = "FLATTEN"
    REDUCE = "REDUCE"


@dataclass(frozen=True)
class EndOfDayPolicy:
    action: EndOfDayAction = EndOfDayAction.HOLD
    trigger_time: time = time(15, 55)
    timezone: str = "America/New_York"
    reduce_fraction: float = 1.0

    def should_apply(self, timestamp: datetime) -> bool:
        local = timestamp.astimezone(ZoneInfo(self.timezone)) if timestamp.tzinfo else timestamp.replace(tzinfo=ZoneInfo(self.timezone))
        return local.time() >= self.trigger_time

    def action_payload(self) -> dict:
        return {
            "action": self.action.value,
            "trigger_time": self.trigger_time.isoformat(),
            "timezone": self.timezone,
            "reduce_fraction": self.reduce_fraction,
        }
