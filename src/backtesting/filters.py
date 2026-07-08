from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from src.indicators import AnchoredVWAP, ATR, ChoppinessIndex, FairValueGap, LiquiditySweep, MarketStructureBreak, RelativeVolume


@dataclass(frozen=True)
class ResearchFilterConfig:
    choppiness_threshold: float = 55.0
    vwap_stretch_threshold: float = 0.04
    structure_lookback: int = 30
    min_relative_volume: float = 1.0
    fvg_min_atr_multiple: float = 0.15
    liquidity_sweep_lookback: int = 20


@dataclass(frozen=True)
class ResearchFilterResult:
    name: str
    passed: bool
    direction: str
    score: float
    reason: str
    values: Mapping[str, object]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "direction": self.direction,
            "score": self.score,
            "reason": self.reason,
            "values": dict(self.values),
        }


@dataclass(frozen=True)
class ResearchFilterSnapshot:
    symbol: str
    timestamp: object
    filters: tuple[ResearchFilterResult, ...]

    @property
    def passed_filters(self) -> tuple[str, ...]:
        return tuple(result.name for result in self.filters if result.passed)

    def result(self, name: str) -> ResearchFilterResult | None:
        for filter_result in self.filters:
            if filter_result.name == name:
                return filter_result
        return None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": str(self.timestamp),
            "passed_filters": list(self.passed_filters),
            "filters": [result.to_dict() for result in self.filters],
        }


def evaluate_research_filters(
    data: pd.DataFrame,
    symbol: str = "",
    config: ResearchFilterConfig | None = None,
) -> ResearchFilterSnapshot:
    """Evaluate reusable strategy context filters on the latest completed bar."""

    config = config or ResearchFilterConfig()
    if data.empty:
        return ResearchFilterSnapshot(symbol=symbol.upper(), timestamp=None, filters=tuple())

    index = data.index[-1]
    filters = (
        choppiness_range_filter(data, config),
        vwap_stretch_filter(data, config),
        structure_confirmation_filter(data, config),
        fair_value_gap_filter(data, config),
        liquidity_sweep_filter(data, config),
    )
    return ResearchFilterSnapshot(symbol=symbol.upper(), timestamp=index, filters=filters)


def choppiness_range_filter(data: pd.DataFrame, config: ResearchFilterConfig | None = None) -> ResearchFilterResult:
    config = config or ResearchFilterConfig()
    chop = ChoppinessIndex(data).calculate()
    value = _last_float(chop)
    passed = value >= config.choppiness_threshold
    score = max(0.0, (value - config.choppiness_threshold) / max(100.0 - config.choppiness_threshold, 1.0))
    return ResearchFilterResult(
        name="choppiness_range",
        passed=passed,
        direction="range" if passed else "neutral",
        score=score,
        reason="range_conditions_present" if passed else "market_not_choppy_enough",
        values={"choppiness": value, "threshold": config.choppiness_threshold},
    )


def vwap_stretch_filter(data: pd.DataFrame, config: ResearchFilterConfig | None = None) -> ResearchFilterResult:
    config = config or ResearchFilterConfig()
    avwap = AnchoredVWAP(data).calculate()
    close = pd.to_numeric(data["Close"], errors="coerce")
    last_close = _last_float(close)
    last_vwap = _last_float(avwap)
    distance = ((last_close - last_vwap) / last_vwap) if last_vwap else 0.0
    abs_distance = abs(distance)
    passed = abs_distance >= config.vwap_stretch_threshold
    direction = "short_mean_reversion" if distance > 0 else "long_mean_reversion" if distance < 0 else "neutral"
    score = abs_distance / config.vwap_stretch_threshold if config.vwap_stretch_threshold else abs_distance
    return ResearchFilterResult(
        name="vwap_stretch",
        passed=passed,
        direction=direction if passed else "neutral",
        score=score if passed else 0.0,
        reason="price_stretched_from_vwap" if passed else "price_near_vwap",
        values={"close": last_close, "anchored_vwap": last_vwap, "distance": distance, "threshold": config.vwap_stretch_threshold},
    )


def structure_confirmation_filter(data: pd.DataFrame, config: ResearchFilterConfig | None = None) -> ResearchFilterResult:
    config = config or ResearchFilterConfig()
    structure = MarketStructureBreak(data, config.structure_lookback).calculate_all()
    relative_volume = RelativeVolume(data).calculate()
    latest = structure.iloc[-1]
    rv = _last_float(relative_volume)
    bullish = bool(latest["BullishStructureBreak"])
    bearish = bool(latest["BearishStructureBreak"])
    volume_confirmed = rv >= config.min_relative_volume
    passed = (bullish or bearish) and volume_confirmed
    direction = "long_breakout" if bullish else "short_breakout" if bearish else "neutral"
    return ResearchFilterResult(
        name="structure_confirmation",
        passed=passed,
        direction=direction if passed else "neutral",
        score=rv if passed else 0.0,
        reason="structure_break_with_volume" if passed else "no_confirmed_structure_break",
        values={
            "bullish_break": bullish,
            "bearish_break": bearish,
            "relative_volume": rv,
            "min_relative_volume": config.min_relative_volume,
        },
    )


def fair_value_gap_filter(data: pd.DataFrame, config: ResearchFilterConfig | None = None) -> ResearchFilterResult:
    config = config or ResearchFilterConfig()
    fvg = FairValueGap(data).calculate_all()
    atr = ATR(data).calculate()
    latest = fvg.iloc[-1]
    atr_value = _last_float(atr)
    fvg_size = _safe_float(latest["FVGSize"])
    direction_value = int(latest["FVGDirection"]) if pd.notna(latest["FVGDirection"]) else 0
    min_size = atr_value * config.fvg_min_atr_multiple
    passed = direction_value != 0 and fvg_size >= min_size
    direction = "bullish_imbalance" if direction_value > 0 else "bearish_imbalance" if direction_value < 0 else "neutral"
    score = fvg_size / min_size if min_size else 0.0
    return ResearchFilterResult(
        name="fair_value_gap",
        passed=passed,
        direction=direction if passed else "neutral",
        score=score if passed else 0.0,
        reason="meaningful_imbalance_present" if passed else "no_meaningful_imbalance",
        values={"fvg_direction": direction_value, "fvg_size": fvg_size, "atr": atr_value, "min_size": min_size},
    )


def liquidity_sweep_filter(data: pd.DataFrame, config: ResearchFilterConfig | None = None) -> ResearchFilterResult:
    config = config or ResearchFilterConfig()
    sweeps = LiquiditySweep(data, config.liquidity_sweep_lookback).calculate_all()
    latest = sweeps.iloc[-1]
    bullish = bool(latest["BullishLiquiditySweep"])
    bearish = bool(latest["BearishLiquiditySweep"])
    passed = bullish or bearish
    direction = "long_reversal" if bullish else "short_reversal" if bearish else "neutral"
    return ResearchFilterResult(
        name="liquidity_sweep",
        passed=passed,
        direction=direction if passed else "neutral",
        score=1.0 if passed else 0.0,
        reason="liquidity_sweep_reversal_context" if passed else "no_liquidity_sweep",
        values={"bullish_sweep": bullish, "bearish_sweep": bearish},
    )


def _last_float(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return _safe_float(series.iloc[-1])


def _safe_float(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
