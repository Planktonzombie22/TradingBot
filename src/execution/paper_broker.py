from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

from src.models import Order

from .broker import Broker
from .orders import mark_order


@dataclass
class PaperBroker(Broker):
    """Minimal broker simulator that tracks order lifecycle in memory."""

    orders: Dict[str, Order] = field(default_factory=dict)
    _counter: int = 0

    def submit_order(self, order: Order) -> Order:
        self._counter += 1
        order_id = str(self._counter)
        accepted = mark_order(order, "PENDING")
        self.orders[order_id] = accepted
        return accepted

    def cancel_order(self, order_id: str) -> Optional[Order]:
        order = self.orders.get(order_id)
        if order is None:
            return None
        cancelled = mark_order(order, "CANCELLED")
        self.orders[order_id] = cancelled
        return cancelled

    def open_orders(self) -> Iterable[Order]:
        return [order for order in self.orders.values() if order.status == "PENDING"]
