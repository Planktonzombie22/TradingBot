from typing import Optional

import pandas as pd

from src.indicators._smoothing import ema
from src.indicators.base import Indicator


class DEMA(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, period: Optional[int] = None):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        period = self.period
        if period is None:
            from src.config import settings as cfg

            period = cfg.DEMA_PERIOD

        ema1 = ema(self.df["Close"], period)
        ema2 = ema(ema1, period)
        return (2 * ema1 - ema2).rename("DEMA")
