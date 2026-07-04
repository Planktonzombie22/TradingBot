import pandas as pd

from src.indicators.base import Indicator


class StochasticOscillator(Indicator):
    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
        super().__init__(df)
        self.k_period = k_period
        self.d_period = d_period

    def calculate_all(self) -> pd.DataFrame:
        lowest_low = self.df["Low"].rolling(self.k_period, min_periods=self.k_period).min()
        highest_high = self.df["High"].rolling(self.k_period, min_periods=self.k_period).max()
        percent_k = 100 * (self.df["Close"] - lowest_low) / (highest_high - lowest_low).replace(0, pd.NA)
        percent_d = percent_k.rolling(self.d_period, min_periods=self.d_period).mean()
        return pd.DataFrame(
            {
                "StochK": percent_k,
                "StochD": percent_d,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["StochK"].rename("StochK")
