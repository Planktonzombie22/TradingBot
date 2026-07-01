from typing import Optional

import pandas as pd


class DEMA:
    def __init__(self, df: pd.DataFrame, period: Optional[int] = None):
        self.df = df
        self.period = period

    def calculate(self) -> pd.Series:
        period = self.period
        if period is None:
            from src.config import settings as cfg

            period = cfg.DEMA_PERIOD

        ema1 = self.df["Close"].ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        return (2 * ema1 - ema2).rename("DEMA")
