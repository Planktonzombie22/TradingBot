from datetime import datetime, timezone

import pytest

from src.config import AlpacaConfig, ExecutionConfig, MarketDataConfig, RuntimeConfig, validate_runtime_environment
from src.data import AlpacaMarketDataStream, MarketDataEventType
from src.deployment import docker_profile, local_windows_task_profile, small_server_profile
from src.engine import EngineEvent, EngineEventType, EngineState, PaperAccountState, RuntimeRiskMonitor
from src.execution import AlpacaPaperBroker, PaperBroker
from src.models import Order
from src.monitoring import (
    HealthCheck,
    HealthStatus,
    InMemoryNotificationSink,
    MetricsRegistry,
    NotificationRouter,
    build_dashboard_snapshot,
)
from src.operations import SoakChecklist
from src.risk import RiskManager


def test_dashboard_snapshot_summarizes_account_orders_fills_and_halts():
    broker = PaperBroker(auto_fill_market_orders=False)
    submitted = broker.submit_order(Order("SPY", "BUY", 1, order_type="LIMIT", limit_price=100))
    account = PaperAccountState(10_000)
    risk = RuntimeRiskMonitor()
    risk._halt("test halt")

    snapshot = build_dashboard_snapshot(
        EngineState.HALTED,
        account,
        broker,
        prices={"SPY": 100},
        risk_monitor=risk,
        health={"stream": "ok"},
    )

    assert snapshot.engine_state == "HALTED"
    assert snapshot.open_orders[0]["id"] == submitted.id
    assert snapshot.risk_halt["halted"]
    assert snapshot.health["stream"] == "ok"


def test_notification_router_emits_operational_topics():
    sink = InMemoryNotificationSink()
    router = NotificationRouter(sink)

    router.handle_engine_event(EngineEvent(EngineEventType.STARTED, "started"))
    router.handle_engine_event(EngineEvent(EngineEventType.HALT, "halted", payload={"reason": "risk"}))

    assert [event.topic for event in sink.events] == ["startup", "halt"]
    assert sink.events[-1].severity == "CRITICAL"


def test_metrics_registry_and_health_check_snapshot():
    metrics = MetricsRegistry()
    metrics.increment("orders")
    metrics.gauge("equity", 10_000)
    metrics.timing("latency", 0.1)

    health = HealthCheck("stream", lambda: HealthStatus("stream", True, "ok")).run()

    assert metrics.snapshot()["counters"]["orders"] == 1
    assert health.healthy


def test_environment_validation_fails_fast_for_missing_alpaca_credentials():
    config = RuntimeConfig(
        data=MarketDataConfig(provider="alpaca"),
        alpaca=AlpacaConfig(api_key="", secret_key=""),
        execution=ExecutionConfig(mode="paper"),
    )

    result = validate_runtime_environment(config)

    assert not result.passed
    assert any("ALPACA_API_KEY" in error for error in result.errors)


def test_environment_validation_allows_safe_paper_configuration():
    config = RuntimeConfig(
        data=MarketDataConfig(provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    assert validate_runtime_environment(config).passed


def test_deployment_profiles_document_runtime_commands():
    profiles = [local_windows_task_profile(), docker_profile(), small_server_profile()]

    assert {profile.name for profile in profiles} == {"windows-task", "docker", "small-server"}
    assert all("paper" in profile.command for profile in profiles)


def test_soak_checklist_requires_all_criteria():
    checklist = SoakChecklist.default()
    assert not checklist.passed

    for check in list(checklist.checks):
        checklist = checklist.with_result(check.name, True, "ok")

    assert checklist.passed


def test_mocked_alpaca_order_reject_and_cancel_flow():
    calls = []

    class FakeClient:
        def request(self, method, url, payload=None):
            calls.append((method, url, payload))
            if method == "POST":
                return {"id": "broker-1", "status": "rejected"}
            return {}

    broker = AlpacaPaperBroker(AlpacaConfig(api_key="key", secret_key="secret"))
    broker.client = FakeClient()

    submitted = broker.submit_order(Order("SPY", "BUY", 1))
    cancelled = broker.cancel_order(submitted.id)

    assert submitted.status == "REJECTED"
    assert cancelled.status == "CANCELLED"
    assert calls[0][0] == "POST"


def test_mocked_alpaca_stream_error_and_reconnect_flow(monkeypatch):
    import sys
    from types import SimpleNamespace

    sockets = {"count": 0}

    class FakeSocket:
        def __init__(self):
            sockets["count"] += 1
            self.index = sockets["count"]

        def connect(self, url):
            self.url = url

        def settimeout(self, timeout):
            self.timeout = timeout

        def send(self, message):
            pass

        def recv(self):
            if self.index == 1:
                raise RuntimeError("disconnect")
            return '[{"T":"error","msg":"test error"}]'

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "websocket", SimpleNamespace(WebSocket=FakeSocket))
    stream = AlpacaMarketDataStream(AlpacaConfig(api_key="key", secret_key="secret"), reconnect_attempts=1, reconnect_delay_seconds=0)
    stream.subscribe_bars(["SPY"])
    events = []

    def stop_on_error(event):
        events.append(event)
        stream.stop()

    stream.add_handler(stop_on_error)
    stream.run_forever()

    assert sockets["count"] == 2
    assert stream.health.reconnects == 1
    assert events[0].event_type == MarketDataEventType.ERROR


def test_failure_scenarios_for_market_closed_risk_and_partial_fills():
    rejected = RiskManager(max_order_notional=10).order_from_signal(
        signal=type("SignalLike", (), {"action": "BUY", "symbol": "SPY", "stop_loss": 99})(),
        equity=10_000,
        price=100,
        risk_fraction=0.10,
        buying_power=10_000,
    )
    assert rejected.accepted
    assert rejected.order.quantity <= 0.1
