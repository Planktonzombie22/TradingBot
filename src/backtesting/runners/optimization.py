from dataclasses import dataclass
from importlib.util import find_spec
from itertools import product
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import pandas as pd

from src.models import BacktestResult
from src.strategies import get_strategy, validate_strategy_params

from ..core.engine import BacktestEngine
from ..core.types import BacktestConfig


@dataclass(frozen=True)
class OptimizationResult:
    strategy_name: str
    params: Dict[str, Any]
    score: float
    result: BacktestResult

    def rank_metrics(self) -> Dict[str, float]:
        return rank_metrics(self.result)


@dataclass(frozen=True)
class OptunaOptimizationConfig:
    n_trials: int = 25
    metric: str = "total_return"
    direction: str = "maximize"
    sampler_seed: int | None = 42
    study_name: str | None = None
    storage_url: str | None = None
    load_if_exists: bool = True
    validation_fraction: float = 0.0
    prune_below_score: float | None = None


@dataclass(frozen=True)
class OptunaTrialRecord:
    number: int
    params: Dict[str, Any]
    score: float | None
    state: str
    train_score: float | None = None
    holdout_score: float | None = None

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "params": dict(self.params),
            "score": self.score,
            "state": self.state,
            "train_score": self.train_score,
            "holdout_score": self.holdout_score,
        }


@dataclass(frozen=True)
class OptunaOptimizationReport:
    strategy_name: str
    symbol: str
    config: OptunaOptimizationConfig
    best_result: OptimizationResult | None
    trials: tuple[OptunaTrialRecord, ...]
    study_name: str | None

    @property
    def best_params(self) -> Dict[str, Any]:
        return dict(self.best_result.params) if self.best_result else {}

    @property
    def best_score(self) -> float | None:
        return self.best_result.score if self.best_result else None

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "study_name": self.study_name,
            "best_params": self.best_params,
            "best_score": self.best_score,
            "config": {
                "n_trials": self.config.n_trials,
                "metric": self.config.metric,
                "direction": self.config.direction,
                "sampler_seed": self.config.sampler_seed,
                "study_name": self.config.study_name,
                "storage_url": self.config.storage_url,
                "load_if_exists": self.config.load_if_exists,
                "validation_fraction": self.config.validation_fraction,
                "prune_below_score": self.config.prune_below_score,
            },
            "trials": [trial.to_dict() for trial in self.trials],
        }


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


def optuna_available() -> bool:
    return find_spec("optuna") is not None


def run_optuna_optimization(
    strategy_name: str,
    symbol: str,
    data: pd.DataFrame,
    param_space: Mapping[str, Any],
    config: OptunaOptimizationConfig | None = None,
    backtest_config: BacktestConfig | None = None,
) -> OptunaOptimizationReport:
    if not optuna_available():
        raise RuntimeError("Optuna optimization requires the research dependency profile: pip install -r requirements/research.txt")

    import optuna

    config = config or OptunaOptimizationConfig()
    sampler = optuna.samplers.TPESampler(seed=config.sampler_seed)
    study = optuna.create_study(
        direction=config.direction,
        sampler=sampler,
        study_name=config.study_name,
        storage=config.storage_url,
        load_if_exists=config.load_if_exists,
    )
    strategy_cls = get_strategy(strategy_name)
    train_data, holdout_data = _optimization_split(data, config.validation_fraction)
    trial_results: dict[int, OptimizationResult] = {}

    def objective(trial) -> float:
        raw_params = {name: _suggest_parameter(trial, name, spec) for name, spec in param_space.items()}
        params = validate_strategy_params(strategy_name, raw_params)
        train_result = BacktestEngine(config=backtest_config or BacktestConfig()).run(strategy_cls(symbol, **params), train_data)
        train_score = _score_result(train_result, config.metric)
        trial.set_user_attr("train_score", train_score)
        if config.prune_below_score is not None and train_score < config.prune_below_score:
            raise optuna.TrialPruned(f"train_score_below_threshold:{train_score}")

        scored_result = train_result
        score = train_score
        if holdout_data is not None:
            holdout_result = BacktestEngine(config=backtest_config or BacktestConfig()).run(strategy_cls(symbol, **params), holdout_data)
            holdout_score = _score_result(holdout_result, config.metric)
            trial.set_user_attr("holdout_score", holdout_score)
            scored_result = holdout_result
            score = holdout_score

        trial_results[trial.number] = OptimizationResult(strategy_name, params, score, scored_result)
        return score

    study.optimize(objective, n_trials=config.n_trials)
    trials = tuple(_trial_record(trial) for trial in study.trials)
    completed = [trial for trial in study.trials if trial.value is not None and trial.number in trial_results]
    best_result = None
    if completed:
        best_number = study.best_trial.number
        best_result = trial_results.get(best_number)

    return OptunaOptimizationReport(
        strategy_name=strategy_name,
        symbol=symbol,
        config=config,
        best_result=best_result,
        trials=trials,
        study_name=study.study_name,
    )


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


def _suggest_parameter(trial: Any, name: str, spec: Any) -> Any:
    if isinstance(spec, Mapping):
        kind = spec.get("type", "categorical")
        if kind == "int":
            return trial.suggest_int(name, int(spec["low"]), int(spec["high"]), step=int(spec.get("step", 1)))
        if kind == "float":
            return trial.suggest_float(name, float(spec["low"]), float(spec["high"]), step=spec.get("step"), log=bool(spec.get("log", False)))
        choices = spec.get("choices", spec.get("values"))
        if choices is None:
            raise ValueError(f"Categorical parameter '{name}' requires choices or values.")
        return trial.suggest_categorical(name, list(choices))
    return trial.suggest_categorical(name, list(spec))


def _optimization_split(data: pd.DataFrame, validation_fraction: float) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    if validation_fraction <= 0:
        return data, None
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1.")
    split_index = max(1, int(len(data) * (1 - validation_fraction)))
    if split_index >= len(data):
        return data, None
    return data.iloc[:split_index], data.iloc[split_index:]


def _trial_record(trial: Any) -> OptunaTrialRecord:
    return OptunaTrialRecord(
        number=trial.number,
        params=dict(trial.params),
        score=trial.value,
        state=trial.state.name,
        train_score=trial.user_attrs.get("train_score"),
        holdout_score=trial.user_attrs.get("holdout_score"),
    )


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
