from typing import Optional

import numpy as np
import pandas as pd

from src.indicators.atr import ATR
from src.indicators.base import Indicator


class SuperTrend(Indicator):
    """Standard SuperTrend with final upper/lower bands and direction tracking."""

    required_columns = ("High", "Low", "Close")

    def __init__(
        self,
        df: pd.DataFrame,
        period: Optional[int] = None,
        multiplier: Optional[float] = None,
    ):
        super().__init__(df)
        self.period = period
        self.multiplier = multiplier
        self._result: Optional[pd.DataFrame] = None

    def calculate(self) -> pd.Series:
        return self.calculate_all()["SuperTrend"]

    def calculate_all(self) -> pd.DataFrame:
        if self._result is not None:
            return self._result

        period = self.period
        multiplier = self.multiplier
        if period is None or multiplier is None:
            from src.config import settings as cfg

            period = period or cfg.SUPER_TREND_PERIOD
            multiplier = multiplier or cfg.SUPER_TREND_MULTIPLIER

        atr = ATR(self.df, period).calculate()
        hl2 = (self.df["High"] + self.df["Low"]) / 2
        basic_ub = hl2 + multiplier * atr
        basic_lb = hl2 - multiplier * atr

        n = len(self.df)
        final_ub = np.full(n, np.nan)
        final_lb = np.full(n, np.nan)
        direction = np.ones(n, dtype=int)
        st = np.full(n, np.nan)

        close = self.df["Close"].to_numpy()
        basic_ub_arr = basic_ub.to_numpy()
        basic_lb_arr = basic_lb.to_numpy()

        for i in range(n):
            if np.isnan(basic_ub_arr[i]) or np.isnan(basic_lb_arr[i]):
                continue

            if i == 0 or np.isnan(final_ub[i - 1]):
                final_ub[i] = basic_ub_arr[i]
                final_lb[i] = basic_lb_arr[i]
            else:
                final_ub[i] = (
                    basic_ub_arr[i]
                    if basic_ub_arr[i] < final_ub[i - 1] or close[i - 1] > final_ub[i - 1]
                    else final_ub[i - 1]
                )
                final_lb[i] = (
                    basic_lb_arr[i]
                    if basic_lb_arr[i] > final_lb[i - 1] or close[i - 1] < final_lb[i - 1]
                    else final_lb[i - 1]
                )

            if i == 0 or np.isnan(final_ub[i - 1]):
                direction[i] = 1
            elif close[i] > final_ub[i - 1]:
                direction[i] = 1
            elif close[i] < final_lb[i - 1]:
                direction[i] = -1
            else:
                direction[i] = direction[i - 1]

            st[i] = final_lb[i] if direction[i] == 1 else final_ub[i]

        self._result = pd.DataFrame(
            {
                "SuperTrend": st,
                "UpperBand": final_ub,
                "LowerBand": final_lb,
                "Direction": direction,
                "Flip": np.concatenate([[False], direction[1:] != direction[:-1]]),
            },
            index=self.df.index,
        )
        return self._result

    def get_flip_signals(self) -> pd.Series:
        return self.calculate_all()["Flip"]
