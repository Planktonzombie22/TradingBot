from typing import Iterable, Optional

from src.config import AlpacaConfig
from src.models import Order

from .base import Broker
from ..lifecycle.reconciliation import BrokerAccountSnapshot, BrokerPositionSnapshot


class LockedAlpacaLiveBroker(Broker):
    """Explicit live broker boundary that refuses all live order operations until live trading is implemented."""

    def __init__(self, config: AlpacaConfig):
        self.config = config

    def submit_order(self, order: Order) -> Order:
        raise RuntimeError("Live Alpaca order submission is locked until the live adapter milestone is intentionally implemented.")

    def cancel_order(self, order_id: str) -> Optional[Order]:
        raise RuntimeError("Live Alpaca order cancellation is locked until the live adapter milestone is intentionally implemented.")

    def replace_order(self, order_id: str, replacement: Order) -> Optional[Order]:
        raise RuntimeError("Live Alpaca order replacement is locked until the live adapter milestone is intentionally implemented.")

    def open_orders(self) -> Iterable[Order]:
        raise RuntimeError("Live Alpaca order inspection is locked until the live adapter milestone is intentionally implemented.")

    def account_snapshot(self) -> BrokerAccountSnapshot:
        raise RuntimeError("Live Alpaca account inspection is locked until the live adapter milestone is intentionally implemented.")

    def positions(self) -> Iterable[BrokerPositionSnapshot]:
        raise RuntimeError("Live Alpaca position inspection is locked until the live adapter milestone is intentionally implemented.")
