from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Any, Callable, Mapping

from .profiling import BenchmarkSuiteReport, BenchmarkSummary


ACCELERATION_BACKEND_BY_CATEGORY = {
    "indicator": "numba",
    "strategy_generation": "numba",
    "backtest_loop": "numba",
    "bulk_research": "polars",
    "storage_write": "polars",
}


@dataclass(frozen=True)
class AccelerationDecision:
    target_name: str
    category: str
    mean_seconds: float
    recommended_backend: str
    backend_available: bool
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready_for_implementation(self) -> bool:
        return self.backend_available and self.recommended_backend != "none"

    def to_dict(self) -> dict:
        return {
            "target_name": self.target_name,
            "category": self.category,
            "mean_seconds": self.mean_seconds,
            "recommended_backend": self.recommended_backend,
            "backend_available": self.backend_available,
            "ready_for_implementation": self.ready_for_implementation,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AccelerationPlan:
    decisions: tuple[AccelerationDecision, ...]
    min_mean_seconds: float

    @property
    def ready_decisions(self) -> tuple[AccelerationDecision, ...]:
        return tuple(decision for decision in self.decisions if decision.ready_for_implementation)

    def to_dict(self) -> dict:
        return {
            "min_mean_seconds": self.min_mean_seconds,
            "ready_count": len(self.ready_decisions),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


@dataclass(frozen=True)
class EquivalenceCheckResult:
    name: str
    passed: bool
    reference_value: Any
    candidate_value: Any
    reason: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reference_value": self.reference_value,
            "candidate_value": self.candidate_value,
            "reason": self.reason,
        }


def numba_available() -> bool:
    return find_spec("numba") is not None


def polars_available() -> bool:
    return find_spec("polars") is not None


def build_acceleration_plan(
    report: BenchmarkSuiteReport,
    min_mean_seconds: float = 0.10,
) -> AccelerationPlan:
    decisions = tuple(_decision(summary, min_mean_seconds) for summary in report.acceleration_candidates(min_mean_seconds))
    return AccelerationPlan(decisions, min_mean_seconds)


def check_equivalence(
    name: str,
    reference: Callable[[], Any],
    candidate: Callable[[], Any],
    comparator: Callable[[Any, Any], bool] | None = None,
) -> EquivalenceCheckResult:
    reference_value = reference()
    candidate_value = candidate()
    passed = comparator(reference_value, candidate_value) if comparator else reference_value == candidate_value
    return EquivalenceCheckResult(
        name=name,
        passed=bool(passed),
        reference_value=reference_value,
        candidate_value=candidate_value,
        reason="equivalent" if passed else "candidate_output_differs",
    )


def _decision(summary: BenchmarkSummary, min_mean_seconds: float) -> AccelerationDecision:
    backend = ACCELERATION_BACKEND_BY_CATEGORY.get(summary.category, "none")
    if backend == "numba":
        available = numba_available()
        reason = "numeric_hot_loop_candidate" if available else "numba_not_installed"
    elif backend == "polars":
        available = polars_available()
        reason = "wide_or_columnar_data_candidate" if available else "polars_not_installed"
    else:
        available = False
        reason = "no_acceleration_backend_mapped"
    return AccelerationDecision(
        target_name=summary.name,
        category=summary.category,
        mean_seconds=summary.mean_seconds,
        recommended_backend=backend,
        backend_available=available,
        reason=reason,
        metadata={
            "threshold": min_mean_seconds,
            "runs": summary.runs,
            "total_seconds": summary.total_seconds,
        },
    )
