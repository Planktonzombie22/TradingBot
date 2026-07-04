from dataclasses import dataclass
from typing import Iterable, Sequence
from uuid import uuid4

from src.models import Order


@dataclass(frozen=True)
class BrokerCapabilityProfile:
    supports_bracket: bool = True
    supports_oco: bool = True
    supports_stop_limit: bool = True
    supports_trailing_stop: bool = True


@dataclass(frozen=True)
class BracketOrderPlan:
    entry: Order
    stop_loss: Order
    take_profit: Order

    @classmethod
    def market_entry(
        cls,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        take_profit_price: float,
    ) -> "BracketOrderPlan":
        group_id = str(uuid4())
        exit_side = "SELL" if side == "BUY" else "BUY"
        entry = Order(symbol=symbol, side=side, quantity=quantity, order_group_id=group_id)
        stop = Order(symbol=symbol, side=exit_side, quantity=quantity, order_type="STOP", stop_price=stop_price, parent_order_id=entry.id, order_group_id=group_id)
        target = Order(symbol=symbol, side=exit_side, quantity=quantity, order_type="LIMIT", limit_price=take_profit_price, parent_order_id=entry.id, order_group_id=group_id)
        return cls(entry, stop, target)

    def orders(self) -> Sequence[Order]:
        return [self.entry, self.stop_loss, self.take_profit]

    def validate(self, capabilities: BrokerCapabilityProfile) -> None:
        if not capabilities.supports_bracket:
            raise ValueError("Broker does not support bracket orders.")


@dataclass(frozen=True)
class OCOOrderPlan:
    orders: Sequence[Order]

    def validate(self, capabilities: BrokerCapabilityProfile) -> None:
        if not capabilities.supports_oco:
            raise ValueError("Broker does not support OCO orders.")
        if len(self.orders) < 2:
            raise ValueError("OCO plan requires at least two orders.")


def validate_order_capabilities(orders: Iterable[Order], capabilities: BrokerCapabilityProfile) -> None:
    for order in orders:
        if order.order_type == "STOP_LIMIT" and not capabilities.supports_stop_limit:
            raise ValueError("Broker does not support stop-limit orders.")
        if order.order_type == "TRAILING_STOP" and not capabilities.supports_trailing_stop:
            raise ValueError("Broker does not support trailing-stop orders.")
