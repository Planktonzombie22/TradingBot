from dataclasses import dataclass

import pandas as pd

from src.models import Signal

from .base import Strategy


@dataclass
class PublishedSmaCrossStrategy(Strategy):
    """Replication target for the backtesting.py quick-start SMA crossover."""

    symbol: str
    fast_period: int = 10
    slow_period: int = 20
    target_fraction: float = 1.0
    signal_delay_bars: int = 1
    commission_bps: float = 0.0

    def __post_init__(self) -> None:
        Strategy.__init__(self, self.symbol)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["Close"]
        fast = close.rolling(self.fast_period).mean()
        slow = close.rolling(self.slow_period).mean()
        cross_up = (fast.shift(1) <= slow.shift(1)) & (fast > slow)
        cross_down = (fast.shift(1) >= slow.shift(1)) & (fast < slow)

        signals = [Signal.hold(self.symbol, timestamp) for timestamp in df.index]
        for index, timestamp in enumerate(df.index):
            source_index = index - self.signal_delay_bars
            if source_index < 0:
                continue
            source_timestamp = df.index[source_index]
            if bool(cross_up.loc[source_timestamp]):
                signals[index] = Signal(
                    action="BUY",
                    symbol=self.symbol,
                    timestamp=timestamp,
                    meta={"target_position_fraction": self.target_fraction, "commission_bps": self.commission_bps},
                )
            elif bool(cross_down.loc[source_timestamp]):
                signals[index] = Signal(
                    action="SELL",
                    symbol=self.symbol,
                    timestamp=timestamp,
                    meta={"target_position_fraction": -self.target_fraction, "commission_bps": self.commission_bps},
                )
        return pd.Series(signals, index=df.index, dtype=object)
