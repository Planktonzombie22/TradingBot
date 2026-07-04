import pandas as pd

from src.indicators.base import Indicator


class MACD(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        super().__init__(df)
        if fast_period >= slow_period:
            raise ValueError("MACD fast_period must be less than slow_period.")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def calculate_all(self) -> pd.DataFrame:
        close = self.df["Close"]
        fast = close.ewm(span=self.fast_period, adjust=False, min_periods=self.fast_period).mean()
        slow = close.ewm(span=self.slow_period, adjust=False, min_periods=self.slow_period).mean()
        line = fast - slow
        signal = line.ewm(span=self.signal_period, adjust=False, min_periods=self.signal_period).mean()
        histogram = line - signal
        return pd.DataFrame(
            {
                "MACD": line,
                "MACDSignal": signal,
                "MACDHistogram": histogram,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["MACDHistogram"].rename("MACDHistogram")
