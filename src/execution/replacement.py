from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.models import Order


@dataclass(frozen=True)
class OrderReplacementDecision:
    should_replace: bool
    reason: str
    replacement: Optional[Order] = None
    should_cancel: bool = False


@dataclass(frozen=True)
class OrderReplacementPolicy:
    stale_after_seconds: int = 300
    limit_chase_bps: float = 0.0
    cancel_stale_market_orders: bool = True

    def evaluate(self, order: Order, reference_price: float, now: Optional[datetime] = None) -> OrderReplacementDecision:
        now = now or datetime.now(timezone.utc)
        age = now - order.created_at
        if age < timedelta(seconds=self.stale_after_seconds):
            return OrderReplacementDecision(False, "Order is not stale.")

        if order.order_type == "MARKET" and self.cancel_stale_market_orders:
            return OrderReplacementDecision(False, "Stale market order should be cancelled.", should_cancel=True)

        if order.order_type == "LIMIT" and self.limit_chase_bps > 0:
            direction = 1 if order.side == "BUY" else -1
            limit_price = reference_price * (1 + direction * self.limit_chase_bps / 10_000)
            return OrderReplacementDecision(
                True,
                "Stale limit order should be replaced near reference price.",
                replacement=replace(order, limit_price=limit_price),
            )

        return OrderReplacementDecision(False, "No replacement rule matched.")
