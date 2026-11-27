from datetime import datetime, time, timedelta, timezone
import json

from src.app import TradingApplication
from src.config import MarketDataConfig, RuntimeConfig, StrategyConfig
from src.operations import (
    AutonomousPaperSessionOptions,
    PaperSessionScheduleReport,
    PaperSessionScheduleWindow,
    PaperCleanupReport,
    PaperTradingDaemonOptions,
    ScheduledPaperSessionRecord,
    build_websocket_rest_parity_report,
    clear_paper_daemon_stop,
    load_paper_daemon_state,
    request_paper_daemon_stop,
    run_paper_trading_daemon,
)


def _sample_app() -> TradingApplication:
    return TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )


class IncrementingClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


def _clean_schedule_report(**kwargs) -> PaperSessionScheduleReport:
    now = kwargs["now"]
    output = kwargs["schedule_output_path"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"passed": True}, indent=2), encoding="utf-8")
    return PaperSessionScheduleReport(
        windows=(PaperSessionScheduleWindow("market_open", time(8, 30), time(10, 0), submit_orders_allowed=True),),
        records=(
            ScheduledPaperSessionRecord(
                "market_open",
                now,
                {
                    "ready_for_submission": True,
                    "warnings": (),
                    "submitted": False,
                    "report_path": str(kwargs["artifact_root"] / "paper-session-report.json"),
                },
            ),
        ),
        checks=({"name": "active_window", "passed": True, "reason": "passed"},),
        active_window="market_open",
        artifact_path=str(output),
    )


def _schedule_report_with_result(result: dict, **kwargs) -> PaperSessionScheduleReport:
    now = kwargs["now"]
    output = kwargs["schedule_output_path"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"passed": True}, indent=2), encoding="utf-8")
    return PaperSessionScheduleReport(
        windows=(PaperSessionScheduleWindow("market_open", time(8, 30), time(10, 0), submit_orders_allowed=True),),
        records=(ScheduledPaperSessionRecord("market_open", now, result),),
        checks=({"name": "active_window", "passed": True, "reason": "passed"},),
        active_window="market_open",
        artifact_path=str(output),
    )


def test_paper_daemon_runs_bounded_iteration_and_writes_state(tmp_path):
    calls = []

    def runner(app, options, **kwargs):
        calls.append((options, kwargs))
        return _clean_schedule_report(**kwargs)

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            max_iterations=1,
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "paper-daemon-state.json"),
            heartbeat_path=str(tmp_path / "paper-daemon-heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "paper-daemon-schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
            submit_orders=False,
        ),
        session_runner=runner,
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    assert report.passed
    assert report.state.status == "completed"
    assert report.state.iteration == 1
    assert len(calls) == 1
    assert calls[0][0].submit_orders is False
    assert (tmp_path / "paper-daemon-state.json").exists()
    assert (tmp_path / "paper-daemon-heartbeat.json").exists()
    assert (tmp_path / "paper-daemon-report.json").exists()
    loaded = load_paper_daemon_state(tmp_path / "paper-daemon-state.json")
    assert loaded["status"] == "completed"
    assert loaded["iteration"] == 1
    report_payload = json.loads((tmp_path / "paper-daemon-report.json").read_text(encoding="utf-8"))
    assert report_payload["iterations"][0]["artifact_paths"]


def test_paper_daemon_kill_switch_blocks_before_session(tmp_path):
    kill_switch = tmp_path / "paper-daemon.kill"
    request_paper_daemon_stop(kill_switch, now=datetime(2026, 1, 5, tzinfo=timezone.utc))
    calls = []

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            kill_switch_path=str(kill_switch),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
        ),
        session_runner=lambda *args, **kwargs: calls.append(kwargs),
        clock=IncrementingClock(),
    )

    assert report.stopped_by_kill_switch
    assert report.state.last_reason == "kill_switch_present_before_start"
    assert calls == []


def test_paper_daemon_stop_and_clear_helpers(tmp_path):
    kill_switch = tmp_path / "paper-daemon.kill"

    output = request_paper_daemon_stop(kill_switch, reason="maintenance_window", now=datetime(2026, 1, 5, tzinfo=timezone.utc))

    assert output == kill_switch
    payload = json.loads(kill_switch.read_text(encoding="utf-8"))
    assert payload["reason"] == "maintenance_window"
    assert clear_paper_daemon_stop(kill_switch) is True
    assert clear_paper_daemon_stop(kill_switch) is False


def test_paper_daemon_detects_kill_switch_after_iteration(tmp_path):
    kill_switch = tmp_path / "paper-daemon.kill"

    def runner(app, options, **kwargs):
        request_paper_daemon_stop(kill_switch, now=kwargs["now"])
        return _clean_schedule_report(**kwargs)

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            kill_switch_path=str(kill_switch),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
            submit_orders=True,
        ),
        session_runner=runner,
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    assert report.stopped_by_kill_switch
    assert report.state.iteration == 1
    assert report.state.last_reason == "kill_switch_detected_after_iteration"


def test_paper_daemon_single_instance_lock_blocks_duplicate_run(tmp_path):
    lock_path = tmp_path / "paper-daemon.lock"
    lock_path.write_text(
        json.dumps(
            {
                "token": "other",
                "acquired_at": datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    calls = []

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(lock_path),
            lock_stale_after_seconds=600,
            report_path=str(tmp_path / "paper-daemon-report.json"),
        ),
        session_runner=lambda *args, **kwargs: calls.append(kwargs),
        clock=IncrementingClock(),
    )

    assert report.state.status == "lock_active"
    assert report.state.last_reason == "paper_daemon_lock_active"
    assert calls == []
    assert lock_path.exists()


def test_paper_daemon_replaces_stale_single_instance_lock(tmp_path):
    lock_path = tmp_path / "paper-daemon.lock"
    lock_path.write_text(
        json.dumps(
            {
                "token": "stale",
                "acquired_at": datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            max_iterations=1,
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(lock_path),
            lock_stale_after_seconds=60,
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
        ),
        session_runner=lambda app, options, **kwargs: _clean_schedule_report(**kwargs),
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    assert report.passed
    assert report.state.status == "completed"
    assert not lock_path.exists()


def test_paper_daemon_runs_preview_cleanup_each_iteration(tmp_path):
    cleanup_calls = []

    def cleanup_runner(app, options):
        cleanup_calls.append(options)
        return PaperCleanupReport(
            submit_requested=options.submit_orders,
            attempted=False,
            positions_seen=({"symbol": "SPY", "quantity": 1.0},),
            planned_orders=({"symbol": "SPY", "side": "SELL", "quantity": 1.0},),
            reason="preview_only",
            artifact_path=options.artifact_path,
        )

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            max_iterations=1,
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
            cleanup_each_iteration=True,
            cleanup_submit_orders=False,
            cleanup_output_path=str(tmp_path / "cleanup.json"),
            submit_orders=True,
        ),
        session_runner=lambda app, options, **kwargs: _clean_schedule_report(**kwargs),
        cleanup_runner=cleanup_runner,
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    assert report.passed
    assert len(cleanup_calls) == 1
    assert cleanup_calls[0].submit_orders is False
    iteration = report.iterations[0]
    assert iteration.cleanup_reason == "preview_only"
    assert iteration.cleanup_planned_orders == 1
    assert iteration.cleanup_artifact_path.endswith("cleanup-0001.json")


def test_paper_daemon_monitor_flags_stale_open_orders(tmp_path):
    old_created_at = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc).isoformat()
    result_payload = {
        "ready_for_submission": True,
        "warnings": (),
        "submitted": True,
        "submitted_orders": (
            {
                "id": "order-1",
                "symbol": "SPY",
                "side": "BUY",
                "quantity": 1.0,
                "status": "NEW",
                "created_at": old_created_at,
            },
        ),
    }

    def cleanup_runner(app, options):
        return PaperCleanupReport(
            submit_requested=options.submit_orders,
            attempted=False,
            positions_seen=(),
            planned_orders=(),
            reason="preview_only",
            artifact_path=options.artifact_path,
        )

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            max_iterations=1,
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
            monitor_each_iteration=True,
            monitor_output_path=str(tmp_path / "monitor.json"),
            cleanup_output_path=str(tmp_path / "cleanup.json"),
            monitor_max_open_order_age_minutes=15,
        ),
        session_runner=lambda app, options, **kwargs: _schedule_report_with_result(result_payload, **kwargs),
        cleanup_runner=cleanup_runner,
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    iteration = report.iterations[0]
    assert not report.passed
    assert not iteration.passed
    assert iteration.monitor_passed is False
    assert iteration.monitor_reason == "stale_open_paper_orders"
    assert iteration.monitor_stale_open_orders == 1
    assert iteration.monitor_artifact_path.endswith("monitor-0001.json")
    assert iteration.monitor_artifact_path in iteration.artifact_paths


def test_paper_daemon_monitor_flags_position_quantity_drift(tmp_path):
    created_at = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc).isoformat()
    result_payload = {
        "ready_for_submission": True,
        "warnings": (),
        "submitted": True,
        "submitted_orders": (
            {
                "id": "order-1",
                "symbol": "SPY",
                "side": "BUY",
                "quantity": 2.0,
                "status": "FILLED",
                "created_at": created_at,
            },
        ),
    }

    def cleanup_runner(app, options):
        return PaperCleanupReport(
            submit_requested=options.submit_orders,
            attempted=False,
            positions_seen=({"symbol": "SPY", "quantity": 1.0, "market_value": 100.0},),
            planned_orders=({"symbol": "SPY", "side": "SELL", "quantity": 1.0},),
            reason="preview_only",
            artifact_path=options.artifact_path,
        )

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            max_iterations=1,
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
            monitor_each_iteration=True,
            monitor_output_path=str(tmp_path / "monitor.json"),
            cleanup_output_path=str(tmp_path / "cleanup.json"),
        ),
        session_runner=lambda app, options, **kwargs: _schedule_report_with_result(result_payload, **kwargs),
        cleanup_runner=cleanup_runner,
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    iteration = report.iterations[0]
    assert not report.passed
    assert iteration.monitor_reason == "paper_position_quantity_mismatch"
    assert iteration.monitor_position_mismatches == 1
    assert iteration.monitor_observed_notional == 100.0


def test_paper_daemon_monitor_hydrates_child_session_report_for_filled_orders(tmp_path):
    session_report = tmp_path / "child-session-report.json"
    session_report.write_text(
        json.dumps(
            {
                "submitted_orders": [
                    {
                        "id": "order-1",
                        "symbol": "SPY",
                        "side": "BUY",
                        "quantity": 1.0,
                        "status": "FILLED",
                        "created_at": "2026-01-05T15:00:00+00:00",
                    }
                ],
                "submission": {"notional_budget": {"max_notional": 250.0}},
            }
        ),
        encoding="utf-8",
    )
    result_payload = {
        "ready_for_submission": True,
        "warnings": (),
        "submitted": True,
        "report_path": str(session_report),
        "planned_orders": (
            {
                "id": "order-1",
                "symbol": "SPY",
                "side": "BUY",
                "quantity": 1.0,
                "status": "PENDING",
            },
        ),
    }

    def cleanup_runner(app, options):
        return PaperCleanupReport(
            submit_requested=options.submit_orders,
            attempted=False,
            positions_seen=({"symbol": "SPY", "quantity": 1.0, "market_value": 100.0},),
            planned_orders=({"symbol": "SPY", "side": "SELL", "quantity": 1.0},),
            reason="preview_only",
            artifact_path=options.artifact_path,
        )

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            max_iterations=1,
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
            monitor_each_iteration=True,
            monitor_output_path=str(tmp_path / "monitor.json"),
            cleanup_output_path=str(tmp_path / "cleanup.json"),
        ),
        session_runner=lambda app, options, **kwargs: _schedule_report_with_result(result_payload, **kwargs),
        cleanup_runner=cleanup_runner,
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    iteration = report.iterations[0]
    assert report.passed
    assert iteration.monitor_passed is True
    assert iteration.monitor_reason == "passed"
    assert iteration.monitor_position_mismatches == 0


def test_paper_daemon_attaches_data_parity_evidence_each_iteration(tmp_path):
    def parity_runner(app, daemon_options, *, schedule_report, now):
        return build_websocket_rest_parity_report(
            ({"symbol": "SPY", "timestamp": now.isoformat(), "close": 100.0},),
            ({"symbol": "SPY", "timestamp": now.isoformat(), "close": 100.0},),
            max_close_drift_bps=daemon_options.data_parity_max_close_drift_bps,
        )

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            max_iterations=1,
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
            data_parity_each_iteration=True,
            data_parity_output_path=str(tmp_path / "data-parity.json"),
        ),
        session_runner=lambda app, options, **kwargs: _clean_schedule_report(**kwargs),
        parity_runner=parity_runner,
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    iteration = report.iterations[0]
    assert report.passed
    assert iteration.data_parity_passed is True
    assert iteration.data_parity_reason == "websocket_rest_parity_passed"
    assert iteration.data_parity_checks == 1
    assert iteration.data_parity_failed_checks == 0
    assert iteration.data_parity_artifact_path.endswith("data-parity-0001.json")
    assert iteration.data_parity_artifact_path in iteration.artifact_paths


def test_paper_daemon_fails_iteration_on_data_parity_drift(tmp_path):
    def parity_runner(app, daemon_options, *, schedule_report, now):
        return build_websocket_rest_parity_report(
            ({"symbol": "SPY", "timestamp": now.isoformat(), "close": 100.0},),
            ({"symbol": "SPY", "timestamp": now.isoformat(), "close": 101.0},),
            max_close_drift_bps=daemon_options.data_parity_max_close_drift_bps,
        )

    report = run_paper_trading_daemon(
        _sample_app(),
        AutonomousPaperSessionOptions(submit_orders=True),
        PaperTradingDaemonOptions(
            interval_seconds=0,
            max_iterations=1,
            kill_switch_path=str(tmp_path / "paper-daemon.kill"),
            state_path=str(tmp_path / "state.json"),
            heartbeat_path=str(tmp_path / "heartbeat.json"),
            lock_path=str(tmp_path / "paper-daemon.lock"),
            artifact_root=str(tmp_path / "daemon-runs"),
            schedule_output_path=str(tmp_path / "schedule.json"),
            report_path=str(tmp_path / "paper-daemon-report.json"),
            data_parity_each_iteration=True,
            data_parity_output_path=str(tmp_path / "data-parity.json"),
            data_parity_max_close_drift_bps=5.0,
        ),
        session_runner=lambda app, options, **kwargs: _clean_schedule_report(**kwargs),
        parity_runner=parity_runner,
        sleep_fn=lambda seconds: None,
        clock=IncrementingClock(),
    )

    iteration = report.iterations[0]
    assert not report.passed
    assert not iteration.passed
    assert iteration.data_parity_passed is False
    assert iteration.data_parity_reason == "close_drift_above_threshold"
    assert iteration.data_parity_checks == 1
    assert iteration.data_parity_failed_checks == 1
