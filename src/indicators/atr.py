from typing import Optional, Tuple

import pandas as pd

from src.indicators.base import Indicator
from src.indicators._smoothing import wilder_rma


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    return pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1).rename("TR")


class ATR(Indicator):
    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, period: Optional[int] = None):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        period = self.period
        if period is None:
            from src.config import settings as cfg

            period = cfg.ATR_PERIOD

        return wilder_rma(true_range(self.df), period).rename("ATR")

    def calculate_with_tr(self) -> Tuple[pd.Series, pd.Series]:
        tr = true_range(self.df)
        period = self.period
        if period is None:
            from src.config import settings as cfg

            period = cfg.ATR_PERIOD
        return tr, wilder_rma(tr, period).rename("ATR")
