from src.backtesting import (
    OptimizationBudgetReport,
    OptimizationReproducibilityReport,
    PromotionOverfittingWarningReport,
    SurvivorshipBiasAwarenessReport,
    WalkForwardDeploymentSimulationReport,
    build_optimization_budget_report,
    build_optimization_reproducibility_report,
    build_promotion_overfitting_warning_report,
    build_survivorship_bias_awareness_report,
    build_walk_forward_deployment_simulation_report,
)


def test_optimization_reproducibility_report_compares_code_dependencies_seed_params_and_score():
    baseline = {
        "code_version": "abc123",
        "dependency_versions": {"pandas": "2.2.0", "numpy": "2.0.0"},
        "sampler_seed": 42,
        "best_params": {"lookback": 20},
        "best_score": 0.123456,
    }
    candidate = dict(baseline)

    passed = build_optimization_reproducibility_report(baseline, candidate)
    failed = build_optimization_reproducibility_report(baseline, {**candidate, "best_params": {"lookback": 30}})

    assert isinstance(passed, OptimizationReproducibilityReport)
    assert passed.passed
    assert not failed.passed
    assert failed.reason == "optimization_best_params_mismatch"


def test_optimization_budget_report_enforces_trials_runtime_memory_and_failed_trial_rate():
    passed = build_optimization_budget_report(40, 2, 120, 512, max_trials=50, max_failed_trial_rate=0.10)
    failed = build_optimization_budget_report(40, 10, 120, 512, max_trials=50, max_failed_trial_rate=0.10)

    assert isinstance(passed, OptimizationBudgetReport)
    assert passed.passed
    assert failed.failed_trial_rate == 0.25
    assert failed.reason == "optimization_failed_trial_rate_exceeded"


def test_promotion_overfitting_warning_report_embeds_warnings_into_manifest_payload():
    report = build_promotion_overfitting_warning_report(
        {"strategy_name": "trend", "symbol": "SPY", "params": {"lookback": 20}},
        parameter_stability_score=0.25,
        false_discovery_rate=0.70,
        train_score=0.30,
        holdout_score=0.05,
        trials=150,
        max_train_holdout_gap=0.10,
    )

    assert isinstance(report, PromotionOverfittingWarningReport)
    assert not report.passed
    assert report.warning_reasons == (
        "parameter_surface_unstable",
        "false_discovery_rate_warning",
        "train_holdout_gap_warning",
        "optimization_trial_count_warning",
    )
    assert report.to_dict()["manifest"]["warning_reasons"][0] == "parameter_surface_unstable"


def test_survivorship_bias_awareness_report_blocks_late_listings_and_included_delistings():
    report = build_survivorship_bias_awareness_report(
        [
            {"symbol": "SPY", "listed_at": "1993-01-29", "included": True},
            {"symbol": "NEW", "listed_at": "2025-01-01", "included": True},
            {"symbol": "OLD", "listed_at": "2000-01-01", "delisted_at": "2024-06-01", "included": True},
            {"symbol": "REMOVED", "listed_at": "2000-01-01", "delisted_at": "2024-06-01", "included": False},
        ],
        backtest_start="2024-01-01",
        backtest_end="2024-12-31",
    )

    assert isinstance(report, SurvivorshipBiasAwarenessReport)
    assert not report.passed
    checks = {check.symbol: check for check in report.checks}
    assert checks["SPY"].passed
    assert checks["NEW"].reason == "symbol_listed_after_backtest_start"
    assert checks["OLD"].reason == "delisted_symbol_included_without_bias_control"
    assert checks["REMOVED"].passed


def test_walk_forward_deployment_simulation_requires_prior_data_only_selection():
    report = build_walk_forward_deployment_simulation_report(
        [
            {
                "strategy_name": "trend",
                "symbol": "SPY",
                "decision_at": "2026-07-24T14:00:00+00:00",
                "selected_at": "2026-07-24T14:05:00+00:00",
                "latest_data_used_at": "2026-07-23T21:00:00+00:00",
                "deployment_start_at": "2026-07-25T14:30:00+00:00",
            },
            {
                "strategy_name": "futureLeak",
                "symbol": "QQQ",
                "decision_at": "2026-07-24T14:00:00+00:00",
                "selected_at": "2026-07-24T14:05:00+00:00",
                "latest_data_used_at": "2026-07-25T21:00:00+00:00",
                "deployment_start_at": "2026-07-25T14:30:00+00:00",
            },
        ]
    )

    assert isinstance(report, WalkForwardDeploymentSimulationReport)
    assert not report.passed
    assert report.decisions[0].passed
    assert report.decisions[1].reason == "deployment_used_future_data"
