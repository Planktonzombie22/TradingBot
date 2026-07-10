import pandas as pd

from src.backtesting import (
    AccountSnapshot,
    BacktestExecutionProfile,
    CapacityAnalysisConfig,
    ExecutionParityScenario,
    FillObservation,
    MarketSnapshot,
    StrategyCapacityProfile,
    TransactionCostCalibration,
    analyze_capacity,
    compare_capacity_reports,
)
from src.models import Order


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
