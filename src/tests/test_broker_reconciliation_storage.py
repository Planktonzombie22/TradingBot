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
