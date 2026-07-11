import pandas as pd

from src.backtesting import (
    AnnualizedBorrowCostModel,
    BarExecutionModel,
    BacktestConfig,
    BacktestEngine,
    BpsCommissionModel,
    CashMarginLedger,
    CompositeRiskModel,
    Fill,
    FixedBpsSlippageModel,
    SimpleMarginModel,
    SpreadVolumeSlippageModel,
    UnlimitedLiquidityModel,
    VolumeShareLiquidityModel,
    commission_model_for_broker,
    run_multi_symbol_backtest,
    validate_backtest_result,
)
from src.backtesting.types import AccountSnapshot, MarketSnapshot
from src.backtesting import TradeCommitteeDecision
from src.data import sample_ohlcv
from src.models import Order, Signal
from src.portfolio import (
    CapitalLedgerPolicy,
    CapitalRequest,
    EqualWeightAllocation,
    FixedNotionalAllocation,
    RiskParityAllocation,
    allocate_capital_requests,
    capital_request_from_decision,
)
from src.risk import PortfolioRiskLimits
from src.strategies.buy_hold import BuyAndHoldStrategy
from src.strategies.base import Strategy


class CostRoundTripStrategy(Strategy):
    def generate_signals(self, df):
        signals = []
        for index, timestamp in enumerate(df.index):
            if index == 0:
                signals.append(Signal("BUY", self.symbol, timestamp, stop_loss=90.0))
            elif index == 1:
                signals.append(Signal("CLOSE", self.symbol, timestamp))
            else:
                signals.append(Signal.hold(self.symbol, timestamp))
        return pd.Series(signals, index=df.index, dtype=object)


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


def test_capital_ledger_allocates_by_edge_and_enforces_family_caps():
    requests = [
        CapitalRequest("trendFast", "SPY", "trade_strategy", 0.25, family="trend", edge_score=0.05),
        CapitalRequest("trendSlow", "QQQ", "trade_strategy", 0.25, family="trend", edge_score=0.04),
        CapitalRequest("meanReversion", "IWM", "trade_strategy", 0.20, family="mean_reversion", edge_score=0.06),
    ]

    report = allocate_capital_requests(
        requests,
        CapitalLedgerPolicy(cash_reserve=0.20, max_symbol_weight=0.30, max_strategy_weight=0.30, max_family_weight=0.40),
    )
    by_strategy = {allocation.request.strategy_name: allocation for allocation in report.allocations}

    assert by_strategy["meanReversion"].allocated_weight == 0.20
    assert by_strategy["trendFast"].allocated_weight == 0.25
    assert by_strategy["trendSlow"].allocated_weight == 0.15
    assert report.weights_by_family["trend"] == 0.40
    assert report.cash_weight >= 0.20


def test_capital_ledger_keeps_hedge_budget_separate_from_primary_capital():
    requests = [
        CapitalRequest("strategy", "SPY", "trade_strategy", 0.50, family="trend", edge_score=0.10),
        CapitalRequest("portfolioHedge", "SH", "hedge", 0.25, family="hedge", edge_score=0.0),
    ]

    report = allocate_capital_requests(
        requests,
        CapitalLedgerPolicy(cash_reserve=0.20, max_symbol_weight=0.60, max_strategy_weight=0.60, max_family_weight=0.60, hedge_budget=0.10),
    )
    by_strategy = {allocation.request.strategy_name: allocation for allocation in report.allocations}

    assert by_strategy["strategy"].allocated_weight == 0.50
    assert by_strategy["portfolioHedge"].allocated_weight == 0.10
    assert report.hedge_weight == 0.10


def test_capital_request_from_committee_decision_preserves_edge_metadata():
    decision = TradeCommitteeDecision(
        symbol="SPY",
        action="trade_strategy",
        target_weight=0.25,
        strategy_name="buyHold",
        reason="approved",
        gates=(),
        metadata={"strategy_edge": 0.07},
    )

    request = capital_request_from_decision(decision, family="benchmark_relative", priority=2)

    assert request.strategy_name == "buyHold"
    assert request.symbol == "SPY"
    assert request.requested_weight == 0.25
    assert request.edge_score == 0.07
    assert request.priority == 2


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


def test_execution_model_caps_fill_quantity_by_volume_share():
    model = BarExecutionModel(
        slippage_model=FixedBpsSlippageModel(0),
        commission_model=BpsCommissionModel(0),
        liquidity_model=VolumeShareLiquidityModel(max_volume_share=0.10),
    )
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        symbol="SPY",
        open=100,
        high=101,
        low=99,
        close=100,
        volume=100,
    )
    account = AccountSnapshot(
        timestamp=pd.Timestamp("2024-01-01"),
        cash=10_000,
        equity=10_000,
        buying_power=10_000,
    )

    fill = model.execute(Order("SPY", "BUY", 50), snapshot, account)

    assert isinstance(fill, Fill)
    assert fill.quantity == 10
    assert fill.liquidity_fraction == 0.2


def test_backtest_result_includes_commission_and_slippage_costs():
    index = pd.date_range("2024-01-01", periods=2)
    data = pd.DataFrame(
        {
            "Open": [100, 100],
            "High": [101, 101],
            "Low": [99, 99],
            "Close": [100, 100],
            "Volume": [1000, 1000],
        },
        index=index,
    )
    execution_model = BarExecutionModel(
        slippage_model=FixedBpsSlippageModel(100),
        commission_model=BpsCommissionModel(100),
        liquidity_model=UnlimitedLiquidityModel(),
    )

    result = BacktestEngine(
        config=BacktestConfig(force_flat_at_end=False),
        execution_model=execution_model,
    ).run(CostRoundTripStrategy("SPY"), data)

    assert len(result.fills) == 2
    assert result.fills[0].price == 101
    assert result.fills[1].price == 99
    assert round(sum(fill.commission for fill in result.fills), 2) == 100.0
    assert round(result.total_pnl, 2) == -200.0
    assert result.metrics["starting_equity"] == 10_000
    assert round(result.metrics["total_return"], 4) == round(result.total_pnl_pct, 4)


def test_backtest_validation_report_accepts_clean_result_and_flags_metric_mismatch():
    data = sample_ohlcv("SPY", periods=40)
    result = BacktestEngine(config=BacktestConfig()).run(BuyAndHoldStrategy("SPY"), data)

    clean_report = validate_backtest_result(result)
    result.metrics["total_return"] = 999
    dirty_report = validate_backtest_result(result)

    assert clean_report.passed
    assert not dirty_report.passed
    assert any(issue.code == "TOTAL_RETURN_MISMATCH" for issue in dirty_report.issues)


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


def test_risk_model_uses_configured_execution_price_for_margin_checks():
    risk = CompositeRiskModel(SimpleMarginModel(leverage=1), price_column="Open")
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
        high=205,
        low=95,
        close=200,
    )

    rejection = risk.evaluate(Order("SPY", "BUY", 100), account, snapshot)

    assert rejection is None


def test_ledger_keeps_open_trade_after_partial_close():
    ledger = CashMarginLedger(initial_cash=10_000)
    timestamp = pd.Timestamp("2024-01-01")

    ledger.apply_fill(Fill(Order("SPY", "BUY", 100), timestamp, quantity=100, price=10))
    ledger.apply_fill(Fill(Order("SPY", "SELL", 40), timestamp, quantity=40, price=12))

    snapshot = ledger.snapshot(timestamp, prices={"SPY": 12})

    assert snapshot.positions["SPY"] == 60
    assert ledger.realized_pnl == 80
    assert len(ledger.closed_trades) == 1
    assert ledger.closed_trades[0].shares == 40
    assert ledger.closed_trades[0].pnl == 80
    assert ledger.open_trades["SPY"].shares == 60
    assert snapshot.equity == 10_200


def test_ledger_opens_new_trade_after_position_reversal():
    ledger = CashMarginLedger(initial_cash=10_000)
    timestamp = pd.Timestamp("2024-01-01")

    ledger.apply_fill(Fill(Order("SPY", "BUY", 100), timestamp, quantity=100, price=10))
    ledger.apply_fill(Fill(Order("SPY", "SELL", 150), timestamp, quantity=150, price=12))

    snapshot = ledger.snapshot(timestamp, prices={"SPY": 12})

    assert snapshot.positions["SPY"] == -50
    assert ledger.realized_pnl == 200
    assert len(ledger.closed_trades) == 1
    assert ledger.closed_trades[0].shares == 100
    assert ledger.closed_trades[0].pnl == 200
    assert ledger.open_trades["SPY"].side == "SHORT"
    assert ledger.open_trades["SPY"].shares == -50
    assert ledger.open_trades["SPY"].entry_price == 12
    assert snapshot.equity == 10_200
