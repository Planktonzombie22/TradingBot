from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

import pandas as pd

from src.storage import JsonlStore
from src.strategies import get_strategy, validate_strategy_params

from ..core.engine import BacktestEngine
from ..core.types import BacktestConfig

HistoricalDataLoader = Callable[[str], pd.DataFrame]


@dataclass(frozen=True)
class BulkBacktestRecord:
    symbol: str
    strategy: str
    params: Mapping[str, object]
    total_pnl: float
    total_pnl_pct: float
    metrics: Mapping[str, object]
    trades: int
    fills: int
    rejections: int

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "params": dict(self.params),
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "metrics": dict(self.metrics),
            "trades": self.trades,
            "fills": self.fills,
            "rejections": self.rejections,
        }


@dataclass(frozen=True)
class BulkBacktestError:
    symbol: str
    strategy: str
    error: str

    def to_dict(self) -> dict:
        return {"symbol": self.symbol, "strategy": self.strategy, "error": self.error}


@dataclass
class BulkBacktestReport:
    records: list[BulkBacktestRecord] = field(default_factory=list)
    errors: list[BulkBacktestError] = field(default_factory=list)

    @property
    def completed(self) -> int:
        return len(self.records)

    @property
    def failed(self) -> int:
        return len(self.errors)

    def strategy_summary(self) -> list[dict]:
        grouped: dict[str, list[BulkBacktestRecord]] = {}
        for record in self.records:
            grouped.setdefault(record.strategy, []).append(record)

        summary = []
        for strategy, records in sorted(grouped.items()):
            returns = [record.total_pnl_pct for record in records]
            drawdowns = [float(record.metrics.get("max_drawdown", 0.0)) for record in records]
            wins = [value for value in returns if value > 0]
            summary.append(
                {
                    "strategy": strategy,
                    "markets": len(records),
                    "average_return": sum(returns) / len(returns) if returns else 0.0,
                    "median_return": _median(returns),
                    "best_return": max(returns) if returns else 0.0,
                    "worst_return": min(returns) if returns else 0.0,
                    "average_max_drawdown": sum(drawdowns) / len(drawdowns) if drawdowns else 0.0,
                    "win_rate": len(wins) / len(returns) if returns else 0.0,
                    "total_trades": sum(record.trades for record in records),
                    "total_rejections": sum(record.rejections for record in records),
                }
            )
        return sorted(summary, key=lambda item: item["average_return"], reverse=True)

    def to_dict(self) -> dict:
        return {
            "completed": self.completed,
            "failed": self.failed,
            "strategy_summary": self.strategy_summary(),
            "errors": [error.to_dict() for error in self.errors],
        }


def run_bulk_backtests(
    symbols: Sequence[str],
    strategies: Sequence[str],
    data_loader: HistoricalDataLoader,
    strategy_params: Mapping[str, Mapping[str, object]] | None = None,
    config: BacktestConfig | None = None,
    store: JsonlStore | None = None,
) -> BulkBacktestReport:
    strategy_params = strategy_params or {}
    store = store or JsonlStore("runs")
    report = BulkBacktestReport()
    data_cache: dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        try:
            data_cache[symbol] = data_loader(symbol)
        except Exception as exc:
            for strategy in strategies:
                error = BulkBacktestError(symbol=symbol, strategy=strategy, error=str(exc))
                report.errors.append(error)
                store.append("bulk-errors", error.to_dict())
            continue

        for strategy_name in strategies:
            try:
                params = validate_strategy_params(strategy_name, strategy_params.get(strategy_name, {}))
                strategy = get_strategy(strategy_name)(symbol, **params)
                result = BacktestEngine(config=config or BacktestConfig()).run(strategy, data_cache[symbol])
                record = BulkBacktestRecord(
                    symbol=symbol,
                    strategy=strategy_name,
                    params=params,
                    total_pnl=result.total_pnl,
                    total_pnl_pct=result.total_pnl_pct,
                    metrics=result.metrics,
                    trades=len(result.trades),
                    fills=len(result.fills),
                    rejections=len(result.rejections),
                )
                report.records.append(record)
                store.append("bulk-results", record.to_dict())
            except Exception as exc:
                error = BulkBacktestError(symbol=symbol, strategy=strategy_name, error=str(exc))
                report.errors.append(error)
                store.append("bulk-errors", error.to_dict())
    return report


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2
