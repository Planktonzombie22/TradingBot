from dataclasses import dataclass, field
from typing import Mapping, Sequence

import pandas as pd

from ..runners.bulk import BulkBacktestRecord


@dataclass(frozen=True)
class StrategyFamilyEnsemblePolicy:
    benchmark_strategy: str = "buyHold"
    family_map: Mapping[str, str] = field(default_factory=dict)
    min_markets: int = 1
    min_average_excess_return: float = 0.0
    max_average_drawdown: float = -0.70
    cash_reserve: float = 0.10
    max_strategy_weight: float = 0.30
    max_family_weight: float = 0.45
    drawdown_weight: float = 0.20
    correlation_penalty_weight: float = 0.05
    drawdown_overlap_penalty_weight: float = 0.05
    volatility_penalty_weight: float = 0.05
    win_rate_bonus_weight: float = 0.05


@dataclass(frozen=True)
class StrategyFamilyCandidate:
    strategy: str
    family: str
    markets: int
    average_return: float
    average_excess_return: float
    average_drawdown: float
    average_drawdown_improvement: float
    win_rate: float
    trade_efficiency: float
    tail_risk: float
    correlation_penalty: float
    drawdown_overlap_penalty: float
    volatility_penalty: float
    raw_score: float
    adjusted_score: float
    weight: float
    action: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "family": self.family,
            "markets": self.markets,
            "average_return": self.average_return,
            "average_excess_return": self.average_excess_return,
            "average_drawdown": self.average_drawdown,
            "average_drawdown_improvement": self.average_drawdown_improvement,
            "win_rate": self.win_rate,
            "trade_efficiency": self.trade_efficiency,
            "tail_risk": self.tail_risk,
            "correlation_penalty": self.correlation_penalty,
            "drawdown_overlap_penalty": self.drawdown_overlap_penalty,
            "volatility_penalty": self.volatility_penalty,
            "raw_score": self.raw_score,
            "adjusted_score": self.adjusted_score,
            "weight": self.weight,
            "action": self.action,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyFamilyEnsembleReport:
    policy: StrategyFamilyEnsemblePolicy
    candidates: tuple[StrategyFamilyCandidate, ...]
    missing_benchmarks: tuple[str, ...] = tuple()

    @property
    def active_candidates(self) -> tuple[StrategyFamilyCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.action == "allocate")

    @property
    def invested_weight(self) -> float:
        return sum(candidate.weight for candidate in self.active_candidates)

    @property
    def cash_weight(self) -> float:
        return max(0.0, 1.0 - self.invested_weight)

    @property
    def weights_by_strategy(self) -> dict[str, float]:
        return {candidate.strategy: candidate.weight for candidate in self.active_candidates}

    @property
    def weights_by_family(self) -> dict[str, float]:
        weights: dict[str, float] = {}
        for candidate in self.active_candidates:
            weights[candidate.family] = weights.get(candidate.family, 0.0) + candidate.weight
        return weights

    def to_dict(self) -> dict:
        return {
            "policy": {
                "benchmark_strategy": self.policy.benchmark_strategy,
                "min_markets": self.policy.min_markets,
                "min_average_excess_return": self.policy.min_average_excess_return,
                "max_average_drawdown": self.policy.max_average_drawdown,
                "cash_reserve": self.policy.cash_reserve,
                "max_strategy_weight": self.policy.max_strategy_weight,
                "max_family_weight": self.policy.max_family_weight,
            },
            "invested_weight": self.invested_weight,
            "cash_weight": self.cash_weight,
            "weights_by_strategy": self.weights_by_strategy,
            "weights_by_family": self.weights_by_family,
            "missing_benchmarks": list(self.missing_benchmarks),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def build_strategy_family_ensemble(
    records: Sequence[BulkBacktestRecord],
    returns_by_strategy: Mapping[str, pd.Series] | None = None,
    policy: StrategyFamilyEnsemblePolicy | None = None,
) -> StrategyFamilyEnsembleReport:
    """Allocate across strategy families using edge, drawdown, and diversification."""

    policy = policy or StrategyFamilyEnsemblePolicy()
    returns_by_strategy = returns_by_strategy or {}
    by_symbol = _records_by_symbol(records)
    benchmark_by_symbol = {
        symbol: strategies[policy.benchmark_strategy]
        for symbol, strategies in by_symbol.items()
        if policy.benchmark_strategy in strategies
    }
    missing_benchmarks = tuple(sorted(set(by_symbol).difference(benchmark_by_symbol)))
    raw_candidates = []

    for strategy in sorted({record.strategy for record in records if record.strategy != policy.benchmark_strategy}):
        matched = [
            (record, benchmark_by_symbol[record.symbol])
            for record in records
            if record.strategy == strategy and record.symbol in benchmark_by_symbol
        ]
        raw_candidates.append(_candidate_for_strategy(strategy, matched, returns_by_strategy, policy))

    weighted = _assign_weights(raw_candidates, policy)
    return StrategyFamilyEnsembleReport(
        policy=policy,
        candidates=tuple(sorted(weighted, key=lambda candidate: (candidate.action == "allocate", candidate.weight, candidate.adjusted_score), reverse=True)),
        missing_benchmarks=missing_benchmarks,
    )


def _records_by_symbol(records: Sequence[BulkBacktestRecord]) -> dict[str, dict[str, BulkBacktestRecord]]:
    grouped: dict[str, dict[str, BulkBacktestRecord]] = {}
    for record in records:
        grouped.setdefault(record.symbol, {})[record.strategy] = record
    return grouped


def _candidate_for_strategy(
    strategy: str,
    matched: Sequence[tuple[BulkBacktestRecord, BulkBacktestRecord]],
    returns_by_strategy: Mapping[str, pd.Series],
    policy: StrategyFamilyEnsemblePolicy,
) -> StrategyFamilyCandidate:
    family = str(policy.family_map.get(strategy, strategy))
    markets = len(matched)
    if not matched:
        return _rejected(strategy, family, "missing_benchmark_overlap")

    strategy_returns = [float(record.total_pnl_pct) for record, _ in matched]
    excess_returns = [float(record.total_pnl_pct - benchmark.total_pnl_pct) for record, benchmark in matched]
    drawdowns = [_metric_float(record.metrics, "max_drawdown") for record, _ in matched]
    benchmark_drawdowns = [_metric_float(benchmark.metrics, "max_drawdown") for _, benchmark in matched]
    drawdown_improvements = [abs(benchmark) - abs(strategy_drawdown) for strategy_drawdown, benchmark in zip(drawdowns, benchmark_drawdowns)]
    trades = sum(record.trades for record, _ in matched)
    average_return = _average(strategy_returns)
    average_excess = _average(excess_returns)
    average_drawdown = _average(drawdowns)
    average_drawdown_improvement = _average(drawdown_improvements)
    win_rate = sum(1 for value in excess_returns if value > 0) / markets if markets else 0.0
    trade_efficiency = average_excess / trades if trades else 0.0
    tail_risk = min([*strategy_returns, *drawdowns], default=0.0)
    correlation_penalty = _correlation_penalty(strategy, returns_by_strategy)
    drawdown_overlap_penalty = _drawdown_overlap_penalty(strategy, returns_by_strategy)
    volatility_penalty = _volatility_penalty(strategy, returns_by_strategy)
    raw_score = average_excess + average_drawdown_improvement * policy.drawdown_weight + win_rate * policy.win_rate_bonus_weight
    adjusted_score = (
        raw_score
        - abs(min(0.0, average_drawdown)) * policy.drawdown_weight
        - correlation_penalty * policy.correlation_penalty_weight
        - drawdown_overlap_penalty * policy.drawdown_overlap_penalty_weight
        - volatility_penalty * policy.volatility_penalty_weight
    )
    action, reason = _decision(markets, average_excess, average_drawdown, adjusted_score, policy)

    return StrategyFamilyCandidate(
        strategy=strategy,
        family=family,
        markets=markets,
        average_return=average_return,
        average_excess_return=average_excess,
        average_drawdown=average_drawdown,
        average_drawdown_improvement=average_drawdown_improvement,
        win_rate=win_rate,
        trade_efficiency=trade_efficiency,
        tail_risk=tail_risk,
        correlation_penalty=correlation_penalty,
        drawdown_overlap_penalty=drawdown_overlap_penalty,
        volatility_penalty=volatility_penalty,
        raw_score=raw_score,
        adjusted_score=adjusted_score,
        weight=0.0,
        action=action,
        reason=reason,
    )


def _decision(
    markets: int,
    average_excess: float,
    average_drawdown: float,
    adjusted_score: float,
    policy: StrategyFamilyEnsemblePolicy,
) -> tuple[str, str]:
    if markets < policy.min_markets:
        return "reject", "insufficient_markets"
    if average_excess < policy.min_average_excess_return:
        return "reject", "insufficient_average_edge"
    if average_drawdown < policy.max_average_drawdown:
        return "reject", "drawdown_too_deep"
    if adjusted_score <= 0:
        return "reject", "risk_adjusted_score_non_positive"
    return "allocate", "passes_family_ensemble_gates"


def _assign_weights(
    candidates: Sequence[StrategyFamilyCandidate],
    policy: StrategyFamilyEnsemblePolicy,
) -> tuple[StrategyFamilyCandidate, ...]:
    active = [candidate for candidate in candidates if candidate.action == "allocate"]
    if not active:
        return tuple(candidates)

    available = max(0.0, 1.0 - policy.cash_reserve)
    score_sum = sum(max(candidate.adjusted_score, 0.0) for candidate in active)
    family_weights: dict[str, float] = {}
    assigned: dict[str, float] = {}
    remaining = available

    for candidate in sorted(active, key=lambda item: item.adjusted_score, reverse=True):
        raw_weight = available * max(candidate.adjusted_score, 0.0) / score_sum if score_sum else 0.0
        family_remaining = max(0.0, policy.max_family_weight - family_weights.get(candidate.family, 0.0))
        weight = min(raw_weight, policy.max_strategy_weight, family_remaining, remaining)
        assigned[candidate.strategy] = max(0.0, weight)
        family_weights[candidate.family] = family_weights.get(candidate.family, 0.0) + assigned[candidate.strategy]
        remaining -= assigned[candidate.strategy]

    return tuple(
        StrategyFamilyCandidate(
            strategy=candidate.strategy,
            family=candidate.family,
            markets=candidate.markets,
            average_return=candidate.average_return,
            average_excess_return=candidate.average_excess_return,
            average_drawdown=candidate.average_drawdown,
            average_drawdown_improvement=candidate.average_drawdown_improvement,
            win_rate=candidate.win_rate,
            trade_efficiency=candidate.trade_efficiency,
            tail_risk=candidate.tail_risk,
            correlation_penalty=candidate.correlation_penalty,
            drawdown_overlap_penalty=candidate.drawdown_overlap_penalty,
            volatility_penalty=candidate.volatility_penalty,
            raw_score=candidate.raw_score,
            adjusted_score=candidate.adjusted_score,
            weight=assigned.get(candidate.strategy, 0.0),
            action=candidate.action if assigned.get(candidate.strategy, 0.0) > 0 or candidate.action != "allocate" else "reject",
            reason=candidate.reason if assigned.get(candidate.strategy, 0.0) > 0 or candidate.action != "allocate" else "family_or_strategy_cap_exhausted",
        )
        for candidate in candidates
    )


def _rejected(strategy: str, family: str, reason: str) -> StrategyFamilyCandidate:
    return StrategyFamilyCandidate(
        strategy=strategy,
        family=family,
        markets=0,
        average_return=0.0,
        average_excess_return=0.0,
        average_drawdown=0.0,
        average_drawdown_improvement=0.0,
        win_rate=0.0,
        trade_efficiency=0.0,
        tail_risk=0.0,
        correlation_penalty=0.0,
        drawdown_overlap_penalty=0.0,
        volatility_penalty=0.0,
        raw_score=0.0,
        adjusted_score=0.0,
        weight=0.0,
        action="reject",
        reason=reason,
    )


def _correlation_penalty(strategy: str, returns_by_strategy: Mapping[str, pd.Series]) -> float:
    series = _return_series(strategy, returns_by_strategy)
    if series is None:
        return 0.0
    penalties = []
    for other_strategy, other_series in returns_by_strategy.items():
        if other_strategy == strategy:
            continue
        aligned = pd.concat([series.rename("strategy"), other_series.rename("other")], axis=1).dropna()
        if len(aligned) < 3:
            continue
        corr = aligned["strategy"].corr(aligned["other"])
        if pd.notna(corr):
            penalties.append(max(0.0, float(corr)))
    return max(penalties) if penalties else 0.0


def _drawdown_overlap_penalty(strategy: str, returns_by_strategy: Mapping[str, pd.Series]) -> float:
    series = _return_series(strategy, returns_by_strategy)
    if series is None:
        return 0.0
    downside = series.clip(upper=0.0)
    penalties = []
    for other_strategy, other_series in returns_by_strategy.items():
        if other_strategy == strategy:
            continue
        aligned = pd.concat([downside.rename("strategy"), other_series.clip(upper=0.0).rename("other")], axis=1).dropna()
        if len(aligned) < 3 or aligned["strategy"].abs().sum() == 0 or aligned["other"].abs().sum() == 0:
            continue
        corr = aligned["strategy"].corr(aligned["other"])
        if pd.notna(corr):
            penalties.append(max(0.0, float(corr)))
    return max(penalties) if penalties else 0.0


def _volatility_penalty(strategy: str, returns_by_strategy: Mapping[str, pd.Series]) -> float:
    series = _return_series(strategy, returns_by_strategy)
    if series is None:
        return 0.0
    volatility = series.std()
    return float(volatility) if pd.notna(volatility) else 0.0


def _return_series(strategy: str, returns_by_strategy: Mapping[str, pd.Series]) -> pd.Series | None:
    series = returns_by_strategy.get(strategy)
    if series is None:
        return None
    return pd.to_numeric(series, errors="coerce").dropna()


def _metric_float(metrics: Mapping[str, object], name: str) -> float:
    value = metrics.get(name, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
