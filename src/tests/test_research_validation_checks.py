from src.validation import (
    BacktestDifferentialScenario,
    OptimizerValidationCase,
    PortfolioRiskStressScenario,
    StrategyRobustnessCase,
    default_portfolio_risk_stress_scenarios,
    evaluate_backtest_differential,
    evaluate_optimizer_validation,
    evaluate_portfolio_risk_stress,
    evaluate_strategy_robustness,
)


def test_backtest_differential_report_compares_observed_to_reference_metrics():
    clean = BacktestDifferentialScenario(
        "buy_hold_math",
        observed={"total_return": 0.10, "ending_equity": 11_000, "fills": 1},
        reference={"total_return": 0.10001, "ending_equity": 11_000.5, "fills": 1},
        tolerances={"total_return": 0.001, "ending_equity": 1.0},
    )
    dirty = BacktestDifferentialScenario(
        "slippage_mismatch",
        observed={"total_return": 0.05, "ending_equity": 10_500, "fills": 3},
        reference={"total_return": 0.10, "ending_equity": 11_000, "fills": 1},
        tolerances={"total_return": 0.001, "ending_equity": 1.0},
    )

    report = evaluate_backtest_differential((clean, dirty))
    probes = {probe.name: probe for probe in report.probes}

    assert not report.passed
    assert probes["buy_hold_math"].passed
    assert probes["slippage_mismatch"].reason == "backtest_differential_mismatch"
    assert "total_return" in probes["slippage_mismatch"].evidence["failures"]
    assert "fills" in probes["slippage_mismatch"].evidence["failures"]


def test_backtest_differential_report_flags_missing_required_fields():
    report = evaluate_backtest_differential(
        (
            BacktestDifferentialScenario(
                "missing_fills",
                observed={"total_return": 0.1, "ending_equity": 11_000},
                reference={"total_return": 0.1, "ending_equity": 11_000, "fills": 1},
            ),
        )
    )

    assert not report.passed
    assert report.probes[0].reason == "missing_required_fields"


def test_strategy_robustness_report_requires_all_promotion_survival_gates():
    report = evaluate_strategy_robustness(
        (
            StrategyRobustnessCase("stable_trend", True, 0.75, 0.80, True, True),
            StrategyRobustnessCase("fragile_reversion", True, 0.20, 0.40, True, False),
        )
    )
    probes = {probe.name: probe for probe in report.probes}

    assert not report.passed
    assert probes["stable_trend"].passed
    assert probes["fragile_reversion"].reason == "strategy_robustness_failed"
    assert not probes["fragile_reversion"].evidence["checks"]["benchmark_relative_passed"]


def test_optimizer_validation_report_requires_reproducibility_and_no_leakage():
    report = evaluate_optimizer_validation(
        (
            OptimizerValidationCase("clean_grid", True, True, True, True, True, True),
            OptimizerValidationCase("leaky_study", True, False, False, True, True, True),
        )
    )

    probes = {probe.name: probe for probe in report.probes}

    assert not report.passed
    assert probes["clean_grid"].passed
    assert probes["leaky_study"].reason == "optimizer_validation_failed"
    assert not probes["leaky_study"].evidence["checks"]["train_test_separated"]
    assert not probes["leaky_study"].evidence["checks"]["no_lookahead_detected"]


def test_portfolio_risk_stress_report_checks_expected_actions_and_limits():
    clean = evaluate_portfolio_risk_stress(default_portfolio_risk_stress_scenarios())
    dirty = evaluate_portfolio_risk_stress(
        (
            PortfolioRiskStressScenario("concentration_limit", "block", "allow", exposure=0.40, limit=0.25),
            PortfolioRiskStressScenario("normal_allocation", "allow", "allow", exposure=0.20, limit=0.25),
        )
    )

    assert clean.passed
    assert not dirty.passed
    probes = {probe.name: probe for probe in dirty.probes}
    assert probes["concentration_limit"].reason == "portfolio_risk_stress_failed"
    assert probes["normal_allocation"].passed
