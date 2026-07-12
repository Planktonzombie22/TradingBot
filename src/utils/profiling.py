from dataclasses import dataclass, field
from statistics import mean, median
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence


DEFAULT_BENCHMARK_CATEGORIES = (
    "indicator",
    "strategy_generation",
    "backtest_loop",
    "bulk_research",
    "storage_write",
    "paper_session_planning",
)


@dataclass(frozen=True)
class BenchmarkTask:
    name: str
    operation: Callable[[], Any]
    category: str = "general"
    repeats: int = 3
    warmups: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkMeasurement:
    name: str
    category: str
    elapsed_seconds: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass(frozen=True)
class BenchmarkSummary:
    name: str
    category: str
    runs: int
    min_seconds: float
    max_seconds: float
    mean_seconds: float
    median_seconds: float
    total_seconds: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "runs": self.runs,
            "min_seconds": self.min_seconds,
            "max_seconds": self.max_seconds,
            "mean_seconds": self.mean_seconds,
            "median_seconds": self.median_seconds,
            "total_seconds": self.total_seconds,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class BenchmarkSuiteReport:
    summaries: tuple[BenchmarkSummary, ...]
    measurements: tuple[BenchmarkMeasurement, ...]

    @property
    def total_elapsed_seconds(self) -> float:
        return sum(summary.total_seconds for summary in self.summaries)

    @property
    def slowest(self) -> BenchmarkSummary | None:
        if not self.summaries:
            return None
        return max(self.summaries, key=lambda summary: summary.mean_seconds)

    @property
    def by_category(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for summary in self.summaries:
            totals[summary.category] = totals.get(summary.category, 0.0) + summary.total_seconds
        return totals

    def acceleration_candidates(self, min_mean_seconds: float = 0.10) -> tuple[BenchmarkSummary, ...]:
        return tuple(
            sorted(
                (summary for summary in self.summaries if summary.mean_seconds >= min_mean_seconds),
                key=lambda summary: summary.mean_seconds,
                reverse=True,
            )
        )

    def to_dict(self) -> dict:
        return {
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "slowest": self.slowest.to_dict() if self.slowest else None,
            "by_category": dict(self.by_category),
            "summaries": [summary.to_dict() for summary in self.summaries],
            "measurements": [measurement.to_dict() for measurement in self.measurements],
        }


def benchmark_callable(
    name: str,
    operation: Callable[[], Any],
    category: str = "general",
    repeats: int = 3,
    warmups: int = 0,
    metadata: Mapping[str, Any] | None = None,
) -> BenchmarkSummary:
    return run_benchmark_task(
        BenchmarkTask(
            name=name,
            operation=operation,
            category=category,
            repeats=repeats,
            warmups=warmups,
            metadata=dict(metadata or {}),
        )
    )[0]


def run_benchmark_task(task: BenchmarkTask) -> tuple[BenchmarkSummary, tuple[BenchmarkMeasurement, ...]]:
    if task.repeats <= 0:
        raise ValueError("BenchmarkTask.repeats must be positive.")
    if task.warmups < 0:
        raise ValueError("BenchmarkTask.warmups cannot be negative.")

    for _ in range(task.warmups):
        task.operation()

    measurements = []
    for _ in range(task.repeats):
        start = perf_counter()
        task.operation()
        measurements.append(
            BenchmarkMeasurement(
                name=task.name,
                category=task.category,
                elapsed_seconds=perf_counter() - start,
            )
        )
    summary = _summary(task, measurements)
    return summary, tuple(measurements)


def run_benchmark_suite(tasks: Sequence[BenchmarkTask]) -> BenchmarkSuiteReport:
    summaries: list[BenchmarkSummary] = []
    measurements: list[BenchmarkMeasurement] = []
    for task in tasks:
        summary, task_measurements = run_benchmark_task(task)
        summaries.append(summary)
        measurements.extend(task_measurements)
    return BenchmarkSuiteReport(tuple(summaries), tuple(measurements))


def _summary(task: BenchmarkTask, measurements: Sequence[BenchmarkMeasurement]) -> BenchmarkSummary:
    values = [measurement.elapsed_seconds for measurement in measurements]
    return BenchmarkSummary(
        name=task.name,
        category=task.category,
        runs=len(values),
        min_seconds=min(values),
        max_seconds=max(values),
        mean_seconds=mean(values),
        median_seconds=median(values),
        total_seconds=sum(values),
        metadata=dict(task.metadata),
    )
