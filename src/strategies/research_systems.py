from typing import Optional

import pandas as pd

from src.indicators import ADX, ATR, BollingerBands, DonchianChannel, EMA, KeltnerChannel, MACD, ROC, RSI, RollingZScore, StochasticOscillator
from src.models import Signal
from src.strategies.base import Strategy


def _timestamp(value):
    return value.to_pydatetime() if hasattr(value, "to_pydatetime") else value


def _is_ready(*values) -> bool:
    return all(pd.notna(value) for value in values)


class MomentumRegimeSystem(Strategy):
    """Trend follower using EMA regime, MACD thrust, ROC confirmation, and ATR stops."""

    def __init__(
        self,
        symbol: str,
        fast_ema: int = 20,
        slow_ema: int = 50,
        roc_period: int = 20,
        min_roc: float = 0.0,
        atr_period: int = 14,
        atr_stop_multiple: float = 3.0,
    ):
        super().__init__(symbol)
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.roc_period = roc_period
        self.min_roc = min_roc
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        macd = MACD(df).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "FastEMA": EMA(df, self.fast_ema).calculate(),
                "SlowEMA": EMA(df, self.slow_ema).calculate(),
                "ROC": ROC(df, self.roc_period).calculate(),
                "ATR": ATR(df, self.atr_period).calculate(),
                "MACDHistogram": macd["MACDHistogram"],
            },
            index=df.index,
        )
        return self._indicators

    @property
    def indicators(self) -> pd.DataFrame:
        return self._indicators if self._indicators is not None else pd.DataFrame()

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ind = self._compute_indicators(df)
        signals = []
        position = 0

        for i, ts in enumerate(df.index):
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            prev2 = ind.iloc[i - 2]
            price = float(df["Close"].iloc[i - 1])
            atr = prev["ATR"]
            if not _is_ready(prev["FastEMA"], prev["SlowEMA"], prev["ROC"], prev["ATR"], prev["MACDHistogram"], prev2["MACDHistogram"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            long_regime = prev["FastEMA"] > prev["SlowEMA"] and prev["MACDHistogram"] > 0 and prev["ROC"] > self.min_roc
            short_regime = prev["FastEMA"] < prev["SlowEMA"] and prev["MACDHistogram"] < 0 and prev["ROC"] < -self.min_roc
            long_exit = position == 1 and (prev["FastEMA"] < prev["SlowEMA"] or prev["MACDHistogram"] < 0)
            short_exit = position == -1 and (prev["FastEMA"] > prev["SlowEMA"] or prev["MACDHistogram"] > 0)

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif position == 0 and long_regime and prev["MACDHistogram"] >= prev2["MACDHistogram"]:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(atr) * self.atr_stop_multiple))
            elif position == 0 and short_regime and prev["MACDHistogram"] <= prev2["MACDHistogram"]:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(atr) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class MeanReversionSystem(Strategy):
    """Fades stretched Bollinger/z-score moves with RSI and stochastic exhaustion filters."""

    def __init__(
        self,
        symbol: str,
        band_period: int = 20,
        band_deviation: float = 2.0,
        rsi_period: int = 14,
        oversold: int = 30,
        overbought: int = 70,
        min_zscore: float = 1.5,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.0,
    ):
        super().__init__(symbol)
        self.band_period = band_period
        self.band_deviation = band_deviation
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.min_zscore = min_zscore
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        bands = BollingerBands(df, self.band_period, self.band_deviation).calculate_all()
        stoch = StochasticOscillator(df).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "LowerBand": bands["LowerBand"],
                "MiddleBand": bands["MiddleBand"],
                "UpperBand": bands["UpperBand"],
                "PercentB": bands["PercentB"],
                "RSI": RSI(df, self.rsi_period).calculate(),
                "StochK": stoch["StochK"],
                "ZScore": RollingZScore(df, self.band_period).calculate(),
                "ATR": ATR(df, self.atr_period).calculate(),
            },
            index=df.index,
        )
        return self._indicators

    @property
    def indicators(self) -> pd.DataFrame:
        return self._indicators if self._indicators is not None else pd.DataFrame()

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ind = self._compute_indicators(df)
        signals = []
        position = 0

        for i, ts in enumerate(df.index):
            if i < 1:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["LowerBand"], prev["MiddleBand"], prev["UpperBand"], prev["RSI"], prev["ZScore"], prev["ATR"], prev["StochK"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            long_entry = price < prev["LowerBand"] and prev["RSI"] <= self.oversold and prev["ZScore"] <= -self.min_zscore and prev["StochK"] <= 35
            short_entry = price > prev["UpperBand"] and prev["RSI"] >= self.overbought and prev["ZScore"] >= self.min_zscore and prev["StochK"] >= 65
            long_exit = position == 1 and (price >= prev["MiddleBand"] or prev["RSI"] >= 50)
            short_exit = position == -1 and (price <= prev["MiddleBand"] or prev["RSI"] <= 50)

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif position == 0 and long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif position == 0 and short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class VolatilityBreakoutSystem(Strategy):
    """Donchian breakout system gated by ADX and volatility expansion."""

    def __init__(
        self,
        symbol: str,
        channel_period: int = 55,
        adx_period: int = 14,
        min_adx: int = 18,
        atr_period: int = 14,
        atr_stop_multiple: float = 3.0,
        min_channel_width: float = 0.02,
    ):
        super().__init__(symbol)
        self.channel_period = channel_period
        self.adx_period = adx_period
        self.min_adx = min_adx
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self.min_channel_width = min_channel_width
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        channel = DonchianChannel(df, self.channel_period).calculate_all()
        keltner = KeltnerChannel(df, ema_period=20, atr_period=self.atr_period, atr_multiple=2.0).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "DonchianUpper": channel["DonchianUpper"],
                "DonchianLower": channel["DonchianLower"],
                "DonchianMiddle": channel["DonchianMiddle"],
                "DonchianWidth": channel["DonchianWidth"],
                "KeltnerWidth": keltner["KeltnerWidth"],
                "ADX": ADX(df, self.adx_period).calculate(),
                "ATR": ATR(df, self.atr_period).calculate(),
            },
            index=df.index,
        )
        return self._indicators

    @property
    def indicators(self) -> pd.DataFrame:
        return self._indicators if self._indicators is not None else pd.DataFrame()

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ind = self._compute_indicators(df)
        channel_ex_breakout_bar = ind[["DonchianUpper", "DonchianLower"]].shift(1)
        signals = []
        position = 0

        for i, ts in enumerate(df.index):
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            prev_channel = channel_ex_breakout_bar.iloc[i - 1]
            prev2 = ind.iloc[i - 2]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev_channel["DonchianUpper"], prev_channel["DonchianLower"], prev["DonchianMiddle"], prev["DonchianWidth"], prev["KeltnerWidth"], prev["ADX"], prev["ATR"], prev2["KeltnerWidth"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            volatility_expanding = prev["DonchianWidth"] >= self.min_channel_width or prev["KeltnerWidth"] > prev2["KeltnerWidth"]
            trend_ready = prev["ADX"] >= self.min_adx and volatility_expanding
            long_entry = price > prev_channel["DonchianUpper"] and trend_ready
            short_entry = price < prev_channel["DonchianLower"] and trend_ready
            long_exit = position == 1 and price < prev["DonchianMiddle"]
            short_exit = position == -1 and price > prev["DonchianMiddle"]

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif position == 0 and long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif position == 0 and short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)
