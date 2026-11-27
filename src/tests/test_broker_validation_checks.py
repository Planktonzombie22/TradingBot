import pandas as pd

from src.execution import BrokerAccountSnapshot, BrokerPositionSnapshot, ExecutionReport, PaperBroker
from src.models import Order
from src.validation import (
    FailureInjectionScenario,
    evaluate_alpaca_data_connectivity,
    evaluate_broker_account_parity,
    evaluate_failure_injection,
    evaluate_paper_order_lifecycle,
)


def _bars(close=100.0):
    return pd.DataFrame(
        {
            "Open": [close - 1],
            "High": [close + 1],
            "Low": [close - 2],
            "Close": [close],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2024-01-02T00:00:00Z"]),
    )


def test_alpaca_data_connectivity_report_passes_with_history_latest_stream_and_drift():
    report = evaluate_alpaca_data_connectivity(
        historical_loader=lambda: _bars(100),
        latest_probe=lambda: {"passed": True, "quote": {"bid": 99.9, "ask": 100.1}},
        websocket_probe=lambda: {"passed": True, "events": 1, "reconnects": 0},
        secondary_loader=lambda: _bars(100.5),
        max_close_drift_pct=0.01,
    )

    payload = report.to_dict()

    assert payload["passed"]
    assert {probe["name"] for probe in payload["probes"]} == {
        "historical_bars",
        "latest_market_data",
        "websocket_stream",
        "secondary_provider_drift",
    }


def test_alpaca_data_connectivity_report_flags_loader_and_drift_failures():
    report = evaluate_alpaca_data_connectivity(
        historical_loader=lambda: _bars(100),
        latest_probe=lambda: (_ for _ in ()).throw(RuntimeError("latest down")),
        secondary_loader=lambda: _bars(120),
        max_close_drift_pct=0.01,
    )

    reasons = {probe.name: probe.reason for probe in report.probes}

    assert not report.passed
    assert reasons["latest_market_data"] == "latest_market_data_failed"
    assert reasons["secondary_provider_drift"] == "close_drift_too_high"


def test_paper_order_lifecycle_report_covers_submit_duplicate_cancel_and_reconciliation():
    broker = PaperBroker(auto_fill_market_orders=False)
    order = Order(symbol="SPY", side="BUY", quantity=1, order_type="LIMIT", limit_price=100)
    replacement = Order(symbol="SPY", side="BUY", quantity=2, order_type="LIMIT", limit_price=99)

    report = evaluate_paper_order_lifecycle(broker, order, replacement)
    payload = report.to_dict()

    assert payload["passed"]
    assert {probe["name"] for probe in payload["probes"]} >= {
        "submit_acknowledged",
        "duplicate_client_order_protected",
        "replace_acknowledged",
        "cancel_acknowledged",
        "reconciliation_clean",
    }
    assert payload["orders"][-1]["status"] == "CANCELLED"


def test_broker_account_parity_report_detects_clean_and_dirty_state():
    account = BrokerAccountSnapshot(cash=1000, buying_power=2000, equity=1500)
    positions = [BrokerPositionSnapshot(symbol="SPY", quantity=3)]
    orders = [Order(id="order-1", client_order_id="client-1", symbol="SPY", side="BUY", quantity=1)]
    reports = [ExecutionReport(order_id="order-1", status="FILLED", broker_order_id="broker-1")]

    clean = evaluate_broker_account_parity(account, account, positions, positions, orders, orders, reports, reports)
    dirty = evaluate_broker_account_parity(
        account,
        BrokerAccountSnapshot(cash=900, buying_power=2000, equity=1500),
        positions,
        [BrokerPositionSnapshot(symbol="SPY", quantity=4)],
        orders,
        [],
        reports,
        [],
    )

    assert clean.passed
    assert not dirty.passed
    reasons = {probe.name: probe.reason for probe in dirty.probes if not probe.passed}
    assert reasons["cash"] == "cash_mismatch"
    assert reasons["positions"] == "position_mismatch"
    assert reasons["open_orders"] == "open_order_mismatch"
    assert reasons["execution_reports"] == "execution_report_mismatch"


def test_failure_injection_report_requires_expected_failures_and_messages():
    report = evaluate_failure_injection(
        (
            FailureInjectionScenario("rate_limit", lambda: (_ for _ in ()).throw(RuntimeError("429 rate limit")), RuntimeError, "rate limit"),
            FailureInjectionScenario("unexpected_success", lambda: "ok", RuntimeError),
            FailureInjectionScenario("wrong_message", lambda: (_ for _ in ()).throw(ValueError("bad payload")), ValueError, "timeout"),
        )
    )

    reasons = {probe.name: probe.reason for probe in report.probes}

    assert not report.passed
    assert reasons["rate_limit"] == "passed"
    assert reasons["unexpected_success"] == "expected_failure_did_not_occur"
    assert reasons["wrong_message"] == "unexpected_exception_message"
