from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, Iterable, List, Mapping

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


def _score_result(result: BacktestResult, metric: str) -> float:
    if metric == "total_pnl":
        return float(result.total_pnl)
    return float(result.metrics.get(metric, result.total_pnl_pct))
