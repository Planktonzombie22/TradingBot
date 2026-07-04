import pandas as pd

from src.indicators.base import Indicator


class DonchianChannel(Indicator):
    required_columns = ("High", "Low")

    def __init__(self, df: pd.DataFrame, period: int = 20):
        super().__init__(df)
        self.period = period

    def calculate_all(self) -> pd.DataFrame:
        upper = self.df["High"].rolling(self.period, min_periods=self.period).max()
        lower = self.df["Low"].rolling(self.period, min_periods=self.period).min()
        middle = (upper + lower) / 2
        width = (upper - lower) / middle.replace(0, pd.NA)
        return pd.DataFrame(
            {
                "DonchianUpper": upper,
                "DonchianLower": lower,
                "DonchianMiddle": middle,
                "DonchianWidth": width,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["DonchianMiddle"].rename("DonchianMiddle")
