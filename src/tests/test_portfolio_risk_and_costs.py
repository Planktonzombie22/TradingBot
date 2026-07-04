import pandas as pd

from src.backtesting import (
    AnnualizedBorrowCostModel,
    BacktestConfig,
    CompositeRiskModel,
    SimpleMarginModel,
    SpreadVolumeSlippageModel,
    commission_model_for_broker,
    run_multi_symbol_backtest,
)
from src.backtesting.types import AccountSnapshot, MarketSnapshot
from src.data import sample_ohlcv
from src.models import Order
from src.portfolio import EqualWeightAllocation, FixedNotionalAllocation, RiskParityAllocation
from src.risk import PortfolioRiskLimits
from src.strategies.buy_hold import BuyAndHoldStrategy


def test_multi_symbol_backtest_aggregates_results():
    data = {
        "SPY": sample_ohlcv("SPY", periods=40),
        "QQQ": sample_ohlcv("QQQ", periods=40),
    }

    result = run_multi_symbol_backtest(
        data=data,
        strategy_factory=lambda symbol: BuyAndHoldStrategy(symbol),
        config=BacktestConfig(initial_cash=10_000),
    )

    assert set(result.symbol_results) == {"SPY", "QQQ"}
    assert len(result.fills) == 4
    assert result.equity.iloc[-1] > 0


def test_portfolio_limits_reject_concentrated_order():
    limits = PortfolioRiskLimits(max_symbol_weight=0.20, max_gross_exposure=1.0)

    decision = limits.evaluate_order("SPY", order_notional=3_000, equity=10_000, exposures={})

    assert not decision.accepted


def test_portfolio_limits_reject_high_correlation():
    returns = pd.DataFrame(
        {
            "SPY": [0.01, 0.02, -0.01, 0.03],
            "QQQ": [0.011, 0.021, -0.009, 0.031],
        }
    )
    limits = PortfolioRiskLimits(max_pairwise_correlation=0.80)

    decision = limits.evaluate_correlation(returns)

    assert not decision.accepted


def test_portfolio_allocation_policies_create_targets():
    equal = EqualWeightAllocation(gross_exposure=0.8).allocate(["SPY", "QQQ"], equity=10_000)
    fixed = FixedNotionalAllocation(notional_per_symbol=1_000).allocate(["SPY", "QQQ"], equity=10_000)

    assert [target.notional for target in equal] == [4_000, 4_000]
    assert [target.weight for target in fixed] == [0.1, 0.1]


def test_risk_parity_allocates_more_to_lower_volatility_symbol():
    returns = pd.DataFrame(
        {
            "LOW": [0.001, 0.002, 0.001, 0.002],
            "HIGH": [0.01, -0.02, 0.03, -0.01],
        }
    )

    targets = RiskParityAllocation(gross_exposure=1.0).allocate(["LOW", "HIGH"], equity=10_000, returns=returns)
    by_symbol = {target.symbol: target.weight for target in targets}

    assert by_symbol["LOW"] > by_symbol["HIGH"]


def test_portfolio_limits_reject_cash_reserve_and_beta_breaches():
    reserve_limits = PortfolioRiskLimits(max_symbol_weight=1.0, max_gross_exposure=1.0, min_cash_reserve=0.20)
    beta_limits = PortfolioRiskLimits(
        max_symbol_weight=1.0,
        max_gross_exposure=2.0,
        max_net_beta=0.5,
        beta_map={"SPY": 1.2},
    )

    reserve_decision = reserve_limits.evaluate_order("SPY", order_notional=9_000, equity=10_000, exposures={})
    beta_decision = beta_limits.evaluate_order("SPY", order_notional=6_000, equity=10_000, exposures={})

    assert not reserve_decision.accepted
    assert not beta_decision.accepted


def test_spread_volume_slippage_moves_price_against_order():
    model = SpreadVolumeSlippageModel(spread_bps=2, impact_bps_per_volume_share=10)
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        symbol="SPY",
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1000,
    )

    buy_price = model.apply(Order("SPY", "BUY", 100), snapshot, 100)
    sell_price = model.apply(Order("SPY", "SELL", 100), snapshot, 100)

    assert buy_price > 100
    assert sell_price < 100


def test_commission_presets_and_borrow_costs():
    ibkr = commission_model_for_broker("ibkr")
    fee = ibkr.calculate(Order("SPY", "BUY", 10), fill_price=100, fill_quantity=10)
    assert fee >= 1.0

    account = AccountSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        cash=10_000,
        equity=10_000,
        buying_power=10_000,
        positions={"SPY": -10},
    )
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        symbol="SPY",
        open=100,
        high=101,
        low=99,
        close=100,
    )
    borrow = AnnualizedBorrowCostModel(annual_rate=0.10).accrue(account, snapshot)
    assert borrow > 0


def test_short_locate_rejection():
    risk = CompositeRiskModel(SimpleMarginModel(), allow_shorting=True, shortable_symbols={"QQQ"})
    account = AccountSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        cash=10_000,
        equity=10_000,
        buying_power=10_000,
    )
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        symbol="SPY",
        open=100,
        high=101,
        low=99,
        close=100,
    )

    rejection = risk.evaluate(Order("SPY", "SELL", 1), account, snapshot)

    assert rejection is not None
    assert rejection.message == "Short locate unavailable."
