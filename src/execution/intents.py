from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.models import Order, Signal


@dataclass(frozen=True)
class SignalIntent:
    signal: Signal
    strategy_name: str
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class TargetPositionIntent:
    symbol: str
    target_quantity: float
    source_signal: Optional[SignalIntent] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class GeneratedOrderIntent:
    order: Order
    source_target: Optional[TargetPositionIntent] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class BrokerOrderIntent:
    order: Order
    broker_order_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class FillIntent:
    order: Order
    quantity: float
    price: float
    broker_fill_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
