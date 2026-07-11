import numpy as np
import pandas as pd

from src.indicators.core.base import Indicator
from src.indicators.volatility.atr import true_range


class Aroon(Indicator):
    required_columns = ("High", "Low")

    def __init__(self, df: pd.DataFrame, period: int = 25):
        super().__init__(df)
        self.period = period

    def calculate_all(self) -> pd.DataFrame:
        def up(values):
            return 100 * (np.argmax(values) + 1) / len(values)

        def down(values):
            return 100 * (np.argmin(values) + 1) / len(values)

        aroon_up = self.df["High"].rolling(self.period, min_periods=self.period).apply(up, raw=True)
        aroon_down = self.df["Low"].rolling(self.period, min_periods=self.period).apply(down, raw=True)
        return pd.DataFrame(
            {
                "AroonUp": aroon_up,
                "AroonDown": aroon_down,
                "AroonOscillator": aroon_up - aroon_down,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["AroonOscillator"].rename("AroonOscillator")


class VortexIndicator(Indicator):
    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, period: int = 14):
        super().__init__(df)
        self.period = period

    def calculate_all(self) -> pd.DataFrame:
        vm_plus = (self.df["High"] - self.df["Low"].shift(1)).abs()
        vm_minus = (self.df["Low"] - self.df["High"].shift(1)).abs()
        tr = true_range(self.df)
        tr_sum = tr.rolling(self.period, min_periods=self.period).sum().replace(0, pd.NA)
        vi_plus = vm_plus.rolling(self.period, min_periods=self.period).sum() / tr_sum
        vi_minus = vm_minus.rolling(self.period, min_periods=self.period).sum() / tr_sum
        return pd.DataFrame(
            {
                "VIPlus": vi_plus,
                "VIMinus": vi_minus,
                "VIDiff": vi_plus - vi_minus,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["VIDiff"].rename("VIDiff")


class ChoppinessIndex(Indicator):
    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, period: int = 14):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        tr_sum = true_range(self.df).rolling(self.period, min_periods=self.period).sum()
        high_max = self.df["High"].rolling(self.period, min_periods=self.period).max()
        low_min = self.df["Low"].rolling(self.period, min_periods=self.period).min()
        denominator = (high_max - low_min).replace(0, pd.NA)
        chop = 100 * np.log10(tr_sum / denominator) / np.log10(self.period)
        return chop.rename("ChoppinessIndex")


class EfficiencyRatio(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, period: int = 20):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        direction = (self.df["Close"] - self.df["Close"].shift(self.period)).abs()
        volatility = self.df["Close"].diff().abs().rolling(self.period, min_periods=self.period).sum()
        return (direction / volatility.replace(0, pd.NA)).rename("EfficiencyRatio")


class UlcerIndex(Indicator):
    required_columns = ("Close",)

    def __init__(self, df: pd.DataFrame, period: int = 14):
        super().__init__(df)
        self.period = period

    def calculate(self) -> pd.Series:
        rolling_high = self.df["Close"].rolling(self.period, min_periods=self.period).max()
        drawdown_pct = 100 * (self.df["Close"] - rolling_high) / rolling_high.replace(0, pd.NA)
        ulcer = np.sqrt((drawdown_pct.pow(2)).rolling(self.period, min_periods=self.period).mean())
        return ulcer.rename("UlcerIndex")


class ElderRayIndex(Indicator):
    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, period: int = 13):
        super().__init__(df)
        self.period = period

    def calculate_all(self) -> pd.DataFrame:
        ema = self.df["Close"].ewm(span=self.period, adjust=False, min_periods=self.period).mean()
        bull_power = self.df["High"] - ema
        bear_power = self.df["Low"] - ema
        return pd.DataFrame(
            {
                "BullPower": bull_power,
                "BearPower": bear_power,
                "ElderRay": bull_power + bear_power,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["ElderRay"].rename("ElderRay")


class IchimokuCloud(Indicator):
    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, conversion_period: int = 9, base_period: int = 26, span_b_period: int = 52, displacement: int = 26):
        super().__init__(df)
        self.conversion_period = conversion_period
        self.base_period = base_period
        self.span_b_period = span_b_period
        self.displacement = displacement

    def calculate_all(self) -> pd.DataFrame:
        conversion = _midpoint(self.df, self.conversion_period)
        base = _midpoint(self.df, self.base_period)
        span_a = ((conversion + base) / 2).shift(self.displacement)
        span_b = _midpoint(self.df, self.span_b_period).shift(self.displacement)
        lagging = self.df["Close"].shift(-self.displacement)
        return pd.DataFrame(
            {
                "TenkanSen": conversion,
                "KijunSen": base,
                "SenkouSpanA": span_a,
                "SenkouSpanB": span_b,
                "ChikouSpan": lagging,
                "CloudBias": (span_a - span_b),
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["CloudBias"].rename("CloudBias")


def _midpoint(df: pd.DataFrame, period: int) -> pd.Series:
    high = df["High"].rolling(period, min_periods=period).max()
    low = df["Low"].rolling(period, min_periods=period).min()
    return (high + low) / 2
