import pandas as pd
import pytest

from src.backtesting import (
    AccountSnapshot,
    BacktestExecutionProfile,
    BacktestPaperExpectationReport,
    CapacityAnalysisConfig,
    CorporateActionCashflowReport,
    ExecutionParityScenario,
    Fill,
    FillModelCalibrationReport,
    IntrabarExecutionAssumptionReport,
    LatencyAwareBacktestReport,
    FillObservation,
    MarginLeverageCostReport,
    MarketSnapshot,
    PaperBacktestReplayReport,
    PaperSessionRegressionFixtureReport,
    PortfolioRebalanceParityReport,
    ReferenceBacktestComparisonReport,
    ShortBorrowFeeReport,
    SlippageModelVersionReport,
    StrategyCapacityProfile,
    TransactionCostCalibration,
    analyze_capacity,
    build_backtest_paper_expectation_report,
    build_corporate_action_cashflow_report,
    build_fill_model_calibration_report,
    build_intrabar_execution_assumption_report,
    build_latency_aware_backtest_report,
    build_margin_leverage_cost_report,
    build_paper_backtest_replay_report,
    build_paper_session_regression_fixture_report,
    build_portfolio_rebalance_parity_report,
    build_reference_backtest_comparison_report,
    build_short_borrow_fee_report,
    build_slippage_model_version_report,
    compare_capacity_reports,
)
from src.models import BacktestResult, Order


def snapshot(volume=1_000):
    return MarketSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        symbol="SPY",
        open=100,
        high=101,
        low=99,
        close=100,
        volume=volume,
    )


def account():
    return AccountSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        cash=10_000,
        equity=10_000,
        buying_power=10_000,
    )


def test_transaction_cost_calibration_builds_slippage_model_from_observed_fills():
    observations = [
        FillObservation(
            symbol="SPY",
            side="BUY",
            expected_price=100,
            fill_price=100.05,
            quantity=100,
            quoted_bid=99.99,
            quoted_ask=100.01,
            bar_volume=1_000,
        ),
        FillObservation(
            symbol="SPY",
            side="SELL",
            expected_price=100,
            fill_price=99.95,
            quantity=100,
            quoted_bid=99.99,
            quoted_ask=100.01,
            bar_volume=1_000,
        ),
    ]

    calibration = TransactionCostCalibration.from_observations(observations)
    model = calibration.to_slippage_model()

    assert calibration.observations == 2
    assert calibration.spread_bps > 0
    assert calibration.impact_bps_per_volume_share > 0
    assert model.spread_bps == calibration.spread_bps


def test_backtest_execution_profile_builds_commission_slippage_and_partial_fill_model():
    profile = BacktestExecutionProfile(
        spread_bps=2,
        impact_bps_per_volume_share=10,
        max_volume_share=0.10,
        commission_bps=1,
        price_column="Close",
    )
    model = profile.build_execution_model()

    fill = model.execute(Order("SPY", "BUY", 500), snapshot(volume=1_000), account())

    assert fill.quantity == 100
    assert fill.price > 100
    assert fill.commission > 0
    assert profile.to_metadata()["max_volume_share"] == 0.10


def test_execution_parity_scenario_matches_status_and_quantity_for_market_order():
    scenario = ExecutionParityScenario(
        order=Order("SPY", "BUY", 5),
        snapshot=snapshot(),
        account=account(),
        profile=BacktestExecutionProfile(),
    )

    result = scenario.replay()

    assert result.status_matches
    assert result.quantity_matches
    assert result.backtest_price == result.paper_reference_price


def test_capacity_analysis_degrades_returns_as_capital_and_volume_share_rise():
    profile = StrategyCapacityProfile(
        strategy="fast_reversion",
        gross_return=0.20,
        gross_trade_notional=100_000,
        average_trade_notional=5_000,
        average_bar_volume_notional=50_000,
        turnover=10.0,
        short_notional_fraction=0.20,
        trades=20,
    )

    report = analyze_capacity(
        profile,
        CapacityAnalysisConfig(
            capital_levels=(10_000, 100_000, 1_000_000),
            spread_bps=4,
            impact_bps_per_volume_share=50,
            commission_bps=1,
            annual_borrow_rate=0.10,
            max_volume_participation=0.10,
            max_short_notional_fraction=0.50,
            min_net_return=0.05,
        ),
    )

    assert report.points[0].capacity_ok
    assert report.points[-1].volume_participation > 0.10
    assert not report.points[-1].capacity_ok
    assert report.points[-1].net_return < report.points[0].net_return
    assert report.estimated_capacity == 10_000
    assert report.to_dict()["config"]["max_volume_participation"] == 0.10


def test_capacity_analysis_rejects_short_heavy_system_when_borrow_is_limited():
    profile = StrategyCapacityProfile(
        strategy="short_book",
        gross_return=0.15,
        gross_trade_notional=80_000,
        average_trade_notional=2_000,
        average_bar_volume_notional=1_000_000,
        turnover=4.0,
        short_notional_fraction=0.90,
        trades=10,
    )

    report = analyze_capacity(
        profile,
        CapacityAnalysisConfig(
            capital_levels=(10_000,),
            max_short_notional_fraction=0.25,
        ),
    )

    assert not report.points[0].capacity_ok
    assert report.points[0].reason == "borrow_availability_too_low"


def test_capacity_report_ranks_higher_capacity_strategy_first():
    liquid = analyze_capacity(
        StrategyCapacityProfile("liquid_trend", 0.12, 100_000, 1_000, 1_000_000, 3.0, 0.0, 12),
        CapacityAnalysisConfig(capital_levels=(10_000, 100_000), max_volume_participation=0.10),
    )
    crowded = analyze_capacity(
        StrategyCapacityProfile("crowded_reversion", 0.18, 100_000, 10_000, 50_000, 6.0, 0.0, 30),
        CapacityAnalysisConfig(capital_levels=(10_000, 100_000), max_volume_participation=0.10),
    )

    rows = compare_capacity_reports([crowded, liquid])

    assert rows[0]["strategy"] == "liquid_trend"
    assert rows[0]["estimated_capacity"] == 100_000


def test_paper_backtest_replay_report_matches_actual_paper_fills_to_backtest_fills():
    result = backtest_result_with_fills()

    report = build_paper_backtest_replay_report(
        result,
        [
            {
                "order_id": "bt-1",
                "symbol": "SPY",
                "paper_price": 100.05,
                "paper_quantity": 2,
                "paper_timestamp": "2026-07-24T14:30:01+00:00",
            }
        ],
        max_price_drift_bps=10,
    )

    assert isinstance(report, PaperBacktestReplayReport)
    assert report.passed
    assert report.events[0].price_drift_bps == pytest.approx(5)
    assert report.events[0].reason == "paper_backtest_event_matched"


def test_paper_backtest_replay_report_flags_price_and_fill_count_mismatch():
    result = backtest_result_with_fills()

    report = build_paper_backtest_replay_report(
        result,
        [
            {"order_id": "bt-1", "symbol": "SPY", "paper_price": 101.0, "paper_quantity": 2},
            {"order_id": "extra", "symbol": "SPY", "paper_price": 100.0, "paper_quantity": 1},
        ],
        max_price_drift_bps=10,
    )

    assert not report.passed
    assert report.reason == "paper_backtest_fill_count_mismatch"
    assert report.events[0].reason == "paper_backtest_price_drift_too_high"
    assert report.events[1].reason == "paper_fill_missing_backtest_match"


def test_backtest_to_paper_expectation_report_serializes_expected_behavior_before_submit():
    report = build_backtest_paper_expectation_report(
        backtest_result_with_fills(),
        strategy_name="managedFutures",
        symbol="SPY",
        assumptions={"slippage_model_version": "paper-v1", "latency_mode": "decision-plus-submit"},
        now=pd.Timestamp("2026-07-24T14:00:00Z").to_pydatetime(),
    )

    assert isinstance(report, BacktestPaperExpectationReport)
    assert report.passed
    assert report.expectation.expected_fills == 1
    assert report.expectation.expected_fill_prices["bt-1"] == 100
    assert report.to_dict()["assumptions"]["slippage_model_version"] == "paper-v1"


def test_fill_model_calibration_report_reuses_observed_paper_fill_calibration():
    report = build_fill_model_calibration_report(
        [
            {"symbol": "SPY", "side": "BUY", "expected_price": 100, "fill_price": 100.05, "quantity": 100, "quoted_bid": 99.99, "quoted_ask": 100.01, "bar_volume": 1000},
            {"symbol": "SPY", "side": "SELL", "expected_price": 100, "fill_price": 99.95, "quantity": 100, "quoted_bid": 99.99, "quoted_ask": 100.01, "bar_volume": 1000},
        ],
        min_observations=2,
    )

    assert isinstance(report, FillModelCalibrationReport)
    assert report.passed
    assert report.calibration.observations == 2
    assert report.calibration.spread_bps > 0
    assert report.calibration.impact_bps_per_volume_share > 0


def test_slippage_model_version_report_requires_active_recorded_version():
    report = build_slippage_model_version_report(
        [
            {
                "name": "spread_volume",
                "version": "paper-v1",
                "parameters": {"spread_bps": 2, "impact_bps_per_volume_share": 10},
                "calibrated_from": "paper-session-001",
            }
        ],
        active_version="paper-v1",
    )
    missing = build_slippage_model_version_report(
        [{"name": "spread_volume", "version": "paper-v1", "parameters": {"spread_bps": 2}}],
        active_version="paper-v2",
    )

    assert isinstance(report, SlippageModelVersionReport)
    assert report.passed
    assert not missing.passed
    assert missing.reason == "active_slippage_version_missing"


def test_latency_aware_backtest_report_simulates_submission_and_fill_timestamps():
    report = build_latency_aware_backtest_report(
        [
            {
                "order_id": "fast",
                "decision_timestamp": "2026-07-24T14:30:00+00:00",
                "decision_delay_ms": 100,
                "broker_submission_delay_ms": 150,
                "fill_delay_ms": 200,
            },
            {
                "order_id": "slow",
                "decision_timestamp": "2026-07-24T14:30:00+00:00",
                "decision_delay_ms": 500,
                "broker_submission_delay_ms": 600,
                "fill_delay_ms": 100,
            },
        ],
        max_total_latency_ms=1000,
    )

    assert isinstance(report, LatencyAwareBacktestReport)
    assert not report.passed
    assert report.events[0].simulated_submission_timestamp == "2026-07-24T14:30:00.250000+00:00"
    assert report.events[0].simulated_fill_timestamp == "2026-07-24T14:30:00.450000+00:00"
    assert report.events[1].reason == "latency_total_above_threshold"


def test_intrabar_execution_assumption_report_validates_stop_limit_and_bracket_behavior():
    report = build_intrabar_execution_assumption_report(
        [
            {"order_id": "stop-1", "symbol": "SPY", "order_type": "STOP", "side": "SELL", "low": 94, "high": 101, "stop_price": 95, "paper_triggered": True, "paper_price": 95.02},
            {"order_id": "limit-1", "symbol": "QQQ", "order_type": "LIMIT", "side": "BUY", "low": 99, "high": 105, "limit_price": 100, "paper_triggered": True, "paper_price": 100.01},
            {"order_id": "bracket-1", "symbol": "GLD", "order_type": "BRACKET", "low": 190, "high": 202, "stop_loss": 192, "take_profit_price": 205, "paper_triggered": False},
        ],
        max_price_drift_bps=5,
    )

    assert isinstance(report, IntrabarExecutionAssumptionReport)
    assert not report.passed
    assert report.checks[0].passed
    assert report.checks[1].passed
    assert report.checks[2].reason == "intrabar_trigger_mismatch"


def test_short_borrow_fee_report_blocks_missing_locates_and_high_borrow_costs():
    report = build_short_borrow_fee_report(
        [
            {"symbol": "SPY", "short_notional": 10_000, "locate_available": True, "borrow_rate": 0.05, "holding_days": 10},
            {"symbol": "ILLQ", "short_notional": 2_000, "locate_available": False, "borrow_rate": 0.01, "holding_days": 5},
            {"symbol": "HARD", "short_notional": 1_000, "locate_available": True, "borrow_rate": 0.50, "holding_days": 5},
        ],
        max_borrow_rate=0.20,
    )

    assert isinstance(report, ShortBorrowFeeReport)
    assert not report.passed
    checks = {check.symbol: check for check in report.checks}
    assert checks["SPY"].passed
    assert checks["ILLQ"].reason == "short_locate_unavailable"
    assert checks["HARD"].reason == "short_borrow_rate_too_high"


def test_margin_leverage_cost_report_estimates_interest_and_blocks_excess_leverage():
    report = build_margin_leverage_cost_report(
        [
            {"symbol": "SPY", "borrowed_notional": 5_000, "margin_rate": 0.08, "holding_days": 30, "leverage": 1.2},
            {"symbol": "QQQ", "borrowed_notional": 8_000, "margin_rate": 0.08, "holding_days": 30, "leverage": 2.5},
        ],
        max_leverage=2.0,
        max_total_interest=200,
    )

    assert isinstance(report, MarginLeverageCostReport)
    assert not report.passed
    assert report.checks[0].passed
    assert report.checks[1].reason == "margin_leverage_too_high"
    assert report.total_estimated_interest == pytest.approx((5_000 + 8_000) * 0.08 * 30 / 365)


def test_corporate_action_cashflow_report_models_dividends_and_splits():
    report = build_corporate_action_cashflow_report(
        [
            {"symbol": "SPY", "action_type": "dividend", "quantity": 10, "dividend_per_share": 1.25, "cashflow": 12.5, "quantity_after": 10},
            {"symbol": "AAPL", "action_type": "split", "quantity": 5, "split_ratio": 4, "cashflow": 0, "quantity_after": 20},
            {"symbol": "BAD", "action_type": "dividend", "quantity": 4, "dividend_per_share": 1.0, "cashflow": 1.0},
        ]
    )

    assert isinstance(report, CorporateActionCashflowReport)
    assert not report.passed
    assert report.checks[0].passed
    assert report.checks[1].expected_quantity_after == 20
    assert report.checks[2].reason == "corporate_action_cashflow_mismatch"


def test_portfolio_rebalance_parity_report_compares_backtest_and_paper_targets():
    report = build_portfolio_rebalance_parity_report(
        [
            {"symbol": "SPY", "backtest_target_notional": 1_000, "paper_target_notional": 1_000.5},
            {"symbol": "QQQ", "backtest_target_notional": 500, "paper_target_notional": 540, "tolerance_notional": 10},
        ],
        default_tolerance_notional=1,
    )

    assert isinstance(report, PortfolioRebalanceParityReport)
    assert not report.passed
    assert report.checks[0].passed
    assert report.checks[1].reason == "portfolio_rebalance_target_mismatch"


def test_reference_backtest_comparison_report_flags_external_reference_drift():
    report = build_reference_backtest_comparison_report(
        [
            {"scenario": "portfolio_partial_fill", "metric": "ending_equity", "local_value": 10010, "reference_value": 10010.5, "tolerance": 1},
            {"scenario": "rebalance_exit", "metric": "fills", "local_value": 4, "reference_value": 5, "tolerance": 0},
        ]
    )

    assert isinstance(report, ReferenceBacktestComparisonReport)
    assert not report.passed
    assert report.comparisons[0].passed
    assert report.comparisons[1].reason == "reference_backtest_comparison_drift"


def test_paper_session_regression_fixture_report_requires_replay_scorecard_monitor_and_reconciliation():
    report = build_paper_session_regression_fixture_report(
        [
            {
                "fixture_id": "paper-session-001",
                "artifact_paths": ["runs/session.json", "runs/monitor.json"],
                "replay_passed": True,
                "scorecard_passed": True,
                "monitor_passed": True,
                "broker_reconciliation_passed": True,
            },
            {
                "fixture_id": "paper-session-002",
                "artifact_paths": ["runs/session-2.json"],
                "replay_passed": True,
                "scorecard_passed": False,
                "monitor_passed": True,
                "broker_reconciliation_passed": True,
            },
        ]
    )

    assert isinstance(report, PaperSessionRegressionFixtureReport)
    assert not report.passed
    assert report.fixtures[0].passed
    assert report.fixtures[1].reason == "paper_fixture_scorecard_failed"


def backtest_result_with_fills():
    order = Order("SPY", "BUY", 2, id="bt-1")
    fill = Fill(order=order, timestamp=pd.Timestamp("2026-07-24T14:30:00Z").to_pydatetime(), quantity=2, price=100)
    return BacktestResult(
        trades=[],
        equity=pd.Series([10_000, 10_010]),
        money_available=pd.Series([10_000, 9_800]),
        total_pnl=10,
        total_pnl_pct=0.001,
        fills=[fill],
        metrics={"ending_equity": 10_010},
    )
