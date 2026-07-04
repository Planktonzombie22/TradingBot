from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Protocol

from src.engine import EngineEvent, EngineEventType


@dataclass(frozen=True)
class NotificationEvent:
    topic: str
    message: str
    severity: str = "INFO"
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationSink(Protocol):
    def send(self, event: NotificationEvent) -> None:
        ...


@dataclass
class InMemoryNotificationSink:
    events: list[NotificationEvent] = field(default_factory=list)

    def send(self, event: NotificationEvent) -> None:
        self.events.append(event)


@dataclass(frozen=True)
class NotificationRouter:
    sink: NotificationSink

    def handle_engine_event(self, event: EngineEvent) -> None:
        topic_map = {
            EngineEventType.STARTED: ("startup", "INFO"),
            EngineEventType.STOPPED: ("shutdown", "INFO"),
            EngineEventType.ORDER: ("order", "INFO"),
            EngineEventType.FILL: ("fill", "INFO"),
            EngineEventType.ERROR: ("exception", "ERROR"),
            EngineEventType.HALT: ("halt", "CRITICAL"),
        }
        if event.event_type not in topic_map:
            return
        topic, severity = topic_map[event.event_type]
        self.sink.send(
            NotificationEvent(
                topic=topic,
                message=event.message,
                severity=severity,
                payload=event.payload,
                timestamp=event.timestamp,
            )
        )
