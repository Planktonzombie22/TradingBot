import pandas as pd

from src.indicators.core.base import Indicator


class ROC(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, period: int = 20):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        roc = self.df["Close"].pct_change(self.period)
        return roc.rename("ROC")
