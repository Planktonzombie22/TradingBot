from src.execution import (
    BrokerAccountSnapshot,
    BrokerPositionSnapshot,
    BrokerReconciler,
    BrokerSyncSnapshot,
    ExecutionReport,
    PaperBroker,
    ReconciliationStatus,
)
from src.models import Order
from src.backtesting import (
    PaperTradingExpectation,
    PaperTradingObservation,
    PaperTradingScorecardPolicy,
    build_paper_trading_scorecard,
)
from src.storage import SQLiteStateStore


def test_paper_broker_uses_client_order_id_for_idempotency():
    broker = PaperBroker()
    order = Order(symbol="SPY", side="BUY", quantity=1)

    first = broker.submit_order(order)
    second = broker.submit_order(order)

    assert first.id == second.id
    assert first.client_order_id is not None
    assert len(broker.orders) == 1


def test_reconciler_detects_status_mismatches_and_missing_orders():
    local = [
        Order(id="local-filled", symbol="SPY", side="BUY", quantity=1, status="FILLED"),
        Order(id="local-pending", symbol="QQQ", side="BUY", quantity=1, status="PENDING"),
    ]
    reports = [
        ExecutionReport(order_id="local-filled", status="FILLED", broker_order_id="broker-1"),
        ExecutionReport(order_id="local-pending", status="CANCELLED", broker_order_id="broker-2"),
        ExecutionReport(order_id="broker-only", status="FILLED", broker_order_id="broker-3"),
    ]

    result = BrokerReconciler().reconcile_orders(local, reports)

    statuses = {item.order_id: item.status for item in result.orders}
    assert statuses["local-filled"] == ReconciliationStatus.MATCHED
    assert statuses["local-pending"] == ReconciliationStatus.STATUS_MISMATCH
    assert statuses["broker-only"] == ReconciliationStatus.BROKER_ONLY
    assert not result.is_clean


def test_paper_trading_scorecard_passes_when_broker_behavior_matches_backtest():
    local = [Order(id="order-1", symbol="SPY", side="BUY", quantity=1, status="FILLED")]
    reports = [ExecutionReport(order_id="order-1", status="FILLED", filled_quantity=1, average_fill_price=100.05)]
    reconciliation = BrokerReconciler().reconcile_orders(local, reports)
    expectation = PaperTradingExpectation(
        strategy_name="buyHold",
        symbol="SPY",
        expected_fills=1,
        expected_trades=1,
        expected_return=0.01,
        expected_ending_equity=10_100,
        expected_fill_prices={"order-1": 100.0},
    )
    observation = PaperTradingObservation(
        reports=reports,
        account=BrokerAccountSnapshot(cash=100, buying_power=10_000, equity=10_095),
        reconciliation=reconciliation,
        broker_statement={"statement_equity": 10_095},
    )

    scorecard = build_paper_trading_scorecard(expectation, observation)

    assert scorecard.passed
    assert scorecard.reason == "paper_behavior_in_line"
    assert round(scorecard.average_slippage_bps, 2) == 5.0
    assert scorecard.to_dict()["observation"]["broker_statement"]["statement_equity"] == 10_095


def test_paper_trading_scorecard_flags_missed_rejected_and_unreconciled_orders():
    local = [
        Order(id="order-1", symbol="SPY", side="BUY", quantity=1, status="FILLED"),
        Order(id="order-2", symbol="SPY", side="BUY", quantity=1, status="PENDING"),
    ]
    reports = [
        ExecutionReport(order_id="order-1", status="FILLED", filled_quantity=1, average_fill_price=102.0),
        ExecutionReport(order_id="order-3", status="REJECTED", filled_quantity=0),
    ]
    reconciliation = BrokerReconciler().reconcile_orders(local, reports)
    expectation = PaperTradingExpectation(
        strategy_name="buyHold",
        symbol="SPY",
        expected_fills=3,
        expected_trades=2,
        expected_return=0.03,
        expected_ending_equity=10_300,
        expected_fill_prices={"order-1": 100.0},
    )
    observation = PaperTradingObservation(
        reports=reports,
        account=BrokerAccountSnapshot(cash=0, buying_power=0, equity=9_800),
        reconciliation=reconciliation,
    )

    scorecard = build_paper_trading_scorecard(
        expectation,
        observation,
        PaperTradingScorecardPolicy(max_average_slippage_bps=10, max_missed_fill_rate=0.10, max_reject_rate=0.10),
    )

    assert not scorecard.passed
    assert scorecard.reason == "slippage_too_high"
    gate_reasons = {gate.name: gate.reason for gate in scorecard.gates if not gate.passed}
    assert gate_reasons["average_slippage_bps"] == "slippage_too_high"
    assert gate_reasons["missed_fill_rate"] == "missed_fill_rate_too_high"
    assert gate_reasons["reject_rate"] == "reject_rate_too_high"
    assert gate_reasons["reconciliation"] == "unresolved_reconciliation_items"


def test_sqlite_state_store_persists_and_recovers_broker_state(tmp_path):
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    order = Order(symbol="SPY", side="BUY", quantity=3, status="PENDING", client_order_id="client-1")
    report = ExecutionReport(order_id=order.id, status="PENDING", broker_order_id="broker-1")
    account = BrokerAccountSnapshot(cash=1000, buying_power=4000, equity=1200, daytrade_count=1)
    positions = [BrokerPositionSnapshot(symbol="SPY", quantity=3, average_entry_price=100, market_value=300)]

    store.save_order(order)
    store.save_sync_snapshot(BrokerSyncSnapshot(account=account, positions=positions, open_orders=[order], reports=[report]))

    recovered = store.load_broker_state()
    broker = store.restore_paper_broker()

    assert recovered.account is not None
    assert recovered.account.buying_power == 4000
    assert recovered.positions[0].symbol == "SPY"
    assert recovered.orders[0].client_order_id == "client-1"
    assert recovered.reports[0].broker_order_id == "broker-1"
    assert broker.orders[order.id].client_order_id == "client-1"
    assert broker.reports[order.id].broker_order_id == "broker-1"
