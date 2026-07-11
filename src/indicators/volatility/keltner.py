import pandas as pd

from src.indicators.core.base import Indicator
from src.indicators.volatility.atr import ATR


class KeltnerChannel(Indicator):
    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, ema_period: int = 20, atr_period: int = 14, atr_multiple: float = 2.0):
        super().__init__(df)
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.atr_multiple = atr_multiple

    def calculate_all(self) -> pd.DataFrame:
        middle = self.df["Close"].ewm(span=self.ema_period, adjust=False, min_periods=self.ema_period).mean()
        atr = ATR(self.df, period=self.atr_period).calculate()
        upper = middle + atr * self.atr_multiple
        lower = middle - atr * self.atr_multiple
        width = (upper - lower) / middle.replace(0, pd.NA)
        return pd.DataFrame(
            {
                "KeltnerMiddle": middle,
                "KeltnerUpper": upper,
                "KeltnerLower": lower,
                "KeltnerWidth": width,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["KeltnerMiddle"].rename("KeltnerMiddle")
