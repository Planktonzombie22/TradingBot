from dataclasses import dataclass
from itertools import combinations
from math import isfinite, log
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class PairsResearchConfig:
    min_history: int = 120
    correlation_lookback: int = 90
    hedge_lookback: int = 120
    zscore_lookback: int = 60
    min_abs_correlation: float = 0.70
    min_abs_zscore: float = 1.5
    max_half_life: float = 30.0
    max_pairs: int = 20
    gross_exposure_per_pair: float = 0.20
    allow_short: bool = True


@dataclass(frozen=True)
class PairTradeLeg:
    symbol: str
    side: str
    weight: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class PairCandidate:
    symbol_y: str
    symbol_x: str
    action: str
    score: float
    correlation: float
    hedge_ratio: float
    spread_zscore: float
    half_life: float | None
    stationarity_score: float
    cointegration_proxy: float
    observations: int
    legs: tuple[PairTradeLeg, ...]

    @property
    def pair(self) -> str:
        return f"{self.symbol_y}/{self.symbol_x}"

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "symbol_y": self.symbol_y,
            "symbol_x": self.symbol_x,
            "action": self.action,
            "score": self.score,
            "correlation": self.correlation,
            "hedge_ratio": self.hedge_ratio,
            "spread_zscore": self.spread_zscore,
            "half_life": self.half_life,
            "stationarity_score": self.stationarity_score,
            "cointegration_proxy": self.cointegration_proxy,
            "observations": self.observations,
            "legs": [leg.to_dict() for leg in self.legs],
        }


@dataclass(frozen=True)
class PairsResearchReport:
    config: PairsResearchConfig
    candidates: tuple[PairCandidate, ...]
    skipped_pairs: Mapping[str, str]

    @property
    def active_candidates(self) -> tuple[PairCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.action != "watch")

    def to_dict(self) -> dict:
        return {
            "config": {
                "min_history": self.config.min_history,
                "correlation_lookback": self.config.correlation_lookback,
                "hedge_lookback": self.config.hedge_lookback,
                "zscore_lookback": self.config.zscore_lookback,
                "min_abs_correlation": self.config.min_abs_correlation,
                "min_abs_zscore": self.config.min_abs_zscore,
                "max_half_life": self.config.max_half_life,
                "max_pairs": self.config.max_pairs,
                "gross_exposure_per_pair": self.config.gross_exposure_per_pair,
                "allow_short": self.config.allow_short,
            },
            "candidate_count": len(self.candidates),
            "active_count": len(self.active_candidates),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "skipped_pairs": dict(self.skipped_pairs),
        }


def discover_stat_arb_pairs(
    data_by_symbol: Mapping[str, pd.DataFrame],
    config: PairsResearchConfig | None = None,
) -> PairsResearchReport:
    """Discover candidate mean-reverting pairs from aligned close histories."""

    if len(data_by_symbol) < 2:
        raise ValueError("Pairs research requires at least two symbols.")

    config = config or PairsResearchConfig()
    normalized = {str(symbol).upper(): data.sort_index() for symbol, data in data_by_symbol.items()}
    candidates: list[PairCandidate] = []
    skipped: dict[str, str] = {}

    for symbol_y, symbol_x in combinations(sorted(normalized), 2):
        key = f"{symbol_y}/{symbol_x}"
        aligned = _aligned_closes(normalized[symbol_y], normalized[symbol_x], symbol_y, symbol_x)
        reason = _skip_reason(aligned, config)
        if reason:
            skipped[key] = reason
            continue

        candidate = _candidate_from_aligned(symbol_y, symbol_x, aligned, config)
        if candidate is None:
            skipped[key] = "failed_metric_calculation"
            continue
        if abs(candidate.correlation) < config.min_abs_correlation:
            skipped[key] = "correlation_below_threshold"
            continue
        if candidate.half_life is None or candidate.half_life > config.max_half_life:
            skipped[key] = "half_life_out_of_range"
            continue
        candidates.append(candidate)

    candidates = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[: config.max_pairs]
    return PairsResearchReport(config=config, candidates=tuple(candidates), skipped_pairs=skipped)


def _aligned_closes(data_y: pd.DataFrame, data_x: pd.DataFrame, symbol_y: str, symbol_x: str) -> pd.DataFrame:
    closes = pd.concat(
        [
            data_y["Close"].astype(float).rename(symbol_y),
            data_x["Close"].astype(float).rename(symbol_x),
        ],
        axis=1,
    )
    return closes.dropna()


def _skip_reason(aligned: pd.DataFrame, config: PairsResearchConfig) -> str | None:
    if aligned.empty:
        return "empty_overlap"
    if len(aligned) < config.min_history:
        return "insufficient_overlap"
    if (aligned <= 0).any().any():
        return "non_positive_prices"
    return None


def _candidate_from_aligned(
    symbol_y: str,
    symbol_x: str,
    aligned: pd.DataFrame,
    config: PairsResearchConfig,
) -> PairCandidate | None:
    log_prices = aligned.apply(_safe_log)
    correlation = log_prices[symbol_y].tail(config.correlation_lookback).corr(log_prices[symbol_x].tail(config.correlation_lookback))
    if pd.isna(correlation):
        return None

    y = log_prices[symbol_y].tail(config.hedge_lookback)
    x = log_prices[symbol_x].tail(config.hedge_lookback)
    hedge_ratio = _hedge_ratio(y, x)
    if hedge_ratio is None:
        return None

    spread = y - hedge_ratio * x
    zscore = _latest_zscore(spread.tail(config.zscore_lookback))
    half_life = _half_life(spread)
    stationarity_score = _stationarity_score(half_life, config)
    cointegration_proxy = abs(float(correlation)) * stationarity_score
    action = _action_for_zscore(zscore, config)
    legs = _legs_for_action(symbol_y, symbol_x, hedge_ratio, action, config)
    score = cointegration_proxy + abs(zscore) * 0.10

    return PairCandidate(
        symbol_y=symbol_y,
        symbol_x=symbol_x,
        action=action,
        score=float(score),
        correlation=float(correlation),
        hedge_ratio=float(hedge_ratio),
        spread_zscore=float(zscore),
        half_life=float(half_life) if half_life is not None else None,
        stationarity_score=float(stationarity_score),
        cointegration_proxy=float(cointegration_proxy),
        observations=len(aligned),
        legs=legs,
    )


def _safe_log(series: pd.Series) -> pd.Series:
    return series.apply(lambda value: log(float(value)))


def _hedge_ratio(y: pd.Series, x: pd.Series) -> float | None:
    covariance = x.cov(y)
    variance = x.var()
    if pd.isna(covariance) or pd.isna(variance) or variance <= 0:
        return None
    return float(covariance / variance)


def _latest_zscore(spread: pd.Series) -> float:
    mean = spread.mean()
    std = spread.std()
    if pd.isna(std) or std == 0:
        return 0.0
    return float((spread.iloc[-1] - mean) / std)


def _half_life(spread: pd.Series) -> float | None:
    lagged = spread.shift(1).dropna()
    delta = spread.diff().dropna()
    aligned = pd.concat([lagged.rename("lagged"), delta.rename("delta")], axis=1).dropna()
    if len(aligned) < 3:
        return None
    slope = _hedge_ratio(aligned["delta"], aligned["lagged"])
    if slope is None or slope >= 0:
        return None
    half_life = -log(2) / slope
    if not isfinite(half_life) or half_life <= 0:
        return None
    return float(half_life)


def _stationarity_score(half_life: float | None, config: PairsResearchConfig) -> float:
    if half_life is None or half_life <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - half_life / config.max_half_life))


def _action_for_zscore(zscore: float, config: PairsResearchConfig) -> str:
    if abs(zscore) < config.min_abs_zscore:
        return "watch"
    if zscore > 0:
        return "short_spread"
    return "long_spread"


def _legs_for_action(
    symbol_y: str,
    symbol_x: str,
    hedge_ratio: float,
    action: str,
    config: PairsResearchConfig,
) -> tuple[PairTradeLeg, ...]:
    if action == "watch":
        return tuple()
    if not config.allow_short:
        return tuple()

    y_weight, x_weight = _normalized_pair_weights(hedge_ratio, config.gross_exposure_per_pair)
    if action == "short_spread":
        return (
            PairTradeLeg(symbol=symbol_y, side="SELL", weight=-y_weight),
            PairTradeLeg(symbol=symbol_x, side="BUY", weight=x_weight),
        )
    return (
        PairTradeLeg(symbol=symbol_y, side="BUY", weight=y_weight),
        PairTradeLeg(symbol=symbol_x, side="SELL", weight=-x_weight),
    )


def _normalized_pair_weights(hedge_ratio: float, gross_exposure: float) -> tuple[float, float]:
    hedge_abs = abs(hedge_ratio)
    denominator = 1.0 + hedge_abs
    if denominator <= 0:
        return 0.0, 0.0
    y_weight = gross_exposure / denominator
    x_weight = gross_exposure * hedge_abs / denominator
    return float(y_weight), float(x_weight)
