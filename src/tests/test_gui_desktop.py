from pathlib import Path
from datetime import datetime, timedelta, timezone
import json

from src.gui import (
    GuiCommandConfig,
    GuiDaemonStatus,
    GuiDashboardSummary,
    GuiResearchSummary,
    GuiSoakReadinessSummary,
    apply_gui_profile_preset,
    build_cli_command,
    build_gui_autonomous_readiness_report,
    build_gui_daemon_status,
    build_gui_dashboard_summary,
    build_gui_next_capture_decision,
    build_gui_next_capture_command,
    build_gui_operator_snapshot,
    build_gui_research_summary,
    build_gui_soak_readiness_summary,
    gui_profile_presets,
    write_gui_autonomous_readiness_report,
)


def test_gui_builds_backtest_command_with_output_path():
    command = build_cli_command(
        GuiCommandConfig(
            mode="backtest",
            provider="sample",
            symbol="SPY",
            strategy="buyHold",
            output_path="reports/gui-backtest.json",
        ),
        python_executable="python",
        main_path="main.py",
    )

    assert command == [
        "python",
        "main.py",
        "backtest",
        "--provider",
        "sample",
        "--symbol",
        "SPY",
        "--strategy",
        "buyHold",
        "--execution-mode",
        "dry-run",
        "--store-dir",
        "runs/gui",
        "--output",
        "reports/gui-backtest.json",
    ]


def test_gui_builds_paper_daemon_command_with_submit_and_bounds():
    command = build_cli_command(
        GuiCommandConfig(
            mode="paper-daemon",
            provider="alpaca",
            symbol="QQQ",
            strategy="tuffSystem",
            execution_mode="paper",
            paper_profile="micro-notional",
            submit_orders=True,
            daemon_interval_seconds=60,
            daemon_max_iterations=2,
        ),
        python_executable="python",
        main_path=Path("main.py"),
    )

    assert command[:10] == [
        "python",
        "main.py",
        "paper-daemon",
        "--provider",
        "alpaca",
        "--symbol",
        "QQQ",
        "--strategy",
        "tuffSystem",
        "--execution-mode",
    ]
    assert "--submit-orders" in command
    assert "--paper-daemon-state-output" in command
    assert "--paper-daemon-heartbeat-output" in command
    assert "--paper-daemon-kill-switch" in command
    assert "--paper-daemon-lock-path" in command
    assert "--paper-daemon-lock-stale-seconds" in command


def test_gui_daemon_stop_command_keeps_operator_controls_simple():
    command = build_cli_command(
        GuiCommandConfig(mode="paper-daemon-stop"),
        python_executable="python",
        main_path="main.py",
    )

    assert command == ["python", "main.py", "paper-daemon-stop"]


def test_gui_builds_validation_profile_command():
    command = build_cli_command(
        GuiCommandConfig(
            mode="validate-profile",
            provider="sample",
            symbol="SPY",
            strategy="buyHold",
            validation_profile="fast",
            validation_output_path="reports/gui-validation-fast.json",
        ),
        python_executable="python",
        main_path="main.py",
    )

    assert command[:3] == ["python", "main.py", "validate-profile"]
    assert command[-4:] == [
        "--validation-profile",
        "fast",
        "--validation-profile-output",
        "reports/gui-validation-fast.json",
    ]


def test_gui_profile_presets_apply_safe_defaults():
    names = {preset.name for preset in gui_profile_presets()}

    assert {"Sample dry-run", "Alpaca data-only", "Micro paper", "Full paper rehearsal"} <= names

    sample = apply_gui_profile_preset(GuiCommandConfig(mode="paper-daemon"), "Sample dry-run")
    micro = apply_gui_profile_preset(GuiCommandConfig(mode="paper-daemon"), "Micro paper")

    assert sample.provider == "sample"
    assert sample.execution_mode == "dry-run"
    assert not sample.submit_orders
    assert sample.daemon_max_iterations == 1
    assert micro.provider == "alpaca"
    assert micro.execution_mode == "paper"
    assert micro.paper_profile == "micro-notional"
    assert micro.submit_orders


def test_gui_unknown_profile_preset_fails_closed():
    try:
        apply_gui_profile_preset(GuiCommandConfig(mode="backtest"), "not-a-profile")
    except ValueError as exc:
        assert "Unknown GUI profile preset" in str(exc)
    else:
        raise AssertionError("unknown GUI preset should fail")


def test_gui_daemon_status_reports_missing_state(tmp_path):
    status = build_gui_daemon_status(
        state_path=tmp_path / "missing-state.json",
        kill_switch_path=tmp_path / "paper-daemon.kill",
        now=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )

    assert status.status == "missing"
    assert status.heartbeat_state == "missing"
    assert not status.kill_switch_active
    assert "Daemon: missing" in status.card_lines()


def test_gui_daemon_status_reports_fresh_and_stale_heartbeat(tmp_path):
    now = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
    state_path = tmp_path / "paper-daemon-state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "running",
                "iteration": 3,
                "last_heartbeat_at": (now - timedelta(seconds=30)).isoformat(),
                "next_run_at": (now + timedelta(seconds=270)).isoformat(),
                "last_reason": "passed",
                "last_active_window": "intraday",
            }
        ),
        encoding="utf-8",
    )

    fresh = build_gui_daemon_status(state_path=state_path, kill_switch_path=tmp_path / "kill", stale_after_seconds=60, now=now)
    stale = build_gui_daemon_status(state_path=state_path, kill_switch_path=tmp_path / "kill", stale_after_seconds=10, now=now)

    assert fresh.heartbeat_state == "fresh"
    assert fresh.iteration == 3
    assert fresh.last_active_window == "intraday"
    assert stale.heartbeat_state == "stale"


def test_gui_daemon_status_reports_kill_switch(tmp_path):
    kill_switch = tmp_path / "paper-daemon.kill"
    kill_switch.write_text("stop", encoding="utf-8")

    status = build_gui_daemon_status(
        state_path=tmp_path / "missing-state.json",
        kill_switch_path=kill_switch,
        now=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )

    assert status.kill_switch_active
    assert "Kill switch: active" in status.card_lines()


def test_gui_dashboard_summary_reports_missing_artifacts(tmp_path):
    summary = build_gui_dashboard_summary(
        monitor_path=tmp_path / "missing-monitor.json",
        pnl_path=tmp_path / "missing-pnl.json",
        drawdown_path=tmp_path / "missing-drawdown.json",
        fills_path=tmp_path / "missing-fills.jsonl",
    )

    assert summary.monitor_status == "missing"
    assert summary.observed_positions == 0
    assert summary.open_orders == 0
    assert set(summary.artifacts_missing) == {"monitor", "pnl", "drawdown", "fills"}


def test_gui_dashboard_summary_extracts_monitor_analytics_and_fills(tmp_path):
    monitor_path = tmp_path / "monitor.json"
    pnl_path = tmp_path / "pnl.json"
    drawdown_path = tmp_path / "drawdown.json"
    fills_path = tmp_path / "fills.jsonl"
    monitor_path.write_text(
        json.dumps(
            {
                "passed": False,
                "reason": "stale_open_order",
                "observed_positions": {"SPY": 1, "QQQ": 0, "IWM": -2},
                "observed_notional": 350.25,
                "open_orders": {
                    "orders": [
                        {"symbol": "SPY", "stale": True},
                        {"symbol": "QQQ", "stale": False},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    pnl_path.write_text(
        json.dumps({"total_unrealized_pnl": 12.5, "total_market_value": 350.25}),
        encoding="utf-8",
    )
    drawdown_path.write_text(
        json.dumps({"drawdown_pct": 0.034, "mark_to_market_equity": 99_250.0}),
        encoding="utf-8",
    )
    fills_path.write_text(
        "\n".join(
            [
                json.dumps({"symbol": "SPY", "side": "BUY", "quantity": 1, "price": 100}),
                json.dumps({"symbol": "IWM", "side": "SELL", "quantity": 2, "price": 175}),
            ]
        ),
        encoding="utf-8",
    )

    summary = build_gui_dashboard_summary(
        monitor_path=monitor_path,
        pnl_path=pnl_path,
        drawdown_path=drawdown_path,
        fills_path=fills_path,
    )

    assert summary.monitor_status == "failed"
    assert summary.monitor_reason == "stale_open_order"
    assert summary.observed_positions == 2
    assert summary.open_orders == 2
    assert summary.stale_open_orders == 1
    assert summary.total_unrealized_pnl == 12.5
    assert summary.drawdown_pct == 0.034
    assert summary.fills_seen == 2
    assert summary.latest_fill == "IWM SELL 2 @ 175"
    assert set(summary.artifacts_present) == {"monitor", "pnl", "drawdown", "fills"}


def test_gui_research_summary_reports_missing_artifacts(tmp_path):
    summary = build_gui_research_summary(
        bulk_path=tmp_path / "missing-bulk.json",
        benchmark_path=tmp_path / "missing-benchmark.json",
        promotion_path=tmp_path / "missing-promotion.json",
    )

    assert summary.strategy_rows == 0
    assert summary.top_strategy is None
    assert summary.benchmark_rows == 0
    assert set(summary.artifacts_missing) == {"bulk", "benchmark", "promotion"}


def test_gui_research_summary_extracts_top_strategy_and_promotions(tmp_path):
    bulk_path = tmp_path / "bulk.json"
    benchmark_path = tmp_path / "benchmark.json"
    promotion_path = tmp_path / "promotion.json"
    bulk_path.write_text(
        json.dumps(
            {
                "strategy_summary": [
                    {"strategy": "slow", "average_return": 0.01},
                    {"strategy": "fast", "average_return": 0.12},
                ]
            }
        ),
        encoding="utf-8",
    )
    benchmark_path.write_text(
        json.dumps(
            {
                "strategy_summary": [
                    {"strategy": "fast", "average_excess_return": 0.05},
                    {"strategy": "slow", "average_excess_return": -0.02},
                ]
            }
        ),
        encoding="utf-8",
    )
    promotion_path.write_text(
        json.dumps({"candidate_count": 3, "enabled_count": 1}),
        encoding="utf-8",
    )

    summary = build_gui_research_summary(
        bulk_path=bulk_path,
        benchmark_path=benchmark_path,
        promotion_path=promotion_path,
    )

    assert summary.strategy_rows == 2
    assert summary.top_strategy == "fast"
    assert summary.top_metric == "average_return=0.1200"
    assert summary.benchmark_rows == 2
    assert summary.benchmark_leaders == 1
    assert summary.promotion_candidates == 3
    assert summary.promotion_enabled == 1


def test_gui_soak_readiness_summary_reports_missing_artifact(tmp_path):
    summary = build_gui_soak_readiness_summary(
        rollup_path=tmp_path / "missing-rollup.json",
        capture_plan_path=tmp_path / "missing-capture-plan.json",
        use_latest_fallback=False,
    )

    assert summary.readiness_status == "missing"
    assert not summary.ready_for_autonomous_paper
    assert summary.artifacts_missing == ("soak_rollup", "window_capture_plan")
    assert "Autonomy: missing" in summary.card_lines()


def test_gui_soak_readiness_summary_extracts_blocked_rollup(tmp_path):
    rollup_path = tmp_path / "rollup.json"
    capture_plan_path = tmp_path / "capture-plan.json"
    rollup_path.write_text(
        json.dumps(
            {
                "passed": False,
                "checks": {
                    "monitor_passed": True,
                    "data_parity_passed": True,
                    "flatten_drill_passed": True,
                    "stewardship_passed": True,
                },
                "blockers": ["supervised_soak_passed"],
                "warnings": ["insufficient_active_window_coverage"],
                "recommended_action": "collect_more_clean_submitted_daemon_windows_before_escalation",
                "evidence": {
                    "clean_activations": 1,
                    "submitted_activations": 1,
                    "required_clean_activations": 3,
                    "active_windows": ["intraday"],
                    "required_active_windows": 2,
                    "observed_notional": 0.0,
                    "closed_symbols": ["SPY"],
                },
            }
        ),
        encoding="utf-8",
    )
    capture_plan_path.write_text(
        json.dumps(
            {
                "missing_windows": ["market_open", "market_close"],
                "targets": [
                    {
                        "name": "market_open",
                        "start_time": "08:30",
                        "end_time": "10:00",
                        "action": "capture_next",
                        "command": ["python", "main.py", "paper-daemon", "--submit-orders"],
                    },
                    {"name": "intraday", "action": "retain_evidence"},
                    {"name": "market_close", "action": "capture_next"},
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_gui_soak_readiness_summary(
        rollup_path=rollup_path,
        capture_plan_path=capture_plan_path,
        use_latest_fallback=False,
        now=datetime(2026, 1, 5, 8, 0),
        capture_market_session="PRE_MARKET",
    )

    assert summary.readiness_status == "blocked"
    assert summary.clean_activations == 1
    assert summary.required_clean_activations == 3
    assert summary.active_windows == ("intraday",)
    assert summary.blockers == ("supervised_soak_passed",)
    assert summary.flatten_status == "passed"
    assert summary.closed_symbols == ("SPY",)
    assert summary.next_capture_window == "market_open"
    assert summary.next_capture_range == "08:30-10:00 CT"
    assert summary.next_capture_state == "upcoming"
    assert summary.next_capture_market_session == "pre_market"
    assert summary.minutes_until_capture_start == 30.0
    assert summary.missing_capture_windows == ("market_open", "market_close")
    assert summary.next_capture_command == ("python", "main.py", "paper-daemon", "--submit-orders")
    assert any(line.startswith("Windows: 1/2") for line in summary.card_lines())
    assert any(line == "Capture: next=market_open missing=market_open, market_close" for line in summary.card_lines())
    assert any(line == "Capture window: 08:30-10:00 CT state=upcoming session=pre_market starts_in=30m" for line in summary.card_lines())


def test_gui_soak_readiness_summary_reports_ready_rollup(tmp_path):
    rollup_path = tmp_path / "rollup.json"
    capture_plan_path = tmp_path / "capture-plan.json"
    rollup_path.write_text(
        json.dumps(
            {
                "passed": True,
                "checks": {
                    "monitor_passed": True,
                    "data_parity_passed": True,
                    "flatten_drill_passed": True,
                    "stewardship_passed": True,
                },
                "blockers": [],
                "warnings": [],
                "recommended_action": "ready_to_continue_operator_managed_always_on_paper",
                "evidence": {
                    "clean_activations": 3,
                    "submitted_activations": 3,
                    "required_clean_activations": 3,
                    "active_windows": ["market_open", "intraday"],
                    "required_active_windows": 2,
                    "observed_notional": 0,
                    "closed_symbols": ["SPY"],
                },
            }
        ),
        encoding="utf-8",
    )
    capture_plan_path.write_text(json.dumps({"missing_windows": [], "targets": []}), encoding="utf-8")

    summary = build_gui_soak_readiness_summary(
        rollup_path=rollup_path,
        capture_plan_path=capture_plan_path,
        use_latest_fallback=False,
    )

    assert summary.readiness_status == "ready"
    assert summary.ready_for_autonomous_paper
    assert summary.blockers == ()
    assert summary.data_parity_status == "passed"
    assert summary.next_capture_state == "none"


def test_gui_soak_readiness_summary_reports_active_capture_window(tmp_path):
    rollup_path = tmp_path / "rollup.json"
    capture_plan_path = tmp_path / "capture-plan.json"
    rollup_path.write_text(
        json.dumps(
            {
                "passed": False,
                "checks": {"monitor_passed": True, "data_parity_passed": True},
                "blockers": ["supervised_soak_passed"],
                "evidence": {"clean_activations": 1, "required_clean_activations": 3, "active_windows": ["intraday"], "required_active_windows": 2},
            }
        ),
        encoding="utf-8",
    )
    capture_plan_path.write_text(
        json.dumps(
            {
                "missing_windows": ["market_open"],
                "targets": [
                    {
                        "name": "market_open",
                        "start_time": "08:30",
                        "end_time": "10:00",
                        "action": "capture_next",
                        "command": ["python", "main.py", "paper-daemon"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_gui_soak_readiness_summary(
        rollup_path=rollup_path,
        capture_plan_path=capture_plan_path,
        use_latest_fallback=False,
        now=datetime(2026, 1, 5, 9, 15),
        capture_market_session="REGULAR",
    )

    assert summary.next_capture_state == "active"
    assert summary.next_capture_market_session == "regular"
    assert summary.minutes_until_capture_start == 0.0
    assert summary.minutes_until_capture_end == 45.0
    assert any(line == "Capture window: 08:30-10:00 CT state=active session=regular ends_in=45m" for line in summary.card_lines())


def test_gui_soak_readiness_summary_blocks_capture_when_market_closed(tmp_path):
    rollup_path = tmp_path / "rollup.json"
    capture_plan_path = tmp_path / "capture-plan.json"
    rollup_path.write_text(
        json.dumps(
            {
                "passed": False,
                "checks": {"monitor_passed": True, "data_parity_passed": True},
                "blockers": ["supervised_soak_passed"],
                "evidence": {"clean_activations": 1, "required_clean_activations": 3, "active_windows": ["intraday"], "required_active_windows": 2},
            }
        ),
        encoding="utf-8",
    )
    capture_plan_path.write_text(
        json.dumps(
            {
                "missing_windows": ["market_open"],
                "targets": [
                    {
                        "name": "market_open",
                        "start_time": "08:30",
                        "end_time": "10:00",
                        "action": "capture_next",
                        "command": ["python", "main.py", "paper-daemon"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_gui_soak_readiness_summary(
        rollup_path=rollup_path,
        capture_plan_path=capture_plan_path,
        use_latest_fallback=False,
        now=datetime(2026, 1, 10, 9, 15),
        capture_market_session="CLOSED",
    )
    decision = build_gui_next_capture_decision(summary)

    assert summary.next_capture_state == "market_closed"
    assert summary.next_capture_market_session == "closed"
    assert summary.minutes_until_capture_start is None
    assert not decision.can_run
    assert decision.reason == "capture_window_not_active"
    assert decision.state == "market_closed"
    assert any(line == "Capture window: 08:30-10:00 CT state=market_closed session=closed" for line in summary.card_lines())


def test_gui_next_capture_command_extracts_first_pending_target(tmp_path):
    capture_plan_path = tmp_path / "capture-plan.json"
    capture_plan_path.write_text(
        json.dumps(
            {
                "targets": [
                    {"name": "intraday", "action": "retain_evidence", "command": ["ignore"]},
                    {"name": "market_close", "action": "capture_next", "command": ["python", "main.py", "paper-daemon"]},
                ]
            }
        ),
        encoding="utf-8",
    )

    command = build_gui_next_capture_command(
        capture_plan_path=capture_plan_path,
        use_latest_fallback=False,
    )

    assert command == ("python", "main.py", "paper-daemon")


def test_gui_next_capture_decision_blocks_until_window_active():
    summary = GuiSoakReadinessSummary(
        next_capture_window="market_open",
        next_capture_state="upcoming",
        next_capture_command=("python", "main.py", "paper-daemon", "--submit-orders"),
    )

    decision = build_gui_next_capture_decision(summary)

    assert not decision.can_run
    assert decision.reason == "capture_window_not_active"
    assert decision.submit_requested


def test_gui_next_capture_decision_runs_only_active_command():
    summary = GuiSoakReadinessSummary(
        next_capture_window="market_open",
        next_capture_state="active",
        next_capture_command=("python", "main.py", "paper-daemon", "--submit-orders"),
    )

    decision = build_gui_next_capture_decision(summary)

    assert decision.can_run
    assert decision.reason == "ready_to_run_next_capture"
    assert decision.window == "market_open"
    assert decision.submit_requested


def test_gui_next_capture_decision_blocks_missing_command():
    decision = build_gui_next_capture_decision(GuiSoakReadinessSummary())

    assert not decision.can_run
    assert decision.reason == "no_pending_capture_command"


def test_gui_operator_snapshot_prioritizes_kill_switch():
    snapshot = build_gui_operator_snapshot(
        daemon_status=GuiDaemonStatus(status="running", heartbeat_state="fresh", kill_switch_active=True),
        dashboard_summary=GuiDashboardSummary(monitor_status="passed", observed_positions=0),
        soak_summary=GuiSoakReadinessSummary(
            readiness_status="ready",
            clean_activations=3,
            required_clean_activations=3,
            next_capture_window="market_open",
            next_capture_state="active",
            next_capture_command=("python", "main.py", "paper-daemon"),
        ),
        research_summary=GuiResearchSummary(strategy_rows=10, promotion_candidates=2, promotion_enabled=1),
    )

    assert snapshot.status == "stopped"
    assert snapshot.reason == "kill_switch_active"
    assert snapshot.next_capture.can_run
    assert snapshot.to_dict()["daemon"]["kill_switch_active"]
    assert snapshot.card_lines()[0] == "Operator: stopped (kill_switch_active)"


def test_gui_operator_snapshot_marks_active_capture_ready():
    snapshot = build_gui_operator_snapshot(
        daemon_status=GuiDaemonStatus(status="running", heartbeat_state="fresh", kill_switch_active=False),
        dashboard_summary=GuiDashboardSummary(monitor_status="passed", observed_positions=0),
        soak_summary=GuiSoakReadinessSummary(
            readiness_status="blocked",
            clean_activations=1,
            required_clean_activations=3,
            next_capture_window="market_open",
            next_capture_state="active",
            next_capture_command=("python", "main.py", "paper-daemon"),
        ),
        research_summary=GuiResearchSummary(strategy_rows=10, promotion_candidates=2, promotion_enabled=1),
    )

    assert snapshot.status == "capture-ready"
    assert snapshot.reason == "next_capture_window_ready"
    assert snapshot.to_dict()["next_capture"]["can_run"]


def test_gui_autonomous_readiness_report_blocks_thin_soak_evidence():
    snapshot = build_gui_operator_snapshot(
        daemon_status=GuiDaemonStatus(status="running", heartbeat_state="fresh", kill_switch_active=False),
        dashboard_summary=GuiDashboardSummary(monitor_status="passed", observed_positions=0),
        soak_summary=GuiSoakReadinessSummary(
            readiness_status="blocked",
            clean_activations=1,
            submitted_activations=1,
            required_clean_activations=3,
            active_windows=("intraday",),
            required_active_windows=2,
            monitor_status="passed",
            data_parity_status="passed",
            flatten_status="passed",
            stewardship_status="passed",
            recommended_action="collect_more_clean_submitted_daemon_windows_before_escalation",
        ),
        research_summary=GuiResearchSummary(strategy_rows=10),
    )

    report = build_gui_autonomous_readiness_report(snapshot)

    assert report.status == "blocked"
    assert report.reason == "insufficient_clean_daemon_activations"
    assert not report.ready_for_operator_managed_paper
    assert not report.ready_for_unattended_paper
    assert "insufficient_active_window_coverage" in report.blockers
    assert "collect_more_clean_submitted_daemon_windows" in report.next_steps
    assert report.to_dict()["snapshot"]["status"] == "operator-review"


def test_gui_autonomous_readiness_report_surfaces_capture_ready():
    snapshot = build_gui_operator_snapshot(
        daemon_status=GuiDaemonStatus(status="running", heartbeat_state="fresh", kill_switch_active=False),
        dashboard_summary=GuiDashboardSummary(monitor_status="passed", observed_positions=0),
        soak_summary=GuiSoakReadinessSummary(
            readiness_status="blocked",
            clean_activations=1,
            required_clean_activations=3,
            active_windows=("intraday",),
            required_active_windows=2,
            monitor_status="passed",
            data_parity_status="passed",
            flatten_status="passed",
            stewardship_status="passed",
            next_capture_window="market_open",
            next_capture_state="active",
            next_capture_command=("python", "main.py", "paper-daemon"),
        ),
        research_summary=GuiResearchSummary(strategy_rows=10),
    )

    report = build_gui_autonomous_readiness_report(snapshot)

    assert report.status == "capture-ready"
    assert report.reason == "next_capture_window_ready"
    assert not report.ready_for_unattended_paper
    assert "insufficient_clean_daemon_activations" in report.blockers
    assert report.card_lines()[0] == "Autonomous readiness: capture-ready (next_capture_window_ready)"


def test_gui_autonomous_readiness_report_writes_json_artifact(tmp_path):
    snapshot = build_gui_operator_snapshot(
        daemon_status=GuiDaemonStatus(status="running", heartbeat_state="fresh", kill_switch_active=False),
        dashboard_summary=GuiDashboardSummary(monitor_status="passed", observed_positions=0),
        soak_summary=GuiSoakReadinessSummary(
            readiness_status="ready",
            clean_activations=3,
            required_clean_activations=3,
            active_windows=("market_open", "intraday"),
            required_active_windows=2,
            monitor_status="passed",
            data_parity_status="passed",
            flatten_status="passed",
            stewardship_status="passed",
        ),
        research_summary=GuiResearchSummary(strategy_rows=10),
    )
    report = build_gui_autonomous_readiness_report(snapshot)

    path = write_gui_autonomous_readiness_report(report, tmp_path / "readiness.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "autonomous-ready"
    assert payload["ready_for_unattended_paper"]
    assert payload["snapshot"]["autonomy"]["clean_activations"] == 3
