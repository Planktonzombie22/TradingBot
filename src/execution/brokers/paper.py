from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

from src.models import Order

from .base import Broker
from ..lifecycle.reconciliation import BrokerAccountSnapshot, BrokerPositionSnapshot, ExecutionReport
from ..orders.ids import ensure_client_order_id, mark_order


@dataclass
class PaperBroker(Broker):
    """Minimal broker simulator that tracks order lifecycle in memory."""

    auto_fill_market_orders: bool = True
    orders: Dict[str, Order] = field(default_factory=dict)
    reports: Dict[str, ExecutionReport] = field(default_factory=dict)
    _counter: int = 0

    def submit_order(self, order: Order) -> Order:
        order = ensure_client_order_id(order)
        duplicate = self._order_by_client_id(order.client_order_id)
        if duplicate is not None:
            return duplicate
        self._counter += 1
        broker_order_id = str(self._counter)
        status = "FILLED" if self.auto_fill_market_orders and order.order_type == "MARKET" else "PENDING"
        accepted = mark_order(order, status)
        self.orders[accepted.id] = accepted
        self.reports[accepted.id] = ExecutionReport.from_order(accepted, broker_order_id=broker_order_id)
        return accepted

    def cancel_order(self, order_id: str) -> Optional[Order]:
        order = self.orders.get(order_id)
        if order is None:
            return None
        cancelled = mark_order(order, "CANCELLED")
        self.orders[order_id] = cancelled
        self.reports[order_id] = ExecutionReport.from_order(cancelled, broker_order_id=self.reports[order_id].broker_order_id)
        return cancelled

    def replace_order(self, order_id: str, replacement: Order) -> Optional[Order]:
        existing = self.orders.get(order_id)
        if existing is None:
            return None
        replacement.id = order_id
        status = "FILLED" if self.auto_fill_market_orders and replacement.order_type == "MARKET" else "PENDING"
        updated = mark_order(replacement, status)
        self.orders[order_id] = updated
        broker_order_id = self.reports[order_id].broker_order_id if order_id in self.reports else None
        self.reports[order_id] = ExecutionReport.from_order(updated, broker_order_id=broker_order_id)
        return updated

    def open_orders(self) -> Iterable[Order]:
        return [order for order in self.orders.values() if order.status == "PENDING"]

    def account_snapshot(self) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(cash=0.0, buying_power=0.0, equity=0.0, raw={"source": "paper_broker"})

    def positions(self) -> Iterable[BrokerPositionSnapshot]:
        return []

    def execution_reports(self) -> Iterable[ExecutionReport]:
        return list(self.reports.values())

    def _order_by_client_id(self, client_order_id: Optional[str]) -> Optional[Order]:
        if not client_order_id:
            return None
        for order in self.orders.values():
            if order.client_order_id == client_order_id:
                return order
        return None
