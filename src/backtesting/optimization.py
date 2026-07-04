from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import pandas as pd

from src.models import BacktestResult
from src.strategies import get_strategy, validate_strategy_params

from .engine import BacktestEngine
from .types import BacktestConfig


@dataclass(frozen=True)
class OptimizationResult:
    strategy_name: str
    params: Dict[str, Any]
    score: float
    result: BacktestResult

    def rank_metrics(self) -> Dict[str, float]:
        return rank_metrics(self.result)


@dataclass(frozen=True)
class OverfittingReport:
    holdout_score: float
    train_score: float
    stability_score: float
    turnover_penalty: float
    minimum_trade_count_met: bool

    @property
    def passed(self) -> bool:
        return self.minimum_trade_count_met and self.stability_score >= 0


def grid_search(
    strategy_name: str,
    symbol: str,
    data: pd.DataFrame,
    param_grid: Mapping[str, Iterable[Any]],
    metric: str = "total_return",
    config: BacktestConfig | None = None,
) -> List[OptimizationResult]:
    names = list(param_grid)
    values = [list(param_grid[name]) for name in names]
    strategy_cls = get_strategy(strategy_name)
    results: List[OptimizationResult] = []

    for combination in product(*values):
        raw_params = dict(zip(names, combination))
        params = validate_strategy_params(strategy_name, raw_params)
        strategy = strategy_cls(symbol, **params)
        result = BacktestEngine(config=config or BacktestConfig()).run(strategy, data)
        score = _score_result(result, metric)
        results.append(OptimizationResult(strategy_name, params, score, result))

    return sorted(results, key=lambda item: item.score, reverse=True)


def rank_optimization_results(results: Sequence[OptimizationResult]) -> List[OptimizationResult]:
    return sorted(results, key=lambda item: _composite_rank_score(item.result), reverse=True)


def rank_metrics(result: BacktestResult) -> Dict[str, float]:
    metrics = result.metrics or {}
    return {
        "total_return": float(metrics.get("total_return", result.total_pnl_pct)),
        "sharpe": float(metrics.get("sharpe", 0.0)),
        "sortino": float(metrics.get("sortino", 0.0)),
        "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
        "win_rate": float(metrics.get("win_rate", 0.0)),
        "exposure": float(metrics.get("exposure", 0.0)),
        "turnover": float(metrics.get("turnover", len(result.fills))),
        "tail_risk": float(metrics.get("tail_risk", metrics.get("max_drawdown", 0.0))),
    }


def overfitting_report(
    train_result: BacktestResult,
    holdout_result: BacktestResult,
    metric: str = "total_return",
    min_trades: int = 1,
) -> OverfittingReport:
    train_score = _score_result(train_result, metric)
    holdout_score = _score_result(holdout_result, metric)
    stability = holdout_score - train_score if train_score else holdout_score
    turnover_penalty = abs(len(holdout_result.fills) - len(train_result.fills))
    return OverfittingReport(
        holdout_score=holdout_score,
        train_score=train_score,
        stability_score=stability,
        turnover_penalty=float(turnover_penalty),
        minimum_trade_count_met=len(holdout_result.trades) >= min_trades,
    )


def _score_result(result: BacktestResult, metric: str) -> float:
    if metric == "total_pnl":
        return float(result.total_pnl)
    return float(result.metrics.get(metric, result.total_pnl_pct))


def _composite_rank_score(result: BacktestResult) -> float:
    metrics = rank_metrics(result)
    return (
        metrics["total_return"]
        + metrics["sharpe"] * 0.10
        + metrics["sortino"] * 0.05
        + metrics["win_rate"] * 0.05
        - abs(metrics["max_drawdown"]) * 0.50
        - abs(metrics["tail_risk"]) * 0.25
        - metrics["turnover"] * 0.001
    )
