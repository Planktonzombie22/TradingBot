from dataclasses import dataclass, field
from typing import Dict, Optional

from src.models import Position, Trade

from .interfaces import PortfolioLedger
from .margin import SimpleMarginModel
from .types import AccountSnapshot, Fill


@dataclass
class PositionLot:
    symbol: str
    quantity: float
    average_price: float

    def mark_to_market(self, price: float) -> float:
        return self.quantity * price


@dataclass
class CashMarginLedger(PortfolioLedger):
    """Tracks cash, open lots, realized PnL, fees, and trade round trips."""

    initial_cash: float
    margin_model: SimpleMarginModel = field(default_factory=SimpleMarginModel)
    cash: float = field(init=False)
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    positions: Dict[str, PositionLot] = field(default_factory=dict)
    open_trades: Dict[str, Trade] = field(default_factory=dict)
    closed_trades: list[Trade] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    def snapshot(self, timestamp, prices: Optional[dict] = None) -> AccountSnapshot:
        prices = prices or {}
        position_values = {
            symbol: lot.mark_to_market(prices.get(symbol, lot.average_price))
            for symbol, lot in self.positions.items()
        }
        equity = self.cash + sum(position_values.values())
        used_margin = sum(abs(value) / max(self.margin_model.leverage, 1) for value in position_values.values())
        available_margin = max(equity - used_margin, 0.0)
        maintenance_margin = used_margin * self.margin_model.maintenance_rate
        return AccountSnapshot(
            timestamp=timestamp,
            cash=self.cash,
            equity=equity,
            buying_power=available_margin * self.margin_model.leverage,
            used_margin=used_margin,
            maintenance_margin=maintenance_margin,
            unrealized_pnl=sum(
                lot.quantity * (prices.get(symbol, lot.average_price) - lot.average_price)
                for symbol, lot in self.positions.items()
            ),
            realized_pnl=self.realized_pnl,
            fees_paid=self.fees_paid,
            positions={symbol: lot.quantity for symbol, lot in self.positions.items()},
        )

    def apply_fill(self, fill: Fill) -> None:
        signed_quantity = fill.quantity if fill.order.side == "BUY" else -fill.quantity
        cash_delta = -(signed_quantity * fill.price) - fill.commission
        self.cash += cash_delta
        self.fees_paid += fill.commission

        lot = self.positions.get(fill.order.symbol)
        if lot is None:
            self._open_lot(fill, signed_quantity)
            return

        if lot.quantity == 0 or (lot.quantity > 0) == (signed_quantity > 0):
            self._increase_lot(lot, signed_quantity, fill.price)
        else:
            self._reduce_or_reverse_lot(fill, lot, signed_quantity)

    def accrue_cost(self, amount: float, timestamp) -> None:
        self.cash -= amount
        self.fees_paid += max(amount, 0.0)

    def _open_lot(self, fill: Fill, signed_quantity: float) -> None:
        self.positions[fill.order.symbol] = PositionLot(
            symbol=fill.order.symbol,
            quantity=signed_quantity,
            average_price=fill.price,
        )
        side = "LONG" if signed_quantity > 0 else "SHORT"
        self.open_trades[fill.order.symbol] = Trade(
            symbol=fill.order.symbol,
            side=side,
            entry_time=fill.timestamp,
            entry_price=fill.price,
            shares=signed_quantity,
            entry_equity=self.cash + signed_quantity * fill.price,
        )

    def _increase_lot(self, lot: PositionLot, signed_quantity: float, price: float) -> None:
        total_quantity = lot.quantity + signed_quantity
        if total_quantity == 0:
            lot.average_price = price
            lot.quantity = 0.0
            return
        weighted_cost = lot.average_price * abs(lot.quantity) + price * abs(signed_quantity)
        lot.quantity = total_quantity
        lot.average_price = weighted_cost / abs(total_quantity)

    def _reduce_or_reverse_lot(self, fill: Fill, lot: PositionLot, signed_quantity: float) -> None:
        closing_quantity = min(abs(lot.quantity), abs(signed_quantity))
        direction = 1 if lot.quantity > 0 else -1
        pnl = closing_quantity * direction * (fill.price - lot.average_price)
        self.realized_pnl += pnl

        remaining_quantity = lot.quantity + signed_quantity
        trade = self.open_trades.get(fill.order.symbol)
        if trade and abs(remaining_quantity) < abs(lot.quantity):
            closed = trade.close(fill.timestamp, fill.price)
            self.closed_trades.append(closed)
            self.open_trades.pop(fill.order.symbol, None)

        if remaining_quantity == 0:
            self.positions.pop(fill.order.symbol, None)
        elif (remaining_quantity > 0) == (lot.quantity > 0):
            lot.quantity = remaining_quantity
        else:
            lot.quantity = remaining_quantity
            lot.average_price = fill.price
