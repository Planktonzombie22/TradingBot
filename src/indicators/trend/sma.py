import pandas as pd

from src.indicators.core.base import Indicator


class SMA(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, period: int):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        if self.period <= 0:
            raise ValueError("Indicator period must be positive.")
        return self.df["Close"].rolling(self.period).mean()
