from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from src.models import Order, Signal
from src.risk import PositionSizer, PositionSizingRequest
from src.strategies.base import Strategy

from .interfaces import OrderFactory, SignalProvider
from .types import AccountSnapshot, MarketSnapshot, SignalContext


@dataclass
class PandasStrategySignalProvider(SignalProvider):
    """Adapts the current vectorized Strategy contract to event-style simulation."""

    strategy: Strategy
    bars: pd.DataFrame

    def __post_init__(self) -> None:
        self._signals = self.strategy.generate_signals(self.bars)

    def signal_for(self, snapshot: MarketSnapshot, account: AccountSnapshot) -> Signal:
        try:
            return self._signals.loc[snapshot.timestamp]
        except KeyError:
            ts = pd.Timestamp(snapshot.timestamp)
            return self._signals.loc[ts]


@dataclass(frozen=True)
class RiskPercentOrderFactory(OrderFactory):
    """Creates market orders sized from stop distance and account risk."""

    risk_fraction: float
    margin_ratio: float
    allow_fractional_shares: bool = True
    price_column: str = "Close"
    sizer: PositionSizer = PositionSizer()

    def create_orders(self, context: SignalContext) -> Sequence[Order]:
        signal = context.signal
        if signal.action == "HOLD":
            return []

        if signal.action == "CLOSE":
            quantity = abs(context.account.positions.get(signal.symbol, 0.0))
            if quantity <= 0:
                return []
            side = "SELL" if context.account.positions[signal.symbol] > 0 else "BUY"
            return [Order(symbol=signal.symbol, side=side, quantity=quantity)]

        if signal.action not in ("BUY", "SELL"):
            return []

        target_position_fraction = signal.meta.get("target_position_fraction")
        if target_position_fraction is not None:
            return self._target_position_orders(context, float(target_position_fraction))

        if signal.stop_loss is None:
            target_fraction = signal.meta.get("target_notional_fraction")
            if target_fraction is None:
                return []
            target_notional = context.account.equity * float(target_fraction)
            if context.account.buying_power is not None:
                target_notional = min(target_notional, context.account.buying_power)
            target_notional = self._commission_adjusted_notional(signal, target_notional)
            price = context.snapshot.price(self.price_column)
            quantity = target_notional / price if price > 0 else 0.0
            if not self.allow_fractional_shares:
                quantity = int(quantity)
            if quantity <= 0:
                return []
            return [Order(symbol=signal.symbol, side=signal.action, quantity=quantity)]

        quantity = self.sizer.size_from_stop(
            PositionSizingRequest(
                equity=context.account.equity,
                entry_price=context.snapshot.price(self.price_column),
                stop_price=signal.stop_loss,
                risk_fraction=self.risk_fraction,
                buying_power=context.account.buying_power,
                allow_fractional=self.allow_fractional_shares,
            )
        )
        if quantity <= 0:
            return []
        return [Order(symbol=signal.symbol, side=signal.action, quantity=quantity, stop_price=signal.stop_loss)]

    def _target_position_orders(self, context: SignalContext, target_fraction: float) -> Sequence[Order]:
        price = context.snapshot.price(self.price_column)
        if price <= 0:
            return []

        current_quantity = context.account.positions.get(context.signal.symbol, 0.0)
        target_notional = self._commission_adjusted_notional(context.signal, context.account.equity * target_fraction)
        target_quantity = target_notional / price
        orders = []

        if current_quantity and target_quantity and (current_quantity > 0) != (target_quantity > 0):
            close_side = "SELL" if current_quantity > 0 else "BUY"
            orders.append(Order(symbol=context.signal.symbol, side=close_side, quantity=abs(current_quantity)))
            entry_quantity = abs(target_quantity)
            if not self.allow_fractional_shares:
                entry_quantity = int(entry_quantity)
            if entry_quantity > 0:
                entry_side = "BUY" if target_quantity > 0 else "SELL"
                orders.append(Order(symbol=context.signal.symbol, side=entry_side, quantity=entry_quantity))
            return orders

        delta_quantity = target_quantity - current_quantity
        if not self.allow_fractional_shares:
            delta_quantity = int(delta_quantity)
        if abs(delta_quantity) <= 0:
            return orders
        side = "BUY" if delta_quantity > 0 else "SELL"
        orders.append(Order(symbol=context.signal.symbol, side=side, quantity=abs(delta_quantity)))
        return orders

    @staticmethod
    def _commission_adjusted_notional(signal: Signal, target_notional: float) -> float:
        commission_bps = float(signal.meta.get("commission_bps", 0.0))
        if commission_bps <= 0:
            return target_notional
        return target_notional / (1 + commission_bps / 10_000)
