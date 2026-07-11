import numpy as np
import pandas as pd

from src.indicators.core.base import Indicator


class FairValueGap(Indicator):
    """Three-bar imbalance detector inspired by fair value gap concepts."""

    required_columns = ("High", "Low", "Close")

    def calculate_all(self) -> pd.DataFrame:
        high_two_back = self.df["High"].shift(2)
        low_two_back = self.df["Low"].shift(2)
        bullish = self.df["Low"] > high_two_back
        bearish = self.df["High"] < low_two_back
        gap_top = pd.Series(np.nan, index=self.df.index, dtype="float64")
        gap_bottom = pd.Series(np.nan, index=self.df.index, dtype="float64")
        gap_top = gap_top.mask(bullish, self.df["Low"]).mask(bearish, low_two_back)
        gap_bottom = gap_bottom.mask(bullish, high_two_back).mask(bearish, self.df["High"])
        midpoint = (gap_top + gap_bottom) / 2
        size = (gap_top - gap_bottom).abs()
        direction = pd.Series(0, index=self.df.index, dtype="int64").mask(bullish, 1).mask(bearish, -1)
        return pd.DataFrame(
            {
                "BullishFVG": bullish.fillna(False),
                "BearishFVG": bearish.fillna(False),
                "FVGDirection": direction,
                "FVGTop": gap_top,
                "FVGBottom": gap_bottom,
                "FVGMidpoint": midpoint,
                "FVGSize": size,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["FVGDirection"].rename("FVGDirection")


class SwingPoints(Indicator):
    """Centered swing-high/swing-low detector."""

    required_columns = ("High", "Low")

    def __init__(self, df: pd.DataFrame, left_bars: int = 2, right_bars: int = 2):
        super().__init__(df)
        self.left_bars = left_bars
        self.right_bars = right_bars

    def calculate_all(self) -> pd.DataFrame:
        window = self.left_bars + self.right_bars + 1
        high_max = self.df["High"].rolling(window, center=True, min_periods=window).max()
        low_min = self.df["Low"].rolling(window, center=True, min_periods=window).min()
        swing_high = self.df["High"].eq(high_max).fillna(False)
        swing_low = self.df["Low"].eq(low_min).fillna(False)
        return pd.DataFrame(
            {
                "SwingHigh": swing_high,
                "SwingLow": swing_low,
                "SwingHighPrice": self.df["High"].where(swing_high),
                "SwingLowPrice": self.df["Low"].where(swing_low),
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        all_points = self.calculate_all()
        return (all_points["SwingHigh"].astype(int) - all_points["SwingLow"].astype(int)).rename("SwingPoint")


class LiquiditySweep(Indicator):
    """Detects wick sweeps through recent highs/lows that close back inside the range."""

    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, lookback: int = 20):
        super().__init__(df)
        self.lookback = lookback

    def calculate_all(self) -> pd.DataFrame:
        prior_high = self.df["High"].rolling(self.lookback, min_periods=self.lookback).max().shift(1)
        prior_low = self.df["Low"].rolling(self.lookback, min_periods=self.lookback).min().shift(1)
        bearish_sweep = (self.df["High"] > prior_high) & (self.df["Close"] < prior_high)
        bullish_sweep = (self.df["Low"] < prior_low) & (self.df["Close"] > prior_low)
        return pd.DataFrame(
            {
                "BullishLiquiditySweep": bullish_sweep.fillna(False),
                "BearishLiquiditySweep": bearish_sweep.fillna(False),
                "PriorRangeHigh": prior_high,
                "PriorRangeLow": prior_low,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        data = self.calculate_all()
        return (data["BullishLiquiditySweep"].astype(int) - data["BearishLiquiditySweep"].astype(int)).rename("LiquiditySweep")


class MarketStructureBreak(Indicator):
    """Close-based break above/below a rolling structure range."""

    required_columns = ("High", "Low", "Close")

    def __init__(self, df: pd.DataFrame, lookback: int = 20):
        super().__init__(df)
        self.lookback = lookback

    def calculate_all(self) -> pd.DataFrame:
        structure_high = self.df["High"].rolling(self.lookback, min_periods=self.lookback).max().shift(1)
        structure_low = self.df["Low"].rolling(self.lookback, min_periods=self.lookback).min().shift(1)
        bullish = self.df["Close"] > structure_high
        bearish = self.df["Close"] < structure_low
        return pd.DataFrame(
            {
                "BullishStructureBreak": bullish.fillna(False),
                "BearishStructureBreak": bearish.fillna(False),
                "StructureHigh": structure_high,
                "StructureLow": structure_low,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        data = self.calculate_all()
        return (data["BullishStructureBreak"].astype(int) - data["BearishStructureBreak"].astype(int)).rename("MarketStructureBreak")


class PivotPoints(Indicator):
    """Classic prior-bar pivot, support, and resistance levels."""

    required_columns = ("High", "Low", "Close")

    def calculate_all(self) -> pd.DataFrame:
        high = self.df["High"].shift(1)
        low = self.df["Low"].shift(1)
        close = self.df["Close"].shift(1)
        pivot = (high + low + close) / 3
        r1 = 2 * pivot - low
        s1 = 2 * pivot - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        return pd.DataFrame(
            {
                "Pivot": pivot,
                "R1": r1,
                "S1": s1,
                "R2": r2,
                "S2": s2,
            },
            index=self.df.index,
        )

    def calculate(self) -> pd.Series:
        return self.calculate_all()["Pivot"].rename("Pivot")
