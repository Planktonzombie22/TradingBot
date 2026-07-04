import pandas as pd

from src.backtesting import (
    AccountSnapshot,
    BacktestExecutionProfile,
    ExecutionParityScenario,
    FillObservation,
    MarketSnapshot,
    TransactionCostCalibration,
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
