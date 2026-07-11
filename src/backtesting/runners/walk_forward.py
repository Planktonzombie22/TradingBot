from dataclasses import dataclass
from typing import Callable, List

import pandas as pd

from src.models import BacktestResult
from src.strategies.core.base import Strategy

from ..core.engine import BacktestEngine
from ..core.types import BacktestConfig


StrategyFactory = Callable[[], Strategy]


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    result: BacktestResult


def run_walk_forward(
    data: pd.DataFrame,
    strategy_factory: StrategyFactory,
    train_size: int,
    test_size: int,
    config: BacktestConfig | None = None,
) -> List[WalkForwardWindow]:
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive.")
    if len(data) < train_size + test_size:
        raise ValueError("Not enough data for one walk-forward split.")

    windows: List[WalkForwardWindow] = []
    start = 0
    while start + train_size + test_size <= len(data):
        train = data.iloc[start : start + train_size]
        test = data.iloc[start + train_size : start + train_size + test_size]
        result = BacktestEngine(config=config or BacktestConfig()).run(strategy_factory(), test)
        windows.append(
            WalkForwardWindow(
                train_start=train.index[0],
                train_end=train.index[-1],
                test_start=test.index[0],
                test_end=test.index[-1],
                result=result,
            )
        )
        start += test_size
    return windows
