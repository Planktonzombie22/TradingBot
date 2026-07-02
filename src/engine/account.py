from dataclasses import dataclass, field
from typing import Dict

from src.models import Order


@dataclass
class RuntimePosition:
    symbol: str
    quantity: float
    average_price: float

    def market_value(self, price: float) -> float:
        return self.quantity * price


@dataclass
class PaperAccountState:
    """Minimal account ledger for stream/paper runtime fills."""

    initial_cash: float
    cash: float = field(init=False)
    realized_pnl: float = 0.0
    positions: Dict[str, RuntimePosition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    def quantity(self, symbol: str) -> float:
        position = self.positions.get(symbol)
        return position.quantity if position else 0.0

    def equity(self, prices: Dict[str, float]) -> float:
        return self.cash + sum(
            position.market_value(prices.get(symbol, position.average_price))
            for symbol, position in self.positions.items()
        )

    def apply_fill(self, order: Order, price: float) -> None:
        signed_quantity = order.quantity if order.side == "BUY" else -order.quantity
        self.cash -= signed_quantity * price

        position = self.positions.get(order.symbol)
        if position is None:
            self.positions[order.symbol] = RuntimePosition(order.symbol, signed_quantity, price)
            return

        if (position.quantity > 0) == (signed_quantity > 0):
            total_quantity = position.quantity + signed_quantity
            weighted_cost = position.average_price * abs(position.quantity) + price * abs(signed_quantity)
            position.quantity = total_quantity
            position.average_price = weighted_cost / abs(total_quantity)
            return

        closing_quantity = min(abs(position.quantity), abs(signed_quantity))
        direction = 1 if position.quantity > 0 else -1
        self.realized_pnl += closing_quantity * direction * (price - position.average_price)
        remaining_quantity = position.quantity + signed_quantity

        if remaining_quantity == 0:
            self.positions.pop(order.symbol, None)
        elif (remaining_quantity > 0) == (position.quantity > 0):
            position.quantity = remaining_quantity
        else:
            position.quantity = remaining_quantity
            position.average_price = price

    def snapshot(self, prices: Dict[str, float]) -> dict:
        return {
            "cash": self.cash,
            "equity": self.equity(prices),
            "realized_pnl": self.realized_pnl,
            "positions": {
                symbol: {
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "market_value": position.market_value(prices.get(symbol, position.average_price)),
                }
                for symbol, position in self.positions.items()
            },
        }
