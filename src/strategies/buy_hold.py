from dataclasses import dataclass

import pandas as pd

from src.models import Signal
from src.strategies.base import Strategy


@dataclass
class BuyAndHoldStrategy(Strategy):
    """MVP strategy that buys once and lets the engine force-flat at the end."""

    symbol: str
    stop_percent: float = 0.05

    def __post_init__(self) -> None:
        Strategy.__init__(self, self.symbol)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        signals = []
        for index, timestamp in enumerate(df.index):
            ts = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
            if index == 0:
                price = float(df.loc[timestamp, "Close"])
                signals.append(
                    Signal(
                        action="BUY",
                        symbol=self.symbol,
                        timestamp=ts,
                        stop_loss=price * (1 - self.stop_percent),
                    )
                )
            else:
                signals.append(Signal.hold(self.symbol, ts))
        return pd.Series(signals, index=df.index, dtype=object)
