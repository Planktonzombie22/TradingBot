from typing import Optional

import pandas as pd

from src.indicators.base import Indicator


class EMA(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, period: int = 20, column: str = "Close"):
        self.column = column
        self.period = period
        super().__init__(df)

    def calculate(self) -> pd.Series:
        ema = self.df[self.column].ewm(span=self.period, adjust=False, min_periods=self.period).mean()
        return ema.rename(f"EMA_{self.period}")


class RollingZScore(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, period: int = 20, column: str = "Close"):
        self.column = column
        self.period = period
        super().__init__(df)

    def calculate(self) -> pd.Series:
        values = self.df[self.column]
        mean = values.rolling(self.period, min_periods=self.period).mean()
        std = values.rolling(self.period, min_periods=self.period).std(ddof=0)
        return ((values - mean) / std.replace(0, pd.NA)).rename("ZScore")
