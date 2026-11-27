from datetime import datetime, timedelta, timezone
import argparse
import json

from main import run_paper_command_center_app
from src.operations import build_paper_command_center_report, write_paper_command_center_report


def test_paper_command_center_reports_missing_artifacts(tmp_path):
    report = build_paper_command_center_report(
        state_path=tmp_path / "missing-state.json",
        kill_switch_path=tmp_path / "missing.kill",
        daemon_report_path=tmp_path / "missing-daemon.json",
        monitor_path=tmp_path / "missing-monitor.json",
        pnl_path=tmp_path / "missing-pnl.json",
        drawdown_path=tmp_path / "missing-drawdown.json",
        fills_path=tmp_path / "missing-fills.jsonl",
        now=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
    )

    assert not report.passed
    assert report.daemon_status == "missing"
    assert report.heartbeat_state == "missing"
    assert report.monitor_status == "missing"
    assert "daemon_missing" in report.warnings
    assert "daemon_state_missing" in report.warnings
    assert report.recommended_action == "start_or_recover_paper_daemon"


def test_paper_command_center_extracts_daemon_risk_and_artifacts(tmp_path):
    now = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
    state_path = tmp_path / "state.json"
    daemon_path = tmp_path / "daemon.json"
    monitor_path = tmp_path / "monitor.json"
    pnl_path = tmp_path / "pnl.json"
    drawdown_path = tmp_path / "drawdown.json"
    fills_path = tmp_path / "fills.jsonl"
    state_path.write_text(
        json.dumps(
            {
                "status": "running",
                "iteration": 7,
                "last_heartbeat_at": (now - timedelta(seconds=20)).isoformat(),
                "next_run_at": (now + timedelta(minutes=5)).isoformat(),
                "last_reason": "passed",
                "last_active_window": "intraday",
            }
        ),
        encoding="utf-8",
    )
    daemon_path.write_text(
        json.dumps(
            {
                "artifact_path": str(daemon_path),
                "iterations": [
                    {
                        "artifact_paths": ["runs/session.json", "reports/parity.json"],
                        "data_parity_passed": False,
                        "data_parity_reason": "close_drift_above_threshold",
                        "data_parity_failed_checks": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monitor_path.write_text(
        json.dumps(
            {
                "passed": False,
                "reason": "stale_open_paper_orders",
                "observed_positions": {"SPY": 1, "QQQ": 0},
                "observed_notional": 125.5,
                "open_orders": {
                    "orders": [
                        {"symbol": "SPY", "stale": True},
                        {"symbol": "QQQ", "stale": False},
                    ]
                },
                "artifact_path": str(monitor_path),
            }
        ),
        encoding="utf-8",
    )
    pnl_path.write_text(
        json.dumps({"total_unrealized_pnl": -4.5, "total_market_value": 125.5, "artifact_path": str(pnl_path)}),
        encoding="utf-8",
    )
    drawdown_path.write_text(
        json.dumps({"drawdown_pct": 0.012, "mark_to_market_equity": 99_500.0, "artifact_path": str(drawdown_path)}),
        encoding="utf-8",
    )
    fills_path.write_text(json.dumps({"symbol": "SPY", "side": "BUY", "quantity": 1, "price": 100}), encoding="utf-8")

    report = build_paper_command_center_report(
        provider="alpaca",
        symbol="spy",
        strategy="tuffSystem",
        execution_mode="paper",
        paper_profile="micro-notional",
        state_path=state_path,
        kill_switch_path=tmp_path / "clear.kill",
        daemon_report_path=daemon_path,
        monitor_path=monitor_path,
        pnl_path=pnl_path,
        drawdown_path=drawdown_path,
        fills_path=fills_path,
        now=now,
    )

    assert not report.passed
    assert report.daemon_status == "running"
    assert report.heartbeat_state == "fresh"
    assert report.symbol == "SPY"
    assert report.monitor_status == "failed"
    assert report.observed_positions == 1
    assert report.open_orders == 2
    assert report.stale_open_orders == 1
    assert report.data_parity_status == "failed"
    assert report.data_parity_failed_checks == 2
    assert report.latest_fill == "SPY BUY 1 @ 100"
    assert "data_parity_failed" in report.warnings
    assert "runs/session.json" in report.last_artifacts
    assert report.recommended_action == "review_paper_risk_artifacts_before_next_submit"
    assert "Data parity: failed" in "\n".join(report.summary_lines())


def test_write_and_cli_paper_command_center_report(tmp_path, capsys):
    now = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
    state_path = tmp_path / "state.json"
    output_path = tmp_path / "command-center.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "iteration": 1,
                "last_heartbeat_at": now.isoformat(),
                "last_reason": "max_iterations_completed",
            }
        ),
        encoding="utf-8",
    )
    report = build_paper_command_center_report(
        state_path=state_path,
        daemon_report_path=tmp_path / "missing-report.json",
        monitor_path=tmp_path / "missing-monitor.json",
        pnl_path=tmp_path / "missing-pnl.json",
        drawdown_path=tmp_path / "missing-drawdown.json",
        fills_path=tmp_path / "missing-fills.jsonl",
        now=now,
    )

    written = write_paper_command_center_report(report, output_path)

    assert written == str(output_path)
    assert json.loads(output_path.read_text(encoding="utf-8"))["daemon"]["status"] == "completed"

    cli_output = tmp_path / "command-center-cli.json"
    args = argparse.Namespace(
        provider="sample",
        symbol="SPY",
        strategy="buyHold",
        execution_mode="dry-run",
        paper_profile=None,
        paper_daemon_profile=None,
        paper_daemon_state_output=str(state_path),
        paper_daemon_kill_switch=str(tmp_path / "missing.kill"),
        paper_daemon_report_input=None,
        paper_daemon_report_output=str(tmp_path / "missing-report.json"),
        paper_monitor_output=str(tmp_path / "missing-monitor.json"),
        paper_pnl_attribution_output=None,
        paper_drawdown_output=None,
        store_dir=str(tmp_path),
        paper_command_center_stale_seconds=900.0,
        paper_command_center_output=str(cli_output),
    )

    run_paper_command_center_app(args)

    captured = capsys.readouterr()
    assert "Daemon: completed" in captured.out
    assert "Paper command center written" in captured.out
    assert cli_output.exists()
