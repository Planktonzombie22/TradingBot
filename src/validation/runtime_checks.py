from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from src.data import DataQualityValidator
from src.data.runtime.calendar import MarketSessionCalendar, MarketSessionPolicy

from .broker_checks import ValidationProbe


@dataclass(frozen=True)
class RecoveryDrillStage:
    name: str
    operation: Callable[[], Mapping[str, Any]]
    should_block_next_run: bool
    expected_reason: str | None = None


@dataclass(frozen=True)
class RecoveryDrillReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class WatchdogStressScenario:
    name: str
    duration_seconds: float
    timeout_seconds: float
    grace_seconds: float = 5.0
    cleanup_seconds: float = 0.0


@dataclass(frozen=True)
class WatchdogStressReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class DataQualityTortureScenario:
    name: str
    data: pd.DataFrame
    expected_codes: tuple[str, ...]
    expected_passed: bool
    description: str = ""


@dataclass(frozen=True)
class DataQualityTortureReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "probes": [probe.to_dict() for probe in self.probes],
        }


def evaluate_recovery_drills(stages: Sequence[RecoveryDrillStage]) -> RecoveryDrillReport:
    probes: list[ValidationProbe] = []
    for stage in stages:
        try:
            payload = dict(stage.operation())
        except Exception as exc:
            probes.append(ValidationProbe(stage.name, False, "drill_operation_failed", {"error": str(exc)}))
            continue
        blocked = bool(payload.get("blocked"))
        reason = str(payload.get("reason", ""))
        reason_ok = stage.expected_reason is None or reason == stage.expected_reason
        passed = blocked == stage.should_block_next_run and reason_ok
        probes.append(
            ValidationProbe(
                stage.name,
                passed,
                "passed" if passed else "recovery_drill_expectation_mismatch",
                {
                    "blocked": blocked,
                    "expected_blocked": stage.should_block_next_run,
                    "reason": reason,
                    "expected_reason": stage.expected_reason,
                    **{key: value for key, value in payload.items() if key not in {"blocked", "reason"}},
                },
            )
        )
    return RecoveryDrillReport(tuple(probes))


def default_recovery_drill_stages() -> tuple[RecoveryDrillStage, ...]:
    return (
        RecoveryDrillStage("interrupt_at_data_load", lambda: {"blocked": False, "reason": "no_prior_state"}, False, "no_prior_state"),
        RecoveryDrillStage("interrupt_after_plan_generation", lambda: {"blocked": False, "reason": "plan_not_submitted"}, False, "plan_not_submitted"),
        RecoveryDrillStage("interrupt_pre_submit", lambda: {"blocked": False, "reason": "no_broker_order_created"}, False, "no_broker_order_created"),
        RecoveryDrillStage("interrupt_post_submit_pre_reconcile", lambda: {"blocked": True, "reason": "unresolved_prior_state", "orders_loaded": 1, "reports_loaded": 0}, True, "unresolved_prior_state"),
        RecoveryDrillStage("interrupt_post_fill", lambda: {"blocked": False, "reason": "recovery_clean", "orders_loaded": 1, "reports_loaded": 1}, False, "recovery_clean"),
    )


def evaluate_watchdog_stress(scenarios: Sequence[WatchdogStressScenario]) -> WatchdogStressReport:
    probes: list[ValidationProbe] = []
    for scenario in scenarios:
        timed_out = scenario.duration_seconds > scenario.timeout_seconds
        force_exit = timed_out and scenario.cleanup_seconds > scenario.grace_seconds
        expected_exit_code = 124 if timed_out else 0
        passed = scenario.timeout_seconds > 0 and scenario.grace_seconds > 0
        probes.append(
            ValidationProbe(
                scenario.name,
                passed,
                "passed" if passed else "invalid_watchdog_policy",
                {
                    "duration_seconds": scenario.duration_seconds,
                    "timeout_seconds": scenario.timeout_seconds,
                    "grace_seconds": scenario.grace_seconds,
                    "cleanup_seconds": scenario.cleanup_seconds,
                    "timed_out": timed_out,
                    "force_exit": force_exit,
                    "expected_exit_code": expected_exit_code,
                },
            )
        )
    return WatchdogStressReport(tuple(probes))


def default_watchdog_stress_scenarios() -> tuple[WatchdogStressScenario, ...]:
    return (
        WatchdogStressScenario("normal_backtest_completes", duration_seconds=2, timeout_seconds=180),
        WatchdogStressScenario("slow_provider_interrupts", duration_seconds=360, timeout_seconds=300, cleanup_seconds=1),
        WatchdogStressScenario("stalled_strategy_forces_exit", duration_seconds=600, timeout_seconds=300, cleanup_seconds=10),
        WatchdogStressScenario("optimization_budget_allows_longer_run", duration_seconds=600, timeout_seconds=900),
        WatchdogStressScenario("bulk_research_timeout_interrupts", duration_seconds=1_200, timeout_seconds=900, cleanup_seconds=2),
    )


def evaluate_data_quality_torture(
    scenarios: Sequence[DataQualityTortureScenario] | None = None,
    validator: DataQualityValidator | None = None,
) -> DataQualityTortureReport:
    validator = validator or DataQualityValidator(stale_seconds=60)
    probes: list[ValidationProbe] = []
    for scenario in scenarios or default_data_quality_torture_scenarios():
        report = validator.validate_ohlcv(scenario.data)
        codes = tuple(issue.code for issue in report.issues)
        expected_codes = set(scenario.expected_codes)
        passed = report.passed == scenario.expected_passed and expected_codes <= set(codes)
        probes.append(
            ValidationProbe(
                scenario.name,
                passed,
                "passed" if passed else "data_quality_expectation_mismatch",
                {
                    "description": scenario.description,
                    "expected_passed": scenario.expected_passed,
                    "actual_passed": report.passed,
                    "expected_codes": list(scenario.expected_codes),
                    "actual_codes": list(codes),
                    "issues": [{"severity": issue.severity, "code": issue.code, "message": issue.message} for issue in report.issues],
                },
            )
        )
    return DataQualityTortureReport(tuple(probes))


def default_data_quality_torture_scenarios() -> tuple[DataQualityTortureScenario, ...]:
    base = _base_data()
    duplicate = pd.concat([base.iloc[[0]], base.iloc[[0]], base.iloc[[1]]])
    missing = base.copy()
    missing.loc[missing.index[1], "Close"] = None
    zero_volume = base.copy()
    zero_volume.loc[zero_volume.index[1], "Volume"] = 0
    negative_volume = base.copy()
    negative_volume.loc[negative_volume.index[1], "Volume"] = -1
    invalid_ohlc = base.copy()
    invalid_ohlc.loc[invalid_ohlc.index[0], "High"] = 90
    split_spike = base.copy()
    split_spike.loc[split_spike.index[2], ["Open", "High", "Low", "Close"]] = [50.0, 51.0, 49.0, 50.5]
    gap = _base_data(pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-20"], utc=True))
    return (
        DataQualityTortureScenario("duplicate_bars", duplicate, ("DUPLICATE_INDEX",), False, "Duplicate timestamp bars must fail."),
        DataQualityTortureScenario("missing_close", missing, ("MISSING_BARS",), False, "Missing OHLC values must fail."),
        DataQualityTortureScenario("zero_volume_allowed", zero_volume, (), True, "Zero volume can occur in some assets and should not fail by itself."),
        DataQualityTortureScenario("negative_volume", negative_volume, ("NEGATIVE_VOLUME",), False, "Negative volume is invalid."),
        DataQualityTortureScenario("invalid_ohlc", invalid_ohlc, ("INVALID_OHLC",), False, "High/low bounds must contain open/close."),
        DataQualityTortureScenario("split_like_spike", split_spike, ("SPLIT_SPIKE",), True, "Split-like jumps warn unless other checks fail."),
        DataQualityTortureScenario("calendar_gap", gap, ("TIME_GAPS",), True, "Large calendar gaps warn for review."),
    )


def evaluate_calendar_torture() -> DataQualityTortureReport:
    calendar = MarketSessionCalendar(
        holidays={"2024-01-01"},
        early_closes={"2024-07-03": datetime(2024, 7, 3, 13, 0).time()},
    )
    cases = (
        ("holiday_closed", datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc), False),
        ("regular_open", datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc), True),
        ("early_close_after_regular", datetime(2024, 7, 3, 18, 0, tzinfo=timezone.utc), False),
        ("premarket_not_tradable_default", datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc), False),
        ("premarket_allowed", datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc), True),
    )
    probes = []
    for name, timestamp, expected in cases:
        policy = MarketSessionPolicy(allow_pre_market=True) if name == "premarket_allowed" else MarketSessionPolicy()
        actual = calendar.is_tradable_at(timestamp, policy)
        probes.append(
            ValidationProbe(
                name,
                actual == expected,
                "passed" if actual == expected else "calendar_expectation_mismatch",
                {"timestamp": timestamp.isoformat(), "expected_tradable": expected, "actual_tradable": actual, "session": calendar.session_at(timestamp).value},
            )
        )
    return DataQualityTortureReport(tuple(probes))


def _base_data(index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    index = index if index is not None else pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"], utc=True)
    rows = len(index)
    base = [100.0 + index for index in range(rows)]
    return pd.DataFrame(
        {
            "Open": base,
            "High": [value + 1.0 for value in base],
            "Low": [value - 1.0 for value in base],
            "Close": [value + 0.5 for value in base],
            "Volume": [1000.0 + 100.0 * index for index in range(rows)],
        },
        index=index,
    )
