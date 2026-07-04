import pandas as pd

from src.indicators.base import Indicator


class OBV(Indicator):
    required_columns = ("Close", "Volume")

    def calculate(self) -> pd.Series:
        direction = self.df["Close"].diff().fillna(0).apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
        return (direction * self.df["Volume"]).cumsum().rename("OBV")
