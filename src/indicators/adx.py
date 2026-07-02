from typing import Optional

import numpy as np
import pandas as pd

from src.indicators._smoothing import wilder_rma
from src.indicators.atr import true_range
from src.indicators.base import Indicator


class ADX(Indicator):
    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, period: Optional[int] = None):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        period = self.period
        if period is None:
            from src.config import settings as cfg

            period = cfg.ADX_PERIOD

        up_move = self.df["High"] - self.df["High"].shift(1)
        down_move = self.df["Low"].shift(1) - self.df["Low"]

        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

        tr = true_range(self.df)
        atr = wilder_rma(tr, period)
        plus_di = 100 * wilder_rma(plus_dm, period) / atr.replace(0, np.nan)
        minus_di = 100 * wilder_rma(minus_dm, period) / atr.replace(0, np.nan)

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = wilder_rma(dx, period)
        return adx.rename("ADX")

    def calculate_all(self) -> pd.DataFrame:
        period = self.period
        if period is None:
            from src.config import settings as cfg

            period = cfg.ADX_PERIOD

        up_move = self.df["High"] - self.df["High"].shift(1)
        down_move = self.df["Low"].shift(1) - self.df["Low"]
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        atr = wilder_rma(true_range(self.df), period).replace(0, np.nan)
        plus_di = (100 * wilder_rma(plus_dm, period) / atr).rename("+DI")
        minus_di = (100 * wilder_rma(minus_dm, period) / atr).rename("-DI")
        dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).rename("DX")
        return pd.concat([plus_di, minus_di, dx, wilder_rma(dx, period).rename("ADX")], axis=1)
