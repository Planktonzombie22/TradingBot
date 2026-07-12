import pytest

from src.utils.profiling import BenchmarkTask, benchmark_callable, run_benchmark_suite


def test_benchmark_callable_summarizes_repeated_operation():
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        return calls["count"]

    summary = benchmark_callable(
        "indicator-sma",
        operation,
        category="indicator",
        repeats=3,
        warmups=1,
        metadata={"rows": 100},
    )

    assert calls["count"] == 4
    assert summary.name == "indicator-sma"
    assert summary.category == "indicator"
    assert summary.runs == 3
    assert summary.min_seconds >= 0
    assert summary.metadata["rows"] == 100


def test_benchmark_suite_groups_categories_and_reports_candidates():
    report = run_benchmark_suite(
        [
            BenchmarkTask("storage-jsonl", lambda: sum(range(10)), category="storage_write", repeats=2),
            BenchmarkTask("paper-plan", lambda: sum(range(20)), category="paper_session_planning", repeats=2),
        ]
    )

    payload = report.to_dict()

    assert len(report.summaries) == 2
    assert len(report.measurements) == 4
    assert set(report.by_category) == {"storage_write", "paper_session_planning"}
    assert report.slowest is not None
    assert payload["slowest"]["name"] in {"storage-jsonl", "paper-plan"}
    assert report.acceleration_candidates(min_mean_seconds=0.0)


def test_benchmark_task_rejects_invalid_repeat_counts():
    with pytest.raises(ValueError):
        run_benchmark_suite([BenchmarkTask("bad", lambda: None, repeats=0)])

    with pytest.raises(ValueError):
        run_benchmark_suite([BenchmarkTask("bad", lambda: None, warmups=-1)])
