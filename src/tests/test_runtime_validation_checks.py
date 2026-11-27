import pandas as pd

from src.validation import (
    RecoveryDrillStage,
    WatchdogStressScenario,
    evaluate_calendar_torture,
    evaluate_data_quality_torture,
    evaluate_recovery_drills,
    evaluate_watchdog_stress,
)


def test_default_recovery_drills_cover_clean_and_blocked_restart_paths():
    report = evaluate_recovery_drills(
        (
            RecoveryDrillStage("post_submit", lambda: {"blocked": True, "reason": "unresolved_prior_state", "orders_loaded": 1}, True, "unresolved_prior_state"),
            RecoveryDrillStage("post_fill", lambda: {"blocked": False, "reason": "recovery_clean", "reports_loaded": 1}, False, "recovery_clean"),
        )
    )

    payload = report.to_dict()

    assert payload["passed"]
    assert payload["probes"][0]["evidence"]["orders_loaded"] == 1


def test_recovery_drill_report_flags_unexpected_resume_decisions():
    report = evaluate_recovery_drills(
        (
            RecoveryDrillStage("bad_resume", lambda: {"blocked": False, "reason": "recovery_clean"}, True, "unresolved_prior_state"),
        )
    )

    assert not report.passed
    assert report.probes[0].reason == "recovery_drill_expectation_mismatch"


def test_watchdog_stress_scenarios_report_expected_interrupt_and_force_exit_paths():
    report = evaluate_watchdog_stress(
        (
            WatchdogStressScenario("normal", duration_seconds=1, timeout_seconds=10),
            WatchdogStressScenario("interrupt", duration_seconds=20, timeout_seconds=10, cleanup_seconds=1),
            WatchdogStressScenario("force_exit", duration_seconds=20, timeout_seconds=10, grace_seconds=2, cleanup_seconds=3),
        )
    )

    evidence = {probe.name: probe.evidence for probe in report.probes}

    assert report.passed
    assert evidence["normal"]["expected_exit_code"] == 0
    assert evidence["interrupt"]["expected_exit_code"] == 124
    assert not evidence["interrupt"]["force_exit"]
    assert evidence["force_exit"]["force_exit"]


def test_data_quality_torture_report_covers_hostile_ohlcv_cases():
    report = evaluate_data_quality_torture()
    reasons = {probe.name: probe.reason for probe in report.probes}

    assert report.passed
    assert reasons["duplicate_bars"] == "passed"
    assert reasons["invalid_ohlc"] == "passed"
    assert reasons["zero_volume_allowed"] == "passed"


def test_data_quality_torture_report_flags_unexpected_validator_behavior():
    data = pd.DataFrame(
        {
            "Open": [1.0],
            "High": [2.0],
            "Low": [1.0],
            "Close": [2.0],
            "Volume": [1.0],
        },
        index=pd.to_datetime(["2024-01-02"], utc=True),
    )
    scenario = type(
        "Scenario",
        (),
        {
            "name": "expect_missing_failure",
            "data": data,
            "expected_codes": ("MISSING_BARS",),
            "expected_passed": False,
            "description": "deliberately wrong expectation",
        },
    )()

    report = evaluate_data_quality_torture((scenario,))

    assert not report.passed
    assert report.probes[0].reason == "data_quality_expectation_mismatch"


def test_calendar_torture_checks_holidays_regular_hours_early_close_and_premarket_policy():
    report = evaluate_calendar_torture()
    evidence = {probe.name: probe.evidence for probe in report.probes}

    assert report.passed
    assert evidence["holiday_closed"]["actual_tradable"] is False
    assert evidence["regular_open"]["actual_tradable"] is True
    assert evidence["premarket_not_tradable_default"]["actual_tradable"] is False
    assert evidence["premarket_allowed"]["actual_tradable"] is True
