from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd

from src.models import BacktestResult
from src.strategies import get_strategy, validate_strategy_params

from ..core.engine import BacktestEngine
from ..core.types import BacktestConfig
from .optimization import grid_search


@dataclass(frozen=True)
class WalkForwardGovernanceConfig:
    train_size: int
    test_size: int
    holdout_size: int
    split_mode: str = "rolling"
    metric: str = "total_return"
    min_windows: int = 2
    min_train_score: float = 0.0
    min_oos_score: float = 0.0
    min_holdout_score: float = 0.0
    min_parameter_stability_score: float = 0.50
    max_false_discovery_rate: float = 0.50


@dataclass(frozen=True)
class GovernedWalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    params: dict[str, Any]
    train_score: float
    test_score: float
    test_result: BacktestResult

    def to_dict(self) -> dict:
        return {
            "train_start": str(self.train_start),
            "train_end": str(self.train_end),
            "test_start": str(self.test_start),
            "test_end": str(self.test_end),
            "params": self.params,
            "train_score": self.train_score,
            "test_score": self.test_score,
            "trades": len(self.test_result.trades),
            "fills": len(self.test_result.fills),
        }


@dataclass(frozen=True)
class ParameterStabilityReport:
    champion_params: dict[str, Any]
    parameter_modes: dict[str, Any]
    parameter_stability: dict[str, float]
    stability_score: float

    def to_dict(self) -> dict:
        return {
            "champion_params": self.champion_params,
            "parameter_modes": self.parameter_modes,
            "parameter_stability": self.parameter_stability,
            "stability_score": self.stability_score,
        }


@dataclass(frozen=True)
class WalkForwardGovernanceReport:
    strategy_name: str
    symbol: str
    config: WalkForwardGovernanceConfig
    windows: tuple[GovernedWalkForwardWindow, ...]
    parameter_stability: ParameterStabilityReport
    holdout_result: BacktestResult | None
    holdout_score: float | None
    average_train_score: float
    average_oos_score: float
    false_discovery_rate: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "config": {
                "train_size": self.config.train_size,
                "test_size": self.config.test_size,
                "holdout_size": self.config.holdout_size,
                "split_mode": self.config.split_mode,
                "metric": self.config.metric,
                "min_windows": self.config.min_windows,
                "min_train_score": self.config.min_train_score,
                "min_oos_score": self.config.min_oos_score,
                "min_holdout_score": self.config.min_holdout_score,
                "min_parameter_stability_score": self.config.min_parameter_stability_score,
                "max_false_discovery_rate": self.config.max_false_discovery_rate,
            },
            "windows": [window.to_dict() for window in self.windows],
            "parameter_stability": self.parameter_stability.to_dict(),
            "holdout_score": self.holdout_score,
            "average_train_score": self.average_train_score,
            "average_oos_score": self.average_oos_score,
            "false_discovery_rate": self.false_discovery_rate,
            "passed": self.passed,
            "reason": self.reason,
        }


def run_walk_forward_governance(
    data: pd.DataFrame,
    strategy_name: str,
    symbol: str,
    param_grid: Mapping[str, Iterable[Any]],
    governance_config: WalkForwardGovernanceConfig,
    backtest_config: BacktestConfig | None = None,
) -> WalkForwardGovernanceReport:
    _validate_governance_config(governance_config)
    if len(data) < governance_config.train_size + governance_config.test_size + governance_config.holdout_size:
        raise ValueError("Not enough data for one governed walk-forward split plus holdout.")

    backtest_config = backtest_config or BacktestConfig()
    research_data = data.iloc[: len(data) - governance_config.holdout_size]
    holdout_data = data.iloc[len(data) - governance_config.holdout_size :]
    windows = tuple(
        _run_governance_window(
            data=research_data,
            strategy_name=strategy_name,
            symbol=symbol,
            param_grid=param_grid,
            split=split,
            metric=governance_config.metric,
            backtest_config=backtest_config,
        )
        for split in _walk_forward_splits(research_data, governance_config)
    )
    if not windows:
        raise ValueError("Governance configuration produced no walk-forward windows.")

    stability = _parameter_stability(windows)
    holdout_result = _run_holdout(
        strategy_name=strategy_name,
        symbol=symbol,
        params=stability.champion_params,
        holdout_data=holdout_data,
        backtest_config=backtest_config,
    )
    holdout_score = _score_result(holdout_result, governance_config.metric)
    average_train_score = _average(window.train_score for window in windows)
    average_oos_score = _average(window.test_score for window in windows)
    false_discovery_rate = _false_discovery_rate(windows, governance_config)
    passed, reason = _governance_decision(
        windows=windows,
        stability=stability,
        holdout_score=holdout_score,
        average_oos_score=average_oos_score,
        false_discovery_rate=false_discovery_rate,
        config=governance_config,
    )
    return WalkForwardGovernanceReport(
        strategy_name=strategy_name,
        symbol=symbol,
        config=governance_config,
        windows=windows,
        parameter_stability=stability,
        holdout_result=holdout_result,
        holdout_score=holdout_score,
        average_train_score=average_train_score,
        average_oos_score=average_oos_score,
        false_discovery_rate=false_discovery_rate,
        passed=passed,
        reason=reason,
    )


def _run_governance_window(
    data: pd.DataFrame,
    strategy_name: str,
    symbol: str,
    param_grid: Mapping[str, Iterable[Any]],
    split: tuple[int, int, int, int],
    metric: str,
    backtest_config: BacktestConfig,
) -> GovernedWalkForwardWindow:
    train_start, train_end, test_start, test_end = split
    train = data.iloc[train_start:train_end]
    test = data.iloc[test_start:test_end]
    optimization_results = grid_search(
        strategy_name=strategy_name,
        symbol=symbol,
        data=train,
        param_grid=param_grid,
        metric=metric,
        config=backtest_config,
    )
    best = optimization_results[0]
    strategy_cls = get_strategy(strategy_name)
    params = validate_strategy_params(strategy_name, best.params)
    test_result = BacktestEngine(config=backtest_config).run(strategy_cls(symbol, **params), test)
    return GovernedWalkForwardWindow(
        train_start=train.index[0],
        train_end=train.index[-1],
        test_start=test.index[0],
        test_end=test.index[-1],
        params=params,
        train_score=best.score,
        test_score=_score_result(test_result, metric),
        test_result=test_result,
    )


def _walk_forward_splits(
    data: pd.DataFrame,
    config: WalkForwardGovernanceConfig,
) -> list[tuple[int, int, int, int]]:
    splits = []
    start = 0
    while start + config.train_size + config.test_size <= len(data):
        train_start = 0 if config.split_mode == "anchored" else start
        train_end = start + config.train_size
        test_start = train_end
        test_end = test_start + config.test_size
        splits.append((train_start, train_end, test_start, test_end))
        start += config.test_size
    return splits


def _parameter_stability(windows: tuple[GovernedWalkForwardWindow, ...]) -> ParameterStabilityReport:
    names = sorted({name for window in windows for name in window.params})
    parameter_modes: dict[str, Any] = {}
    parameter_stability: dict[str, float] = {}
    champion_params: dict[str, Any] = {}
    for name in names:
        values = [window.params.get(name) for window in windows]
        mode, count = Counter(values).most_common(1)[0]
        parameter_modes[name] = mode
        parameter_stability[name] = count / len(windows)
        champion_params[name] = mode
    stability_score = min(parameter_stability.values()) if parameter_stability else 1.0
    return ParameterStabilityReport(
        champion_params=champion_params,
        parameter_modes=parameter_modes,
        parameter_stability=parameter_stability,
        stability_score=stability_score,
    )


def _run_holdout(
    strategy_name: str,
    symbol: str,
    params: Mapping[str, Any],
    holdout_data: pd.DataFrame,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    strategy_cls = get_strategy(strategy_name)
    valid_params = validate_strategy_params(strategy_name, params)
    return BacktestEngine(config=backtest_config).run(strategy_cls(symbol, **valid_params), holdout_data)


def _governance_decision(
    windows: tuple[GovernedWalkForwardWindow, ...],
    stability: ParameterStabilityReport,
    holdout_score: float,
    average_oos_score: float,
    false_discovery_rate: float,
    config: WalkForwardGovernanceConfig,
) -> tuple[bool, str]:
    if len(windows) < config.min_windows:
        return False, "insufficient_walk_forward_windows"
    if average_oos_score < config.min_oos_score:
        return False, "out_of_sample_score_below_threshold"
    if holdout_score < config.min_holdout_score:
        return False, "holdout_score_below_threshold"
    if stability.stability_score < config.min_parameter_stability_score:
        return False, "parameter_stability_below_threshold"
    if false_discovery_rate > config.max_false_discovery_rate:
        return False, "false_discovery_rate_too_high"
    return True, "governance_passed"


def _false_discovery_rate(
    windows: tuple[GovernedWalkForwardWindow, ...],
    config: WalkForwardGovernanceConfig,
) -> float:
    train_winners = [window for window in windows if window.train_score >= config.min_train_score]
    if not train_winners:
        return 0.0
    failed_oos = [window for window in train_winners if window.test_score < config.min_oos_score]
    return len(failed_oos) / len(train_winners)


def _score_result(result: BacktestResult, metric: str) -> float:
    if metric == "total_pnl":
        return float(result.total_pnl)
    return float(result.metrics.get(metric, result.total_pnl_pct))


def _average(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _validate_governance_config(config: WalkForwardGovernanceConfig) -> None:
    if config.train_size <= 0 or config.test_size <= 0 or config.holdout_size <= 0:
        raise ValueError("train_size, test_size, and holdout_size must be positive.")
    if config.split_mode not in {"rolling", "anchored"}:
        raise ValueError("split_mode must be 'rolling' or 'anchored'.")
