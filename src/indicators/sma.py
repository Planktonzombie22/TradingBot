import pandas as pd

from src.config import settings as cfg
from src.indicators.base import Indicator


class SMA(Indicator):
    def __init__(self, df: pd.DataFrame, period: int):
        self.df = df.copy()
        self.period = period

    def calculate(self) -> pd.Series:
        return self.df["Close"].rolling(self.period).mean()
