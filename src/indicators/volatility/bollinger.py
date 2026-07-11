import pandas as pd

from src.indicators.core.base import Indicator


class BollingerBands(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, period: int = 20, standard_deviations: float = 2.0):
        super().__init__(df)
        self.period = period
        self.standard_deviations = standard_deviations

    def calculate_all(self) -> pd.DataFrame:
        close = self.df["Close"]
        middle = close.rolling(self.period, min_periods=self.period).mean()
        std = close.rolling(self.period, min_periods=self.period).std(ddof=0)
        upper = middle + std * self.standard_deviations
        lower = middle - std * self.standard_deviations
        width = (upper - lower) / middle.replace(0, pd.NA)
        percent_b = (close - lower) / (upper - lower).replace(0, pd.NA)
        return pd.DataFrame(
            {
                "MiddleBand": middle,
                "UpperBand": upper,
                "LowerBand": lower,
                "BandWidth": width,
                "PercentB": percent_b,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["PercentB"].rename("PercentB")
