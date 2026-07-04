from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict


@dataclass(frozen=True)
class HealthStatus:
    name: str
    healthy: bool
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class HealthCheck:
    name: str
    check: Callable[[], HealthStatus]

    def run(self) -> HealthStatus:
        try:
            return self.check()
        except Exception as exc:
            return HealthStatus(self.name, False, str(exc))


@dataclass
class MetricsRegistry:
    counters: Dict[str, float] = field(default_factory=dict)
    gauges: Dict[str, float] = field(default_factory=dict)
    timings: Dict[str, list[float]] = field(default_factory=dict)

    def increment(self, name: str, amount: float = 1.0) -> None:
        self.counters[name] = self.counters.get(name, 0.0) + amount

    def gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def timing(self, name: str, seconds: float) -> None:
        self.timings.setdefault(name, []).append(seconds)

    def snapshot(self) -> dict:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "timings": {key: list(values) for key, values in self.timings.items()},
        }
