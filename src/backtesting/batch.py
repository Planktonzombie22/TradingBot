from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Mapping, Sequence

from src.storage import JsonlStore
from src.strategies.base import Strategy

from .engine import BacktestEngine
from .types import BacktestConfig

StrategyFactory = Callable[[str, Mapping[str, object]], Strategy]


@dataclass(frozen=True)
class BatchBacktestJob:
    symbol: str
    strategy_name: str
    params: Dict[str, object] = field(default_factory=dict)

    @property
    def key(self) -> str:
        param_key = ",".join(f"{key}={value}" for key, value in sorted(self.params.items()))
        return f"{self.symbol}|{self.strategy_name}|{param_key}"


@dataclass(frozen=True)
class BatchBacktestSummary:
    completed: int
    skipped: int
    failed: int


class BatchBacktestRunner:
    """Resumable batch runner for symbols, strategies, and parameter sets."""

    def __init__(self, store: JsonlStore | None = None):
        self.store = store or JsonlStore("runs")

    def run(
        self,
        jobs: Sequence[BatchBacktestJob],
        data: Mapping[str, object],
        strategy_factory: StrategyFactory,
        completed_keys: Iterable[str] = (),
        config: BacktestConfig | None = None,
    ) -> BatchBacktestSummary:
        completed_set = set(completed_keys)
        completed = skipped = failed = 0
        for job in jobs:
            if job.key in completed_set:
                skipped += 1
                continue
            try:
                result = BacktestEngine(config=config or BacktestConfig()).run(
                    strategy_factory(job.symbol, job.params),
                    data[job.symbol],
                )
                self.store.append(
                    "batch-results",
                    {
                        "key": job.key,
                        "symbol": job.symbol,
                        "strategy": job.strategy_name,
                        "params": job.params,
                        "total_pnl": result.total_pnl,
                        "total_pnl_pct": result.total_pnl_pct,
                        "metrics": result.metrics,
                    },
                )
                completed += 1
            except Exception as exc:
                self.store.append(
                    "batch-errors",
                    {"key": job.key, "symbol": job.symbol, "strategy": job.strategy_name, "error": str(exc)},
                )
                failed += 1
        return BatchBacktestSummary(completed=completed, skipped=skipped, failed=failed)
