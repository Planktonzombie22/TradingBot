from datetime import datetime, time, timezone

from src.execution import BrokerAccountSnapshot, BrokerPositionSnapshot, ExecutionReport
from src.models import Order
from src.operations import (
    AutonomousPaperSessionOptions,
    PaperSessionScheduleWindow,
    ScheduledPaperSessionRecord,
    default_paper_session_schedule_windows,
    evaluate_paper_session_schedule,
    run_scheduled_paper_session,
)
from src.app import TradingApplication
from src.config import MarketDataConfig, RuntimeConfig, StrategyConfig
from src.validation import (
    evaluate_broker_statement_ingestion,
    evaluate_real_alpaca_fill_polling,
    ingest_broker_statement,
)


def test_paper_session_schedule_report_validates_required_windows_and_evidence():
    windows = (
        PaperSessionScheduleWindow("market_open", time(8, 30), time(10, 0)),
        PaperSessionScheduleWindow("end_of_day", time(15, 0), time(17, 0), submit_orders_allowed=False),
    )
    clean = evaluate_paper_session_schedule(
        (
            ScheduledPaperSessionRecord(
                "market_open",
                datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc),
                {"ready_for_submission": True, "warnings": (), "submitted": False},
            ),
            ScheduledPaperSessionRecord(
                "end_of_day",
                datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc),
                {"ready_for_submission": True, "warnings": (), "submitted": False},
            ),
        ),
        windows,
    )
    dirty = evaluate_paper_session_schedule(
        (
            ScheduledPaperSessionRecord(
                "end_of_day",
                datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc),
                {"ready_for_submission": True, "warnings": (), "submitted": True},
            ),
        ),
        windows,
    )

    assert clean.passed
    assert clean.to_evidence().status == "passed"
    assert not dirty.passed
    reasons = {check["name"]: check["reason"] for check in dirty.checks if not check["passed"]}
    assert reasons["market_open"] == "missing_required_window_record"
    assert reasons["end_of_day"] == "orders_submitted_in_blocked_window"


def test_default_paper_session_schedule_allows_regular_submit_windows_only():
    windows = {window.name: window for window in default_paper_session_schedule_windows()}

    assert windows["market_open"].submit_orders_allowed
    assert windows["intraday"].submit_orders_allowed
    assert windows["market_close"].submit_orders_allowed
    assert not windows["pre_market"].submit_orders_allowed
    assert not windows["end_of_day"].submit_orders_allowed


def test_scheduled_paper_session_runs_active_window_and_writes_report(tmp_path):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )
    output = tmp_path / "paper-session-schedule.json"
    windows = (PaperSessionScheduleWindow("market_open", time(8, 30), time(10, 0)),)

    report = run_scheduled_paper_session(
        app,
        AutonomousPaperSessionOptions(artifact_root=str(tmp_path / "unused")),
        windows=windows,
        now=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        artifact_root=tmp_path / "scheduled-runs",
        schedule_output_path=output,
    )

    assert report.passed
    assert report.active_window == "market_open"
    assert report.artifact_path == str(output)
    assert report.records[0].window_name == "market_open"
    assert report.records[0].passed
    assert output.exists()


def test_scheduled_paper_session_blocks_without_active_window(tmp_path):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )

    report = run_scheduled_paper_session(
        app,
        AutonomousPaperSessionOptions(),
        now=datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc),
        schedule_output_path=tmp_path / "schedule.json",
    )

    assert not report.passed
    assert report.active_window is None
    assert report.records == ()
    assert report.checks[0]["reason"] == "no_active_paper_session_window"


def test_scheduled_paper_session_suppresses_submit_in_no_submit_window(tmp_path):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )
    windows = (PaperSessionScheduleWindow("audit_only", time(8, 30), time(10, 0), submit_orders_allowed=False),)

    report = run_scheduled_paper_session(
        app,
        AutonomousPaperSessionOptions(submit_orders=True),
        windows=windows,
        now=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        artifact_root=tmp_path / "scheduled-runs",
    )

    assert report.passed
    assert report.records[0].submitted is False
    result = report.records[0].result.to_dict()
    assert result["submission_guard"]["submit_requested"] is False


def test_broker_statement_ingestion_parses_and_compares_to_local_state():
    payload = {
        "cash": "1000",
        "equity": "1500",
        "positions": [{"symbol": "SPY", "qty": "3"}],
        "fills": [{"symbol": "SPY", "qty": "1"}],
    }
    local_account = BrokerAccountSnapshot(cash=1000, buying_power=2000, equity=1500)
    local_positions = [BrokerPositionSnapshot(symbol="SPY", quantity=3)]

    statement = ingest_broker_statement(payload)
    clean = evaluate_broker_statement_ingestion(payload, local_account, local_positions)
    dirty = evaluate_broker_statement_ingestion(
        {**payload, "equity": "1400", "positions": {"SPY": 2}},
        local_account,
        local_positions,
    )

    assert statement.positions == {"SPY": 3.0}
    assert clean.passed
    assert not dirty.passed
    reasons = {probe.name: probe.reason for probe in dirty.probes if not probe.passed}
    assert reasons["statement_equity"] == "statement_equity_mismatch"
    assert reasons["statement_positions"] == "statement_position_mismatch"


def test_real_alpaca_fill_polling_report_uses_injected_polling_boundary():
    order = Order(id="local-1", client_order_id="client-1", symbol="SPY", side="BUY", quantity=1)
    clean = evaluate_real_alpaca_fill_polling(
        (order,),
        lambda: (
            ExecutionReport(
                order_id="local-1",
                status="FILLED",
                broker_order_id="broker-1",
                filled_quantity=1,
                average_fill_price=100,
            ),
        ),
    )
    dirty = evaluate_real_alpaca_fill_polling(
        (order,),
        lambda: ({"order_id": "other", "status": "unknown"},),
    )

    assert clean.passed
    assert not dirty.passed
    reasons = {probe.name: probe.reason for probe in dirty.probes if not probe.passed}
    assert reasons["expected_orders_reported"] == "missing_polled_fills"
    assert reasons["real_fill_status_present"] == "missing_known_fill_status"
