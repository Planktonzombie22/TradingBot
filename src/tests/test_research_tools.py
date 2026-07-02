import pytest

from src.backtesting import grid_search, run_walk_forward
from src.data import sample_ohlcv
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
