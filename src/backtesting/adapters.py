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

        if signal.action not in ("BUY", "SELL") or signal.stop_loss is None:
            return []

        quantity = self.sizer.size_from_stop(
            PositionSizingRequest(
                equity=context.account.equity,
                entry_price=context.snapshot.close,
                stop_price=signal.stop_loss,
                risk_fraction=self.risk_fraction,
                buying_power=context.account.buying_power,
                allow_fractional=self.allow_fractional_shares,
            )
        )
        if quantity <= 0:
            return []
        return [Order(symbol=signal.symbol, side=signal.action, quantity=quantity)]
