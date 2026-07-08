from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class MarketRegimeConfig:
    lookback: int = 60
    short_volatility_window: int = 20
    long_volatility_window: int = 60
    trend_efficiency_threshold: float = 0.35
    range_efficiency_threshold: float = 0.15
    direction_threshold: float = 0.02
    volatility_expansion_threshold: float = 1.25
    volatility_contraction_threshold: float = 0.75
    low_liquidity_threshold: float = 0.60
    high_liquidity_threshold: float = 1.40


@dataclass(frozen=True)
class MarketRegimeProfile:
    symbol: str
    trend_state: str
    trend_direction: str
    volatility_state: str
    liquidity_state: str
    macro_sensitivity: str
    efficiency_ratio: float
    period_return: float
    volatility_ratio: float
    liquidity_ratio: float
    eligible_modes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "trend_state": self.trend_state,
            "trend_direction": self.trend_direction,
            "volatility_state": self.volatility_state,
            "liquidity_state": self.liquidity_state,
            "macro_sensitivity": self.macro_sensitivity,
            "efficiency_ratio": self.efficiency_ratio,
            "period_return": self.period_return,
            "volatility_ratio": self.volatility_ratio,
            "liquidity_ratio": self.liquidity_ratio,
            "eligible_modes": list(self.eligible_modes),
        }


def classify_market_regime(
    data: pd.DataFrame,
    symbol: str = "",
    config: MarketRegimeConfig | None = None,
) -> MarketRegimeProfile:
    """Classify a market into broad strategy-activation regimes."""

    config = config or MarketRegimeConfig()
    if len(data) < max(3, min(config.lookback, 3)):
        return _unknown_profile(symbol)

    close = pd.to_numeric(data["Close"], errors="coerce").dropna()
    volume = pd.to_numeric(data["Volume"], errors="coerce").dropna() if "Volume" in data else pd.Series(dtype="float64")
    if len(close) < 3:
        return _unknown_profile(symbol)

    lookback = min(config.lookback, len(close) - 1)
    window = close.iloc[-lookback:]
    period_return = (float(window.iloc[-1]) / float(window.iloc[0]) - 1.0) if float(window.iloc[0]) else 0.0
    path_length = close.diff().abs().iloc[-lookback:].sum()
    direct_move = abs(float(close.iloc[-1]) - float(close.iloc[-lookback]))
    efficiency_ratio = float(direct_move / path_length) if path_length else 0.0

    trend_state = _trend_state(efficiency_ratio, config)
    trend_direction = _trend_direction(period_return, config)
    volatility_ratio = _volatility_ratio(close, config)
    volatility_state = _volatility_state(volatility_ratio, config)
    liquidity_ratio = _liquidity_ratio(volume, config)
    liquidity_state = _liquidity_state(liquidity_ratio, config)
    macro_sensitivity = _macro_sensitivity(symbol)
    eligible_modes = _eligible_modes(trend_state, trend_direction, volatility_state, liquidity_state)

    return MarketRegimeProfile(
        symbol=symbol.upper(),
        trend_state=trend_state,
        trend_direction=trend_direction,
        volatility_state=volatility_state,
        liquidity_state=liquidity_state,
        macro_sensitivity=macro_sensitivity,
        efficiency_ratio=efficiency_ratio,
        period_return=period_return,
        volatility_ratio=volatility_ratio,
        liquidity_ratio=liquidity_ratio,
        eligible_modes=eligible_modes,
    )


def classify_regime_universe(
    data_by_symbol: Mapping[str, pd.DataFrame],
    config: MarketRegimeConfig | None = None,
) -> dict[str, MarketRegimeProfile]:
    return {
        symbol.upper(): classify_market_regime(data, symbol, config)
        for symbol, data in sorted(data_by_symbol.items())
    }


def _unknown_profile(symbol: str) -> MarketRegimeProfile:
    return MarketRegimeProfile(
        symbol=symbol.upper(),
        trend_state="unknown",
        trend_direction="flat",
        volatility_state="unknown",
        liquidity_state="unknown",
        macro_sensitivity=_macro_sensitivity(symbol),
        efficiency_ratio=0.0,
        period_return=0.0,
        volatility_ratio=0.0,
        liquidity_ratio=0.0,
        eligible_modes=("benchmark", "cash"),
    )


def _trend_state(efficiency_ratio: float, config: MarketRegimeConfig) -> str:
    if efficiency_ratio >= config.trend_efficiency_threshold:
        return "trending"
    if efficiency_ratio <= config.range_efficiency_threshold:
        return "range_bound"
    return "mixed"


def _trend_direction(period_return: float, config: MarketRegimeConfig) -> str:
    if period_return >= config.direction_threshold:
        return "up"
    if period_return <= -config.direction_threshold:
        return "down"
    return "flat"


def _volatility_ratio(close: pd.Series, config: MarketRegimeConfig) -> float:
    returns = close.pct_change().dropna()
    if returns.empty:
        return 0.0
    short_window = min(config.short_volatility_window, len(returns))
    long_window = min(config.long_volatility_window, len(returns))
    short_vol = float(returns.iloc[-short_window:].std())
    long_vol = float(returns.iloc[-long_window:].std())
    return short_vol / long_vol if long_vol else 0.0


def _volatility_state(volatility_ratio: float, config: MarketRegimeConfig) -> str:
    if volatility_ratio >= config.volatility_expansion_threshold:
        return "expansion"
    if 0 < volatility_ratio <= config.volatility_contraction_threshold:
        return "contraction"
    return "normal"


def _liquidity_ratio(volume: pd.Series, config: MarketRegimeConfig) -> float:
    if volume.empty:
        return 0.0
    recent_window = min(config.short_volatility_window, len(volume))
    baseline_window = min(config.long_volatility_window, len(volume))
    recent = float(volume.iloc[-recent_window:].mean())
    baseline = float(volume.iloc[-baseline_window:].median())
    return recent / baseline if baseline else 0.0


def _liquidity_state(liquidity_ratio: float, config: MarketRegimeConfig) -> str:
    if liquidity_ratio == 0:
        return "unknown"
    if liquidity_ratio <= config.low_liquidity_threshold:
        return "thin"
    if liquidity_ratio >= config.high_liquidity_threshold:
        return "active"
    return "normal"


def _eligible_modes(trend_state: str, trend_direction: str, volatility_state: str, liquidity_state: str) -> tuple[str, ...]:
    modes = ["benchmark"]
    if liquidity_state != "thin":
        if trend_state == "trending" and trend_direction in {"up", "down"}:
            modes.append("trend_following")
        if trend_state in {"range_bound", "mixed"}:
            modes.append("mean_reversion")
        if volatility_state == "expansion":
            modes.append("breakout")
        if volatility_state == "contraction":
            modes.append("range_scalping")
    modes.append("cash")
    return tuple(dict.fromkeys(modes))


def _macro_sensitivity(symbol: str) -> str:
    normalized = symbol.upper()
    high_sensitivity = {
        "TLT",
        "IEF",
        "SHY",
        "GLD",
        "SLV",
        "USO",
        "UNG",
        "UUP",
        "FXE",
        "FXY",
        "EEM",
        "EWZ",
        "EWW",
        "FXI",
        "EPI",
    }
    if normalized in high_sensitivity:
        return "high"
    if normalized.startswith("EW") or normalized.startswith("FX"):
        return "medium"
    return "normal"
