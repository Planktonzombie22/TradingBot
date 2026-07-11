from typing import Optional

import pandas as pd

from src.indicators import (
    ADX,
    ATR,
    Aroon,
    AnchoredVWAP,
    BollingerBands,
    ChaikinMoneyFlow,
    ChoppinessIndex,
    DEMA,
    DonchianChannel,
    EMA,
    EfficiencyRatio,
    ElderRayIndex,
    FairValueGap,
    IchimokuCloud,
    KeltnerChannel,
    LiquiditySweep,
    MACD,
    MarketStructureBreak,
    MoneyFlowIndex,
    OBV,
    PivotPoints,
    ROC,
    RSI,
    RelativeVolume,
    RollingZScore,
    StochasticOscillator,
    SuperTrend,
    VortexIndicator,
)
from src.models import Signal
from src.strategies.core.base import Strategy


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


class ManagedFuturesMomentumSystem(Strategy):
    """Time-series momentum prototype with multi-lookback votes and volatility targeting.

    This is intentionally a single-symbol strategy boundary. Portfolio-level managed
    futures concerns such as asset-class risk budgets and correlation scaling belong
    above it in the allocation engine, while this class emits the clean target
    position intent that allocator/backtester layers can compose later.
    """

    def __init__(
        self,
        symbol: str,
        short_lookback: int = 21,
        medium_lookback: int = 63,
        long_lookback: int = 126,
        macro_lookback: int = 252,
        volatility_lookback: int = 63,
        target_volatility: float = 0.15,
        max_target_fraction: float = 1.0,
        min_signal_strength: float = 0.25,
        exit_threshold: float = 0.10,
        rebalance_interval: int = 21,
        rebalance_threshold: float = 0.10,
        atr_period: int = 20,
        atr_stop_multiple: float = 4.0,
        commission_bps: float = 0.0,
    ):
        super().__init__(symbol)
        self.short_lookback = short_lookback
        self.medium_lookback = medium_lookback
        self.long_lookback = long_lookback
        self.macro_lookback = macro_lookback
        self.volatility_lookback = volatility_lookback
        self.target_volatility = target_volatility
        self.max_target_fraction = max_target_fraction
        self.min_signal_strength = min_signal_strength
        self.exit_threshold = exit_threshold
        self.rebalance_interval = rebalance_interval
        self.rebalance_threshold = rebalance_threshold
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self.commission_bps = commission_bps
        self._indicators: Optional[pd.DataFrame] = None

    @property
    def lookbacks(self) -> tuple[int, ...]:
        values = {
            int(self.short_lookback),
            int(self.medium_lookback),
            int(self.long_lookback),
            int(self.macro_lookback),
        }
        return tuple(sorted(value for value in values if value > 0))

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        close = df["Close"]
        daily_returns = close.pct_change()
        realized_volatility = daily_returns.rolling(self.volatility_lookback).std() * (252**0.5)
        data = {
            "ATR": ATR(df, self.atr_period).calculate(),
            "RealizedVolatility": realized_volatility,
        }
        vote_columns = []
        strength_columns = []

        for lookback in self.lookbacks:
            momentum = close.pct_change(lookback)
            vote_column = f"Vote{lookback}"
            strength_column = f"Strength{lookback}"
            lookback_volatility = realized_volatility * ((lookback / 252) ** 0.5)
            data[vote_column] = momentum.apply(lambda value: 1.0 if value > 0 else -1.0 if value < 0 else 0.0)
            data[strength_column] = (momentum / lookback_volatility).clip(lower=-2.0, upper=2.0) / 2.0
            vote_columns.append(vote_column)
            strength_columns.append(strength_column)

        indicators = pd.DataFrame(data, index=df.index)
        indicators["TrendVote"] = indicators[vote_columns].mean(axis=1)
        indicators["TrendStrength"] = indicators[strength_columns].mean(axis=1)
        indicators["CompositeTrendScore"] = (0.70 * indicators["TrendVote"] + 0.30 * indicators["TrendStrength"]).clip(-1.0, 1.0)
        self._indicators = indicators
        return indicators

    @property
    def indicators(self) -> pd.DataFrame:
        return self._indicators if self._indicators is not None else pd.DataFrame()

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ind = self._compute_indicators(df)
        signals = []
        position = 0
        current_target = 0.0
        last_rebalance_index = -self.rebalance_interval
        readiness_columns = ["ATR", "RealizedVolatility", "CompositeTrendScore"]
        readiness_columns.extend(f"Vote{lookback}" for lookback in self.lookbacks)
        readiness_columns.extend(f"Strength{lookback}" for lookback in self.lookbacks)

        for i, ts in enumerate(df.index):
            if i < 1:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            if not _is_ready(*(prev[column] for column in readiness_columns)):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            price = float(df["Close"].iloc[i - 1])
            atr = float(prev["ATR"])
            score = float(prev["CompositeTrendScore"])
            realized_volatility = float(prev["RealizedVolatility"])
            target_fraction = self._target_fraction(score, realized_volatility)
            abs_score = abs(score)

            if position != 0 and abs_score <= self.exit_threshold:
                position = 0
                current_target = 0.0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts), meta=self._signal_meta(prev, 0.0, "trend_exit")))
                continue

            if abs_score < self.min_signal_strength or target_fraction == 0.0:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            desired_position = 1 if target_fraction > 0 else -1
            is_entry = position == 0
            is_reversal = position != 0 and desired_position != position
            is_rebalance = (
                position == desired_position
                and i - last_rebalance_index >= self.rebalance_interval
                and abs(target_fraction - current_target) >= self.rebalance_threshold
            )

            if not (is_entry or is_reversal or is_rebalance):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            position = desired_position
            current_target = target_fraction
            last_rebalance_index = i
            action = "BUY" if desired_position > 0 else "SELL"
            stop_loss = price - atr * self.atr_stop_multiple if desired_position > 0 else price + atr * self.atr_stop_multiple
            reason = "trend_entry" if is_entry else "trend_reversal" if is_reversal else "volatility_rebalance"
            signals.append(
                Signal(
                    action,
                    self.symbol,
                    _timestamp(ts),
                    stop_loss=stop_loss,
                    meta=self._signal_meta(prev, target_fraction, reason),
                )
            )

        return pd.Series(signals, index=df.index, dtype=object)

    def _target_fraction(self, score: float, realized_volatility: float) -> float:
        if realized_volatility <= 0 or pd.isna(realized_volatility):
            return 0.0
        volatility_scalar = self.target_volatility / realized_volatility
        target_size = min(self.max_target_fraction, max(0.0, volatility_scalar * abs(score)))
        return target_size if score > 0 else -target_size

    def _signal_meta(self, row: pd.Series, target_fraction: float, reason: str) -> dict:
        return {
            "target_position_fraction": target_fraction,
            "target_volatility": self.target_volatility,
            "realized_volatility": float(row["RealizedVolatility"]),
            "trend_vote": float(row["TrendVote"]),
            "trend_strength": float(row["TrendStrength"]),
            "composite_trend_score": float(row["CompositeTrendScore"]),
            "rebalance_reason": reason,
            "commission_bps": self.commission_bps,
        }


class CryptoAdaptiveTrendSystem(Strategy):
    """Crypto trend follower with rolling Sharpe, volatility sizing, and drawdown gates."""

    def __init__(
        self,
        symbol: str,
        fast_ema: int = 20,
        slow_ema: int = 80,
        momentum_lookback: int = 30,
        sharpe_lookback: int = 30,
        volatility_lookback: int = 30,
        drawdown_lookback: int = 90,
        annualization_bars: int = 365,
        target_volatility: float = 0.45,
        max_long_fraction: float = 1.0,
        max_short_fraction: float = 0.35,
        min_trend_score: float = 0.25,
        min_rolling_sharpe: float = 0.15,
        max_drawdown_gate: float = -0.45,
        trailing_atr_multiple: float = 3.0,
        atr_period: int = 14,
        rebalance_interval: int = 12,
        rebalance_threshold: float = 0.12,
        allow_short: bool = True,
        commission_bps: float = 5.0,
    ):
        super().__init__(symbol)
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.momentum_lookback = momentum_lookback
        self.sharpe_lookback = sharpe_lookback
        self.volatility_lookback = volatility_lookback
        self.drawdown_lookback = drawdown_lookback
        self.annualization_bars = annualization_bars
        self.target_volatility = target_volatility
        self.max_long_fraction = max_long_fraction
        self.max_short_fraction = max_short_fraction
        self.min_trend_score = min_trend_score
        self.min_rolling_sharpe = min_rolling_sharpe
        self.max_drawdown_gate = max_drawdown_gate
        self.trailing_atr_multiple = trailing_atr_multiple
        self.atr_period = atr_period
        self.rebalance_interval = rebalance_interval
        self.rebalance_threshold = rebalance_threshold
        self.allow_short = allow_short
        self.commission_bps = commission_bps
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        close = df["Close"].astype(float)
        returns = close.pct_change()
        rolling_return = returns.rolling(self.sharpe_lookback)
        rolling_vol = returns.rolling(self.volatility_lookback).std() * (self.annualization_bars**0.5)
        rolling_high = close.rolling(self.drawdown_lookback).max()
        fast = EMA(df, self.fast_ema).calculate()
        slow = EMA(df, self.slow_ema).calculate()
        momentum = close.pct_change(self.momentum_lookback)
        sharpe_vol = rolling_return.std()
        rolling_sharpe = (rolling_return.mean() / sharpe_vol.replace(0, pd.NA)) * (self.annualization_bars**0.5)
        ema_spread = ((fast / slow) - 1.0).clip(-1.0, 1.0)

        self._indicators = pd.DataFrame(
            {
                "FastEMA": fast,
                "SlowEMA": slow,
                "Momentum": momentum,
                "RollingSharpe": rolling_sharpe,
                "RealizedVolatility": rolling_vol,
                "Drawdown": close / rolling_high - 1.0,
                "ATR": ATR(df, self.atr_period).calculate(),
                "TrendScore": (0.60 * momentum.clip(-1.0, 1.0) + 0.40 * ema_spread).clip(-1.0, 1.0),
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
        current_target = 0.0
        trailing_stop: float | None = None
        extreme_price: float | None = None
        last_rebalance_index = -self.rebalance_interval

        for i, ts in enumerate(df.index):
            if i < 1:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(
                prev["FastEMA"],
                prev["SlowEMA"],
                prev["Momentum"],
                prev["RollingSharpe"],
                prev["RealizedVolatility"],
                prev["Drawdown"],
                prev["ATR"],
                prev["TrendScore"],
            ):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            atr = float(prev["ATR"])
            score = float(prev["TrendScore"])
            sharpe = float(prev["RollingSharpe"])
            drawdown = float(prev["Drawdown"])
            target_fraction = self._target_fraction(score, sharpe, float(prev["RealizedVolatility"]), drawdown)
            desired_position = 1 if target_fraction > 0 else -1 if target_fraction < 0 else 0

            if position != 0:
                extreme_price = self._updated_extreme(price, extreme_price, position)
                trailing_stop = self._trailing_stop(extreme_price, atr, position)
                if self._stop_hit(price, trailing_stop, position):
                    position = 0
                    current_target = 0.0
                    extreme_price = None
                    signals.append(Signal("CLOSE", self.symbol, _timestamp(ts), meta=self._signal_meta(prev, 0.0, "trailing_stop", trailing_stop)))
                    trailing_stop = None
                    continue

            if position > 0 and drawdown <= self.max_drawdown_gate:
                position = 0
                current_target = 0.0
                extreme_price = None
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts), meta=self._signal_meta(prev, 0.0, "drawdown_gate", trailing_stop)))
                trailing_stop = None
                continue

            if desired_position == 0:
                if position != 0 and abs(score) < self.min_trend_score * 0.5:
                    position = 0
                    current_target = 0.0
                    extreme_price = None
                    signals.append(Signal("CLOSE", self.symbol, _timestamp(ts), meta=self._signal_meta(prev, 0.0, "trend_decay", trailing_stop)))
                    trailing_stop = None
                    continue
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            is_entry = position == 0
            is_reversal = position != 0 and desired_position != position
            is_rebalance = (
                position == desired_position
                and i - last_rebalance_index >= self.rebalance_interval
                and abs(target_fraction - current_target) >= self.rebalance_threshold
            )
            if not (is_entry or is_reversal or is_rebalance):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            position = desired_position
            current_target = target_fraction
            last_rebalance_index = i
            extreme_price = price if is_entry or is_reversal or extreme_price is None else extreme_price
            trailing_stop = self._trailing_stop(extreme_price, atr, position)
            action = "BUY" if position > 0 else "SELL"
            reason = "trend_entry" if is_entry else "trend_reversal" if is_reversal else "volatility_rebalance"
            signals.append(
                Signal(
                    action,
                    self.symbol,
                    _timestamp(ts),
                    stop_loss=trailing_stop,
                    meta=self._signal_meta(prev, target_fraction, reason, trailing_stop),
                )
            )

        return pd.Series(signals, index=df.index, dtype=object)

    def _target_fraction(self, score: float, sharpe: float, realized_volatility: float, drawdown: float) -> float:
        if realized_volatility <= 0 or pd.isna(realized_volatility) or abs(score) < self.min_trend_score:
            return 0.0
        if drawdown <= self.max_drawdown_gate and score > 0:
            return 0.0
        if score > 0 and sharpe < self.min_rolling_sharpe:
            return 0.0
        if score < 0 and (not self.allow_short or sharpe > -self.min_rolling_sharpe):
            return 0.0

        cap = self.max_long_fraction if score > 0 else self.max_short_fraction
        volatility_scalar = self.target_volatility / realized_volatility
        target = min(cap, max(0.0, volatility_scalar * abs(score)))
        return target if score > 0 else -target

    def _signal_meta(self, row: pd.Series, target_fraction: float, reason: str, trailing_stop: float | None) -> dict:
        return {
            "target_position_fraction": target_fraction,
            "crypto_trend_score": float(row["TrendScore"]),
            "rolling_sharpe": float(row["RollingSharpe"]),
            "realized_volatility": float(row["RealizedVolatility"]),
            "drawdown": float(row["Drawdown"]),
            "trailing_stop": trailing_stop,
            "rebalance_reason": reason,
            "commission_bps": self.commission_bps,
        }

    @staticmethod
    def _updated_extreme(price: float, current: float | None, position: int) -> float:
        if current is None:
            return price
        return max(current, price) if position > 0 else min(current, price)

    def _trailing_stop(self, extreme_price: float | None, atr: float, position: int) -> float | None:
        if extreme_price is None or atr <= 0 or pd.isna(atr):
            return None
        if position > 0:
            return extreme_price - atr * self.trailing_atr_multiple
        return extreme_price + atr * self.trailing_atr_multiple

    @staticmethod
    def _stop_hit(price: float, trailing_stop: float | None, position: int) -> bool:
        if trailing_stop is None:
            return False
        return price <= trailing_stop if position > 0 else price >= trailing_stop


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


class TrendPullbackSystem(Strategy):
    """Trades pullbacks inside an established EMA trend instead of chasing breakouts."""

    def __init__(
        self,
        symbol: str,
        fast_ema: int = 20,
        slow_ema: int = 100,
        rsi_period: int = 14,
        pullback_rsi: int = 45,
        rebound_rsi: int = 55,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.5,
    ):
        super().__init__(symbol)
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period
        self.pullback_rsi = pullback_rsi
        self.rebound_rsi = rebound_rsi
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        self._indicators = pd.DataFrame(
            {
                "FastEMA": EMA(df, self.fast_ema).calculate(),
                "SlowEMA": EMA(df, self.slow_ema).calculate(),
                "RSI": RSI(df, self.rsi_period).calculate(),
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
        armed_long = False
        armed_short = False

        for i, ts in enumerate(df.index):
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            prev2 = ind.iloc[i - 2]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["FastEMA"], prev["SlowEMA"], prev["RSI"], prev["ATR"], prev2["RSI"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            uptrend = prev["FastEMA"] > prev["SlowEMA"] and price > prev["SlowEMA"]
            downtrend = prev["FastEMA"] < prev["SlowEMA"] and price < prev["SlowEMA"]
            if uptrend and prev["RSI"] <= self.pullback_rsi:
                armed_long = True
            if downtrend and prev["RSI"] >= 100 - self.pullback_rsi:
                armed_short = True

            long_exit = position == 1 and (prev["FastEMA"] < prev["SlowEMA"] or prev["RSI"] >= 70)
            short_exit = position == -1 and (prev["FastEMA"] > prev["SlowEMA"] or prev["RSI"] <= 30)
            long_entry = position == 0 and armed_long and uptrend and prev2["RSI"] < self.rebound_rsi <= prev["RSI"]
            short_entry = position == 0 and armed_short and downtrend and prev2["RSI"] > 100 - self.rebound_rsi >= prev["RSI"]

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                armed_long = False
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                armed_short = False
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class VolumeMomentumSystem(Strategy):
    """Combines price momentum with OBV confirmation and MACD direction."""

    def __init__(
        self,
        symbol: str,
        roc_period: int = 20,
        min_roc: float = 0.03,
        obv_ema_period: int = 20,
        atr_period: int = 14,
        atr_stop_multiple: float = 3.0,
    ):
        super().__init__(symbol)
        self.roc_period = roc_period
        self.min_roc = min_roc
        self.obv_ema_period = obv_ema_period
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        obv = OBV(df).calculate()
        macd = MACD(df).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "ROC": ROC(df, self.roc_period).calculate(),
                "OBV": obv,
                "OBVSignal": obv.ewm(span=self.obv_ema_period, adjust=False, min_periods=self.obv_ema_period).mean(),
                "MACDHistogram": macd["MACDHistogram"],
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
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            prev2 = ind.iloc[i - 2]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["ROC"], prev["OBV"], prev["OBVSignal"], prev["MACDHistogram"], prev["ATR"], prev2["OBV"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            obv_rising = prev["OBV"] > prev["OBVSignal"] and prev["OBV"] > prev2["OBV"]
            obv_falling = prev["OBV"] < prev["OBVSignal"] and prev["OBV"] < prev2["OBV"]
            long_entry = position == 0 and prev["ROC"] >= self.min_roc and prev["MACDHistogram"] > 0 and obv_rising
            short_entry = position == 0 and prev["ROC"] <= -self.min_roc and prev["MACDHistogram"] < 0 and obv_falling
            long_exit = position == 1 and (prev["MACDHistogram"] < 0 or prev["OBV"] < prev["OBVSignal"])
            short_exit = position == -1 and (prev["MACDHistogram"] > 0 or prev["OBV"] > prev["OBVSignal"])

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class SqueezeExpansionSystem(Strategy):
    """Looks for Bollinger/Keltner compression followed by directional expansion."""

    def __init__(
        self,
        symbol: str,
        band_period: int = 20,
        band_deviation: float = 2.0,
        keltner_multiple: float = 1.5,
        momentum_period: int = 20,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.5,
    ):
        super().__init__(symbol)
        self.band_period = band_period
        self.band_deviation = band_deviation
        self.keltner_multiple = keltner_multiple
        self.momentum_period = momentum_period
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        bands = BollingerBands(df, self.band_period, self.band_deviation).calculate_all()
        keltner = KeltnerChannel(df, ema_period=self.band_period, atr_period=self.atr_period, atr_multiple=self.keltner_multiple).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "UpperBand": bands["UpperBand"],
                "LowerBand": bands["LowerBand"],
                "BandWidth": bands["BandWidth"],
                "KeltnerUpper": keltner["KeltnerUpper"],
                "KeltnerLower": keltner["KeltnerLower"],
                "ROC": ROC(df, self.momentum_period).calculate(),
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
        squeezed = False

        for i, ts in enumerate(df.index):
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            prev2 = ind.iloc[i - 2]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["UpperBand"], prev["LowerBand"], prev["KeltnerUpper"], prev["KeltnerLower"], prev["ROC"], prev["ATR"], prev2["BandWidth"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            in_squeeze = prev["UpperBand"] < prev["KeltnerUpper"] and prev["LowerBand"] > prev["KeltnerLower"]
            squeezed = squeezed or bool(in_squeeze)
            expansion = squeezed and prev["BandWidth"] > prev2["BandWidth"]
            long_entry = position == 0 and expansion and price > prev["UpperBand"] and prev["ROC"] > 0
            short_entry = position == 0 and expansion and price < prev["LowerBand"] and prev["ROC"] < 0
            long_exit = position == 1 and (price < prev["LowerBand"] or prev["ROC"] < 0)
            short_exit = position == -1 and (price > prev["UpperBand"] or prev["ROC"] > 0)

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                squeezed = False
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                squeezed = False
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class TuffConsensusSystem(Strategy):
    """Tuff-inspired voting model across SuperTrend, DEMA, RSI, ADX, MACD, and ROC."""

    def __init__(
        self,
        symbol: str,
        adx_minimum: int = 18,
        vote_threshold: int = 4,
        rsi_deviation: int = 3,
        roc_period: int = 20,
        atr_stop_multiple: float = 2.5,
    ):
        super().__init__(symbol)
        self.adx_minimum = adx_minimum
        self.vote_threshold = vote_threshold
        self.rsi_deviation = rsi_deviation
        self.roc_period = roc_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        st = SuperTrend(df)
        macd = MACD(df).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "ATR": ATR(df).calculate(),
                "ADX": ADX(df).calculate(),
                "RSI": RSI(df).calculate(),
                "DEMA": DEMA(df).calculate(),
                "SuperTrend": st.calculate(),
                "SuperTrendFlip": st.get_flip_signals(),
                "MACDHistogram": macd["MACDHistogram"],
                "ROC": ROC(df, self.roc_period).calculate(),
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
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["ATR"], prev["ADX"], prev["RSI"], prev["DEMA"], prev["SuperTrend"], prev["MACDHistogram"], prev["ROC"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            long_votes = sum(
                [
                    price > prev["DEMA"],
                    prev["SuperTrend"] < price,
                    prev["RSI"] > 50 + self.rsi_deviation,
                    prev["ADX"] > self.adx_minimum,
                    prev["MACDHistogram"] > 0,
                    prev["ROC"] > 0,
                ]
            )
            short_votes = sum(
                [
                    price < prev["DEMA"],
                    prev["SuperTrend"] > price,
                    prev["RSI"] < 50 - self.rsi_deviation,
                    prev["ADX"] > self.adx_minimum,
                    prev["MACDHistogram"] < 0,
                    prev["ROC"] < 0,
                ]
            )
            long_entry = position == 0 and long_votes >= self.vote_threshold and long_votes > short_votes
            short_entry = position == 0 and short_votes >= self.vote_threshold and short_votes > long_votes
            long_exit = position == 1 and (short_votes >= self.vote_threshold or bool(prev["SuperTrendFlip"]))
            short_exit = position == -1 and (long_votes >= self.vote_threshold or bool(prev["SuperTrendFlip"]))

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                stop = min(float(prev["SuperTrend"]), price - float(prev["ATR"]) * self.atr_stop_multiple)
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=stop))
            elif short_entry:
                position = -1
                stop = max(float(prev["SuperTrend"]), price + float(prev["ATR"]) * self.atr_stop_multiple)
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=stop))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class TuffRegimeSwitchSystem(Strategy):
    """Switches between Tuff trend-following and volatility-band mean reversion by ADX regime."""

    def __init__(
        self,
        symbol: str,
        trend_adx: int = 22,
        range_adx: int = 18,
        rsi_deviation: int = 5,
        band_period: int = 20,
        band_deviation: float = 1.8,
        atr_stop_multiple: float = 2.0,
    ):
        super().__init__(symbol)
        self.trend_adx = trend_adx
        self.range_adx = range_adx
        self.rsi_deviation = rsi_deviation
        self.band_period = band_period
        self.band_deviation = band_deviation
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        st = SuperTrend(df)
        bands = BollingerBands(df, self.band_period, self.band_deviation).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "ATR": ATR(df).calculate(),
                "ADX": ADX(df).calculate(),
                "RSI": RSI(df).calculate(),
                "DEMA": DEMA(df).calculate(),
                "SuperTrend": st.calculate(),
                "SuperTrendFlip": st.get_flip_signals(),
                "LowerBand": bands["LowerBand"],
                "MiddleBand": bands["MiddleBand"],
                "UpperBand": bands["UpperBand"],
                "ZScore": RollingZScore(df, self.band_period).calculate(),
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
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["ATR"], prev["ADX"], prev["RSI"], prev["DEMA"], prev["SuperTrend"], prev["LowerBand"], prev["MiddleBand"], prev["UpperBand"], prev["ZScore"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            trend_mode = prev["ADX"] >= self.trend_adx
            range_mode = prev["ADX"] <= self.range_adx
            trend_long = trend_mode and price > prev["DEMA"] and prev["SuperTrend"] < price and prev["RSI"] > 50 + self.rsi_deviation
            trend_short = trend_mode and price < prev["DEMA"] and prev["SuperTrend"] > price and prev["RSI"] < 50 - self.rsi_deviation
            range_long = range_mode and price < prev["LowerBand"] and prev["RSI"] < 45 and prev["ZScore"] < -1
            range_short = range_mode and price > prev["UpperBand"] and prev["RSI"] > 55 and prev["ZScore"] > 1
            long_exit = position == 1 and (price >= prev["MiddleBand"] or bool(prev["SuperTrendFlip"]) or trend_short)
            short_exit = position == -1 and (price <= prev["MiddleBand"] or bool(prev["SuperTrendFlip"]) or trend_long)

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif position == 0 and (trend_long or range_long):
                position = 1
                stop = min(float(prev["SuperTrend"]), price - float(prev["ATR"]) * self.atr_stop_multiple)
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=stop))
            elif position == 0 and (trend_short or range_short):
                position = -1
                stop = max(float(prev["SuperTrend"]), price + float(prev["ATR"]) * self.atr_stop_multiple)
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=stop))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class TuffContrarianSystem(Strategy):
    """A deliberately weird anti-Tuff: fades mature Tuff thrusts when price is statistically stretched."""

    def __init__(
        self,
        symbol: str,
        adx_minimum: int = 25,
        rsi_extreme: int = 68,
        zscore_extreme: float = 1.5,
        band_period: int = 20,
        atr_stop_multiple: float = 1.8,
    ):
        super().__init__(symbol)
        self.adx_minimum = adx_minimum
        self.rsi_extreme = rsi_extreme
        self.zscore_extreme = zscore_extreme
        self.band_period = band_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        st = SuperTrend(df)
        bands = BollingerBands(df, self.band_period, 2.0).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "ATR": ATR(df).calculate(),
                "ADX": ADX(df).calculate(),
                "RSI": RSI(df).calculate(),
                "DEMA": DEMA(df).calculate(),
                "SuperTrend": st.calculate(),
                "SuperTrendFlip": st.get_flip_signals(),
                "MiddleBand": bands["MiddleBand"],
                "ZScore": RollingZScore(df, self.band_period).calculate(),
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
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["ATR"], prev["ADX"], prev["RSI"], prev["DEMA"], prev["SuperTrend"], prev["MiddleBand"], prev["ZScore"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            tuff_bull = price > prev["DEMA"] and prev["SuperTrend"] < price and prev["ADX"] >= self.adx_minimum
            tuff_bear = price < prev["DEMA"] and prev["SuperTrend"] > price and prev["ADX"] >= self.adx_minimum
            short_entry = position == 0 and tuff_bull and prev["RSI"] >= self.rsi_extreme and prev["ZScore"] >= self.zscore_extreme
            long_entry = position == 0 and tuff_bear and prev["RSI"] <= 100 - self.rsi_extreme and prev["ZScore"] <= -self.zscore_extreme
            long_exit = position == 1 and (price >= prev["MiddleBand"] or bool(prev["SuperTrendFlip"]))
            short_exit = position == -1 and (price <= prev["MiddleBand"] or bool(prev["SuperTrendFlip"]))

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class GapFadeSystem(Strategy):
    """Fades large overnight-style gaps when the prior bar closes back toward balance."""

    def __init__(
        self,
        symbol: str,
        gap_threshold: float = 0.015,
        rsi_period: int = 14,
        oversold: int = 35,
        overbought: int = 65,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.0,
    ):
        super().__init__(symbol)
        self.gap_threshold = gap_threshold
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        previous_close = df["Close"].shift(1)
        gap = (df["Open"] - previous_close) / previous_close.replace(0, pd.NA)
        close_location = (df["Close"] - df["Low"]) / (df["High"] - df["Low"]).replace(0, pd.NA)
        self._indicators = pd.DataFrame(
            {
                "Gap": gap,
                "CloseLocation": close_location,
                "RSI": RSI(df, self.rsi_period).calculate(),
                "ATR": ATR(df, self.atr_period).calculate(),
                "ZScore": RollingZScore(df, 20).calculate(),
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
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["Gap"], prev["CloseLocation"], prev["RSI"], prev["ATR"], prev["ZScore"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            gap_down_recovered = prev["Gap"] <= -self.gap_threshold and prev["CloseLocation"] >= 0.55 and prev["RSI"] <= self.oversold + 10
            gap_up_rejected = prev["Gap"] >= self.gap_threshold and prev["CloseLocation"] <= 0.45 and prev["RSI"] >= self.overbought - 10
            long_exit = position == 1 and (prev["ZScore"] >= 0 or prev["RSI"] >= 55)
            short_exit = position == -1 and (prev["ZScore"] <= 0 or prev["RSI"] <= 45)

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif position == 0 and gap_down_recovered:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif position == 0 and gap_up_rejected:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class SkewReversionSystem(Strategy):
    """Fades stretched returns when rolling return skew suggests one-sided exhaustion."""

    def __init__(
        self,
        symbol: str,
        lookback: int = 20,
        zscore_entry: float = 1.5,
        skew_threshold: float = 0.2,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.0,
    ):
        super().__init__(symbol)
        self.lookback = lookback
        self.zscore_entry = zscore_entry
        self.skew_threshold = skew_threshold
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        returns = df["Close"].pct_change()
        self._indicators = pd.DataFrame(
            {
                "ReturnZ": RollingZScore(pd.DataFrame({"Close": returns.fillna(0.0)}, index=df.index), self.lookback).calculate(),
                "Skew": returns.rolling(self.lookback, min_periods=self.lookback).skew(),
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
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["ReturnZ"], prev["Skew"], prev["ATR"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            long_entry = position == 0 and prev["ReturnZ"] <= -self.zscore_entry and prev["Skew"] <= -self.skew_threshold
            short_entry = position == 0 and prev["ReturnZ"] >= self.zscore_entry and prev["Skew"] >= self.skew_threshold
            long_exit = position == 1 and prev["ReturnZ"] >= 0
            short_exit = position == -1 and prev["ReturnZ"] <= 0

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))

        return pd.Series(signals, index=df.index, dtype=object)


class FVGRebalanceSystem(Strategy):
    """Trades fair value gap continuation after an imbalance appears."""

    def __init__(
        self,
        symbol: str,
        min_gap_atr: float = 0.15,
        rsi_floor: int = 48,
        atr_period: int = 14,
        atr_stop_multiple: float = 1.8,
    ):
        super().__init__(symbol)
        self.min_gap_atr = min_gap_atr
        self.rsi_floor = rsi_floor
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        fvg = FairValueGap(df).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "FVGDirection": fvg["FVGDirection"],
                "FVGTop": fvg["FVGTop"],
                "FVGBottom": fvg["FVGBottom"],
                "FVGMidpoint": fvg["FVGMidpoint"],
                "FVGSize": fvg["FVGSize"],
                "ATR": ATR(df, self.atr_period).calculate(),
                "RSI": RSI(df).calculate(),
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
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["FVGDirection"], prev["FVGSize"], prev["ATR"], prev["RSI"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue

            gap_big_enough = prev["FVGSize"] >= float(prev["ATR"]) * self.min_gap_atr
            long_entry = position == 0 and prev["FVGDirection"] > 0 and gap_big_enough and prev["RSI"] >= self.rsi_floor
            short_entry = position == 0 and prev["FVGDirection"] < 0 and gap_big_enough and prev["RSI"] <= 100 - self.rsi_floor
            long_exit = position == 1 and (prev["RSI"] < 50 or (pd.notna(prev["FVGTop"]) and price > prev["FVGTop"]))
            short_exit = position == -1 and (prev["RSI"] > 50 or (pd.notna(prev["FVGBottom"]) and price < prev["FVGBottom"]))

            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                stop = min(float(prev["FVGBottom"]) if pd.notna(prev["FVGBottom"]) else price, price - float(prev["ATR"]) * self.atr_stop_multiple)
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=stop))
            elif short_entry:
                position = -1
                stop = max(float(prev["FVGTop"]) if pd.notna(prev["FVGTop"]) else price, price + float(prev["ATR"]) * self.atr_stop_multiple)
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=stop))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
        return pd.Series(signals, index=df.index, dtype=object)


class LiquiditySweepReversalSystem(Strategy):
    """Reverses after wick sweeps of recent highs/lows with money-flow confirmation."""

    def __init__(
        self,
        symbol: str,
        sweep_lookback: int = 20,
        mfi_period: int = 14,
        mfi_extreme: int = 45,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.0,
    ):
        super().__init__(symbol)
        self.sweep_lookback = sweep_lookback
        self.mfi_period = mfi_period
        self.mfi_extreme = mfi_extreme
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        sweeps = LiquiditySweep(df, self.sweep_lookback).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "BullishSweep": sweeps["BullishLiquiditySweep"],
                "BearishSweep": sweeps["BearishLiquiditySweep"],
                "PriorHigh": sweeps["PriorRangeHigh"],
                "PriorLow": sweeps["PriorRangeLow"],
                "MFI": MoneyFlowIndex(df, self.mfi_period).calculate(),
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
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["MFI"], prev["ATR"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            long_entry = position == 0 and bool(prev["BullishSweep"]) and prev["MFI"] <= self.mfi_extreme
            short_entry = position == 0 and bool(prev["BearishSweep"]) and prev["MFI"] >= 100 - self.mfi_extreme
            long_exit = position == 1 and (prev["MFI"] >= 55 or (pd.notna(prev["PriorHigh"]) and price >= prev["PriorHigh"]))
            short_exit = position == -1 and (prev["MFI"] <= 45 or (pd.notna(prev["PriorLow"]) and price <= prev["PriorLow"]))
            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
        return pd.Series(signals, index=df.index, dtype=object)


class StructureBreakoutRetestSystem(Strategy):
    """Trades structure breaks when relative volume and pivots confirm direction."""

    def __init__(
        self,
        symbol: str,
        structure_lookback: int = 30,
        min_relative_volume: float = 1.1,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.5,
    ):
        super().__init__(symbol)
        self.structure_lookback = structure_lookback
        self.min_relative_volume = min_relative_volume
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        structure = MarketStructureBreak(df, self.structure_lookback).calculate_all()
        pivots = PivotPoints(df).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "BullishBreak": structure["BullishStructureBreak"],
                "BearishBreak": structure["BearishStructureBreak"],
                "StructureHigh": structure["StructureHigh"],
                "StructureLow": structure["StructureLow"],
                "Pivot": pivots["Pivot"],
                "RelativeVolume": RelativeVolume(df).calculate(),
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
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["RelativeVolume"], prev["ATR"], prev["Pivot"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            long_entry = position == 0 and bool(prev["BullishBreak"]) and prev["RelativeVolume"] >= self.min_relative_volume and price > prev["Pivot"]
            short_entry = position == 0 and bool(prev["BearishBreak"]) and prev["RelativeVolume"] >= self.min_relative_volume and price < prev["Pivot"]
            long_exit = position == 1 and price < prev["Pivot"]
            short_exit = position == -1 and price > prev["Pivot"]
            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                stop = min(float(prev["StructureHigh"]) if pd.notna(prev["StructureHigh"]) else price, price - float(prev["ATR"]) * self.atr_stop_multiple)
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=stop))
            elif short_entry:
                position = -1
                stop = max(float(prev["StructureLow"]) if pd.notna(prev["StructureLow"]) else price, price + float(prev["ATR"]) * self.atr_stop_multiple)
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=stop))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
        return pd.Series(signals, index=df.index, dtype=object)


class VWAPValueReversionSystem(Strategy):
    """Fades distance from anchored VWAP when money flow begins to mean-revert."""

    def __init__(
        self,
        symbol: str,
        distance_threshold: float = 0.04,
        cmf_period: int = 20,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.0,
    ):
        super().__init__(symbol)
        self.distance_threshold = distance_threshold
        self.cmf_period = cmf_period
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        avwap = AnchoredVWAP(df).calculate()
        self._indicators = pd.DataFrame(
            {
                "AnchoredVWAP": avwap,
                "Distance": (df["Close"] - avwap) / avwap.mask(avwap == 0),
                "CMF": ChaikinMoneyFlow(df, self.cmf_period).calculate(),
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
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["AnchoredVWAP"], prev["Distance"], prev["CMF"], prev["ATR"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            long_entry = position == 0 and prev["Distance"] <= -self.distance_threshold and prev["CMF"] > -0.1
            short_entry = position == 0 and prev["Distance"] >= self.distance_threshold and prev["CMF"] < 0.1
            long_exit = position == 1 and price >= prev["AnchoredVWAP"]
            short_exit = position == -1 and price <= prev["AnchoredVWAP"]
            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
        return pd.Series(signals, index=df.index, dtype=object)


class IchimokuCloudTrendSystem(Strategy):
    """Cloud trend follower using Tenkan/Kijun alignment and cloud bias."""

    def __init__(
        self,
        symbol: str,
        min_cloud_bias: float = 0.0,
        atr_period: int = 14,
        atr_stop_multiple: float = 3.0,
    ):
        super().__init__(symbol)
        self.min_cloud_bias = min_cloud_bias
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        cloud = IchimokuCloud(df).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "Tenkan": cloud["TenkanSen"],
                "Kijun": cloud["KijunSen"],
                "SpanA": cloud["SenkouSpanA"],
                "SpanB": cloud["SenkouSpanB"],
                "CloudBias": cloud["CloudBias"],
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
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["Tenkan"], prev["Kijun"], prev["SpanA"], prev["SpanB"], prev["CloudBias"], prev["ATR"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            cloud_top = max(float(prev["SpanA"]), float(prev["SpanB"]))
            cloud_bottom = min(float(prev["SpanA"]), float(prev["SpanB"]))
            long_entry = position == 0 and price > cloud_top and prev["Tenkan"] > prev["Kijun"] and prev["CloudBias"] > self.min_cloud_bias
            short_entry = position == 0 and price < cloud_bottom and prev["Tenkan"] < prev["Kijun"] and prev["CloudBias"] < -self.min_cloud_bias
            long_exit = position == 1 and (price < prev["Kijun"] or prev["Tenkan"] < prev["Kijun"])
            short_exit = position == -1 and (price > prev["Kijun"] or prev["Tenkan"] > prev["Kijun"])
            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
        return pd.Series(signals, index=df.index, dtype=object)


class ChoppinessRangeSystem(Strategy):
    """High-chop range trader using Bollinger extremes and Money Flow Index."""

    def __init__(
        self,
        symbol: str,
        chop_threshold: float = 55.0,
        band_period: int = 20,
        band_deviation: float = 2.0,
        mfi_extreme: int = 40,
        atr_period: int = 14,
        atr_stop_multiple: float = 1.8,
    ):
        super().__init__(symbol)
        self.chop_threshold = chop_threshold
        self.band_period = band_period
        self.band_deviation = band_deviation
        self.mfi_extreme = mfi_extreme
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        bands = BollingerBands(df, self.band_period, self.band_deviation).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "LowerBand": bands["LowerBand"],
                "MiddleBand": bands["MiddleBand"],
                "UpperBand": bands["UpperBand"],
                "Chop": ChoppinessIndex(df).calculate(),
                "MFI": MoneyFlowIndex(df).calculate(),
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
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["LowerBand"], prev["MiddleBand"], prev["UpperBand"], prev["Chop"], prev["MFI"], prev["ATR"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            range_mode = prev["Chop"] >= self.chop_threshold
            long_entry = position == 0 and range_mode and price < prev["LowerBand"] and prev["MFI"] <= self.mfi_extreme
            short_entry = position == 0 and range_mode and price > prev["UpperBand"] and prev["MFI"] >= 100 - self.mfi_extreme
            long_exit = position == 1 and price >= prev["MiddleBand"]
            short_exit = position == -1 and price <= prev["MiddleBand"]
            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
        return pd.Series(signals, index=df.index, dtype=object)


class AroonVortexTrendSystem(Strategy):
    """Regime momentum system requiring Aroon, Vortex, and Elder-Ray agreement."""

    def __init__(
        self,
        symbol: str,
        aroon_threshold: float = 20.0,
        vortex_threshold: float = 0.05,
        atr_period: int = 14,
        atr_stop_multiple: float = 2.8,
    ):
        super().__init__(symbol)
        self.aroon_threshold = aroon_threshold
        self.vortex_threshold = vortex_threshold
        self.atr_period = atr_period
        self.atr_stop_multiple = atr_stop_multiple
        self._indicators: Optional[pd.DataFrame] = None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._indicators is not None and len(self._indicators) == len(df):
            return self._indicators

        aroon = Aroon(df).calculate_all()
        vortex = VortexIndicator(df).calculate_all()
        elder = ElderRayIndex(df).calculate_all()
        self._indicators = pd.DataFrame(
            {
                "AroonOscillator": aroon["AroonOscillator"],
                "VIDiff": vortex["VIDiff"],
                "BullPower": elder["BullPower"],
                "BearPower": elder["BearPower"],
                "Efficiency": EfficiencyRatio(df).calculate(),
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
            if i < 2:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            prev = ind.iloc[i - 1]
            price = float(df["Close"].iloc[i - 1])
            if not _is_ready(prev["AroonOscillator"], prev["VIDiff"], prev["BullPower"], prev["BearPower"], prev["Efficiency"], prev["ATR"]):
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
                continue
            long_entry = position == 0 and prev["AroonOscillator"] >= self.aroon_threshold and prev["VIDiff"] >= self.vortex_threshold and prev["BullPower"] > 0 and prev["Efficiency"] > 0.2
            short_entry = position == 0 and prev["AroonOscillator"] <= -self.aroon_threshold and prev["VIDiff"] <= -self.vortex_threshold and prev["BearPower"] < 0 and prev["Efficiency"] > 0.2
            long_exit = position == 1 and (prev["AroonOscillator"] < 0 or prev["VIDiff"] < 0)
            short_exit = position == -1 and (prev["AroonOscillator"] > 0 or prev["VIDiff"] > 0)
            if long_exit or short_exit:
                position = 0
                signals.append(Signal("CLOSE", self.symbol, _timestamp(ts)))
            elif long_entry:
                position = 1
                signals.append(Signal("BUY", self.symbol, _timestamp(ts), stop_loss=price - float(prev["ATR"]) * self.atr_stop_multiple))
            elif short_entry:
                position = -1
                signals.append(Signal("SELL", self.symbol, _timestamp(ts), stop_loss=price + float(prev["ATR"]) * self.atr_stop_multiple))
            else:
                signals.append(Signal.hold(self.symbol, _timestamp(ts)))
        return pd.Series(signals, index=df.index, dtype=object)
