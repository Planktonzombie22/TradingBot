from src.utils.acceleration import build_acceleration_plan, check_equivalence, numba_available, polars_available
from src.utils.profiling import BenchmarkSuiteReport, BenchmarkSummary


def test_acceleration_plan_recommends_backend_by_profiled_category():
    report = BenchmarkSuiteReport(
        summaries=(
            _summary("rsi-loop", "indicator", 0.25),
            _summary("bulk-query", "bulk_research", 0.30),
            _summary("paper-plan", "paper_session_planning", 0.40),
        ),
        measurements=(),
    )

    plan = build_acceleration_plan(report, min_mean_seconds=0.10)
    decisions = {decision.target_name: decision for decision in plan.decisions}

    assert decisions["rsi-loop"].recommended_backend == "numba"
    assert decisions["rsi-loop"].backend_available == numba_available()
    assert decisions["bulk-query"].recommended_backend == "polars"
    assert decisions["bulk-query"].backend_available == polars_available()
    assert decisions["paper-plan"].recommended_backend == "none"
    assert plan.to_dict()["decisions"]


def test_acceleration_plan_ignores_fast_enough_tasks():
    report = BenchmarkSuiteReport(
        summaries=(_summary("fast-sma", "indicator", 0.01),),
        measurements=(),
    )

    plan = build_acceleration_plan(report, min_mean_seconds=0.10)

    assert plan.decisions == ()
    assert plan.ready_decisions == ()


def test_equivalence_check_compares_reference_and_candidate_outputs():
    passing = check_equivalence("same", lambda: [1, 2, 3], lambda: [1, 2, 3])
    failing = check_equivalence("different", lambda: 1.0, lambda: 1.1, comparator=lambda left, right: abs(left - right) < 0.01)

    assert passing.passed
    assert passing.reason == "equivalent"
    assert not failing.passed
    assert failing.reason == "candidate_output_differs"


def _summary(name: str, category: str, mean_seconds: float) -> BenchmarkSummary:
    return BenchmarkSummary(
        name=name,
        category=category,
        runs=3,
        min_seconds=mean_seconds,
        max_seconds=mean_seconds,
        mean_seconds=mean_seconds,
        median_seconds=mean_seconds,
        total_seconds=mean_seconds * 3,
    )
