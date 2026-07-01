from abc import ABC, abstractmethod
from typing import Iterable, Optional

from src.models import Order


class Broker(ABC):
    """Broker contract shared by paper, backtest, and future live adapters."""

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> Optional[Order]:
        raise NotImplementedError

    @abstractmethod
    def open_orders(self) -> Iterable[Order]:
        raise NotImplementedError
