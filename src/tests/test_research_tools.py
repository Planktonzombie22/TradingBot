import pytest

from src.backtesting import (
    BatchBacktestJob,
    BatchBacktestRunner,
    grid_search,
    overfitting_report,
    rank_optimization_results,
    run_walk_forward,
)
from src.data import sample_ohlcv
from src.storage import JsonlStore
from src.strategies import validate_strategy_params
from src.strategies.buy_hold import BuyAndHoldStrategy


def test_strategy_parameter_validation_rejects_unknown_params():
    with pytest.raises(ValueError):
        validate_strategy_params("buyHold", {"unknown": 1})


def test_walk_forward_runs_multiple_test_windows():
    data = sample_ohlcv(periods=80)

    windows = run_walk_forward(
        data=data,
        strategy_factory=lambda: BuyAndHoldStrategy("SPY"),
        train_size=20,
        test_size=20,
    )

    assert len(windows) == 3
    assert all(window.result.metrics["ending_equity"] > 0 for window in windows)


def test_grid_search_returns_sorted_results():
    data = sample_ohlcv(periods=40)

    results = grid_search(
        strategy_name="buyHold",
        symbol="SPY",
        data=data,
        param_grid={"stop_percent": [0.03, 0.05]},
    )

    assert len(results) == 2
    assert results[0].score >= results[1].score


def test_optimization_ranking_and_overfitting_report():
    data = sample_ohlcv(periods=60)
    results = grid_search(
        strategy_name="buyHold",
        symbol="SPY",
        data=data,
        param_grid={"stop_percent": [0.03, 0.05]},
    )

    ranked = rank_optimization_results(results)
    report = overfitting_report(results[0].result, results[-1].result, min_trades=1)

    assert len(ranked) == 2
    assert "sharpe" in ranked[0].rank_metrics()
    assert report.minimum_trade_count_met


def test_batch_backtest_runner_skips_completed_jobs_and_writes_artifacts(tmp_path):
    data = {"SPY": sample_ohlcv("SPY", periods=40), "QQQ": sample_ohlcv("QQQ", periods=40)}
    jobs = [
        BatchBacktestJob("SPY", "buyHold", {"stop_percent": 0.05}),
        BatchBacktestJob("QQQ", "buyHold", {"stop_percent": 0.05}),
    ]
    runner = BatchBacktestRunner(JsonlStore(tmp_path))

    summary = runner.run(
        jobs,
        data=data,
        strategy_factory=lambda symbol, params: BuyAndHoldStrategy(symbol, **params),
        completed_keys=[jobs[0].key],
    )

    assert summary.completed == 1
    assert summary.skipped == 1
    assert (tmp_path / "batch-results.jsonl").exists()
