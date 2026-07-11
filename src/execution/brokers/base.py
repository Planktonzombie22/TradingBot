from abc import ABC, abstractmethod
from typing import Iterable, Optional

from src.models import Order
from ..lifecycle.reconciliation import BrokerAccountSnapshot, BrokerPositionSnapshot, BrokerSyncSnapshot, ExecutionReport


class Broker(ABC):
    """Broker contract shared by paper, backtest, and future live adapters."""

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> Optional[Order]:
        raise NotImplementedError

    @abstractmethod
    def replace_order(self, order_id: str, replacement: Order) -> Optional[Order]:
        raise NotImplementedError

    @abstractmethod
    def open_orders(self) -> Iterable[Order]:
        raise NotImplementedError

    def account_snapshot(self) -> BrokerAccountSnapshot:
        raise NotImplementedError("Broker adapter does not support account snapshots yet.")

    def positions(self) -> Iterable[BrokerPositionSnapshot]:
        raise NotImplementedError("Broker adapter does not support position snapshots yet.")

    def execution_reports(self) -> Iterable[ExecutionReport]:
        return []

    def sync_snapshot(self) -> BrokerSyncSnapshot:
        return BrokerSyncSnapshot(
            account=self.account_snapshot(),
            positions=list(self.positions()),
            open_orders=list(self.open_orders()),
            reports=list(self.execution_reports()),
        )
