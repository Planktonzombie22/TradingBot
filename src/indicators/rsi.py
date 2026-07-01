from typing import Optional

import pandas as pd

from src.indicators._smoothing import wilder_rma


class RSI:
    def __init__(self, df: pd.DataFrame, period: Optional[int] = None):
        self.df = df
        self.period = period

    def calculate(self) -> pd.Series:
        period = self.period
        if period is None:
            from src.config import settings as cfg

            period = cfg.RSI_PERIOD

        delta = self.df["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = wilder_rma(gain, period)
        avg_loss = wilder_rma(loss, period)
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return rsi.rename("RSI")
