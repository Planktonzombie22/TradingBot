# cspell:words DEMA Supertrend
from typing import Optional

import pandas as pd

from src.indicators import ADX, ATR, DEMA, RSI, SuperTrend
from src.models import Signal
from src.strategies.base import Strategy


class TuffSystem(Strategy):
    def __init__(
        self,
        symbol: str,
        adx_minimum: int = 30,
        rsi_deviation: int = 5,
    ):
        super().__init__(symbol)
        self.adx_minimum = adx_minimum
        self.rsi_deviation = rsi_deviation
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        st = SuperTrend(df)
        self._indicators = pd.DataFrame(
            {
                "ATR": ATR(df).calculate(),
                "SuperTrend": st.calculate(),
                "SuperTrend_Flip": st.get_flip_signals(),
                "ADX": ADX(df).calculate(),
                "RSI": RSI(df).calculate(),
                "DEMA": DEMA(df).calculate(),
            },
            index=df.index,
        )
        return self._indicators

    @property
    def indicators(self) -> pd.DataFrame:
        if self._indicators is None:
            return pd.DataFrame()
        return self._indicators

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        indicators = self._compute_indicators(df)
        close = df["Close"]

        # Prior-bar values avoid lookahead; act on the signal bar at its close.
        ind = indicators.shift(1)
        prev_close = close.shift(1)
        flip = indicators["SuperTrend_Flip"].shift(1).eq(True).fillna(False)
        stop = indicators["SuperTrend"].shift(1)

        long_entry = (
            (prev_close > ind["DEMA"])
            & (ind["RSI"] > 50 + self.rsi_deviation)
            & (ind["ADX"] > self.adx_minimum)
            & (ind["ATR"] > 0)
            & (ind["SuperTrend"] < prev_close)
        ).fillna(False)

        short_entry = (
            (prev_close < ind["DEMA"])
            & (ind["RSI"] < 50 - self.rsi_deviation)
            & (ind["ADX"] > self.adx_minimum)
            & (ind["ATR"] > 0)
            & (ind["SuperTrend"] > prev_close)
        ).fillna(False)

        signals = []
        for ts in df.index:
            stop_loss = stop[ts] if pd.notna(stop[ts]) else None

            if flip[ts]:
                action = "CLOSE"
            elif long_entry[ts]:
                action = "BUY"
            elif short_entry[ts]:
                action = "SELL"
            else:
                action = "HOLD"

            signals.append(
                Signal(
                    action=action,
                    symbol=self.symbol,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    stop_loss=float(stop_loss) if action in ("BUY", "SELL") and stop_loss is not None else None,
                )
            )

        return pd.Series(signals, index=df.index, dtype=object)
