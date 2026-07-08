import numpy as np
import pandas as pd

from src.indicators.base import Indicator


def _typical_price(df: pd.DataFrame) -> pd.Series:
    return (df["High"] + df["Low"] + df["Close"]) / 3


class VWAP(Indicator):
    required_columns = ("High", "Low", "Close", "Volume")

    def calculate(self) -> pd.Series:
        typical = _typical_price(self.df)
        volume = self.df["Volume"].mask(self.df["Volume"] == 0, np.nan)
        return ((typical * volume).cumsum() / volume.cumsum()).rename("VWAP")


class AnchoredVWAP(Indicator):
    required_columns = ("High", "Low", "Close", "Volume")

    def __init__(self, df: pd.DataFrame, anchor_index: int = 0):
        super().__init__(df)
        self.anchor_index = max(anchor_index, 0)

    def calculate(self) -> pd.Series:
        typical = _typical_price(self.df)
        volume = self.df["Volume"].mask(self.df["Volume"] == 0, np.nan)
        anchored_price_volume = (typical * volume).iloc[self.anchor_index :].cumsum()
        anchored_volume = volume.iloc[self.anchor_index :].cumsum()
        result = pd.Series(np.nan, index=self.df.index, dtype="float64")
        result.iloc[self.anchor_index :] = anchored_price_volume / anchored_volume
        return result.rename("AnchoredVWAP")


class MoneyFlowIndex(Indicator):
    required_columns = ("High", "Low", "Close", "Volume")

    def __init__(self, df: pd.DataFrame, period: int = 14):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        typical = _typical_price(self.df)
        raw_flow = typical * self.df["Volume"]
        positive = raw_flow.where(typical.diff() > 0, 0.0)
        negative = raw_flow.where(typical.diff() < 0, 0.0).abs()
        negative_sum = negative.rolling(self.period, min_periods=self.period).sum()
        ratio = positive.rolling(self.period, min_periods=self.period).sum() / negative_sum.mask(negative_sum == 0, np.nan)
        mfi = 100 - (100 / (1 + ratio))
        return mfi.rename("MFI")


class ChaikinMoneyFlow(Indicator):
    required_columns = ("High", "Low", "Close", "Volume")

    def __init__(self, df: pd.DataFrame, period: int = 20):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        high_low = self.df["High"] - self.df["Low"]
        high_low = high_low.mask(high_low == 0, np.nan)
        multiplier = ((self.df["Close"] - self.df["Low"]) - (self.df["High"] - self.df["Close"])) / high_low
        flow_volume = multiplier * self.df["Volume"]
        volume_sum = self.df["Volume"].rolling(self.period, min_periods=self.period).sum()
        cmf = flow_volume.rolling(self.period, min_periods=self.period).sum() / volume_sum.mask(volume_sum == 0, np.nan)
        return cmf.rename("CMF")


class RelativeVolume(Indicator):
    required_columns = ("Volume",)

    def __init__(self, df: pd.DataFrame, period: int = 20):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        average_volume = self.df["Volume"].rolling(self.period, min_periods=self.period).mean()
        return (self.df["Volume"] / average_volume.mask(average_volume == 0, np.nan)).rename("RelativeVolume")
