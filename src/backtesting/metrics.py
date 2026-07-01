from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from src.portfolio import PerformanceAnalyzer

from .interfaces import MetricsCalculator
from .types import AccountSnapshot, BacktestEvent, Fill


@dataclass(frozen=True)
class BasicMetricsCalculator(MetricsCalculator):
    """Small, dependency-light metrics set; richer analytics can replace this."""

    performance: PerformanceAnalyzer = PerformanceAnalyzer()

    def calculate(
        self,
        account_history: Sequence[AccountSnapshot],
        fills: Sequence[Fill],
        events: Sequence[BacktestEvent],
    ) -> dict:
        if not account_history:
            return {}

        equity = pd.Series(
            [snapshot.equity for snapshot in account_history],
            index=[snapshot.timestamp for snapshot in account_history],
            dtype=float,
        )
        summary = self.performance.summarize(equity)
        summary.update(
            {
            "fills": len(fills),
            "events": len(events),
            }
        )
        return summary
