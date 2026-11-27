import json

from src.app import TradingApplication
from src.config import MarketDataConfig, RuntimeConfig, StrategyConfig
from src.operations import AutonomousPaperSessionOptions, PortfolioPaperSessionOptions, run_autonomous_paper_session, run_portfolio_paper_session
from src.reporting import (
    build_order_lifecycle_timeline,
    build_daily_paper_trading_report,
    build_paper_dashboard_report,
    build_paper_run_comparison_report,
    build_paper_activation_report,
    build_position_lifecycle_timeline,
    build_strategy_review_report,
    render_paper_dashboard_html,
    render_strategy_review_html,
    write_backtest_report,
    write_daily_paper_trading_report,
    write_order_lifecycle_timeline,
    write_paper_dashboard_html,
    write_paper_dashboard_report,
    write_paper_run_comparison_report,
    write_paper_activation_report,
    write_position_lifecycle_timeline,
    write_strategy_review_html,
    write_strategy_review_report,
)


def test_backtest_report_writes_json(tmp_path):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )
    result = app.run_backtest()

    path = write_backtest_report(result, tmp_path / "report.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["fills"]
    assert payload["trades"]
    assert payload["metrics"]["ending_equity"] > 0


def test_daily_paper_trading_report_summarizes_sessions_and_portfolio(tmp_path):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
        )
    )
    session = run_autonomous_paper_session(app, AutonomousPaperSessionOptions(artifact_root=str(tmp_path / "session")))
    portfolio = run_portfolio_paper_session(
        app,
        PortfolioPaperSessionOptions(
            symbols=("SPY", "QQQ"),
            artifact_root=str(tmp_path / "portfolio"),
            requested_weight=0.10,
        ),
    )

    report = build_daily_paper_trading_report(
        sessions=(session,),
        portfolio_report=portfolio,
        report_date="2026-07-13",
        notes=("offline smoke",),
    )
    path = write_daily_paper_trading_report(report, tmp_path / "daily.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["summary"]["sessions"] == 1
    assert payload["summary"]["orders_planned"] == 3
    assert payload["orders"]["portfolio_consolidated"]
    assert payload["fills"]["missed_or_unsubmitted_sessions"] == 1
    assert payload["recommendations"]
    assert payload["notes"] == ["offline smoke"]


def test_paper_activation_report_summarizes_broker_proof_and_evidence(tmp_path):
    broker_proof = tmp_path / "broker-proof.json"
    schedule = tmp_path / "schedule.json"
    evidence = tmp_path / "paper-submit.json"
    cleanup = tmp_path / "cleanup.json"
    broker_proof.write_text(
        json.dumps(
            {
                "passed": False,
                "submitted": False,
                "reason": "market_session_not_tradable",
                "orders": [],
                "execution_reports": [],
                "polled_execution_reports": [],
            }
        ),
        encoding="utf-8",
    )
    schedule.write_text(
        json.dumps(
            {
                "passed": False,
                "checks": [{"name": "active_window", "passed": False, "reason": "no_active_broker_proof_window"}],
                "windows": [{"name": "intraday", "start_time": "10:00:00", "end_time": "14:30:00", "submit_orders_allowed": True}],
            }
        ),
        encoding="utf-8",
    )
    evidence.write_text(
        json.dumps(
            {
                "evidence": [
                    {"check_id": "real_alpaca_fill_polling", "status": "failed", "reason": "paper_broker_proof_not_submitted"},
                    {"check_id": "broker_account_parity", "status": "failed", "reason": "paper_broker_proof_not_submitted"},
                ]
            }
        ),
        encoding="utf-8",
    )
    cleanup.write_text(
        json.dumps(
            {
                "submit_requested": True,
                "submitted": False,
                "reason": "market_session_not_tradable",
                "positions_seen": [{"symbol": "SPY", "quantity": 0.033521}],
                "planned_orders": [{"symbol": "SPY", "side": "SELL", "quantity": 0.033521}],
            }
        ),
        encoding="utf-8",
    )

    report = build_paper_activation_report(
        broker_proof_path=broker_proof,
        scheduled_broker_proof_path=schedule,
        paper_submit_evidence_path=evidence,
        paper_cleanup_path=cleanup,
        report_date="2026-07-19",
    )
    output = write_paper_activation_report(report, tmp_path / "activation.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["summary"]["broker_submitted"] is False
    assert payload["summary"]["scheduled_reason"] == "no_active_broker_proof_window"
    assert payload["summary"]["cleanup_reason"] == "market_session_not_tradable"
    assert payload["summary"]["cleanup_positions_seen"] == 1
    assert payload["paper_cleanup"]["planned_orders"][0]["side"] == "SELL"
    assert payload["paper_submit_evidence"]["real_alpaca_fill_polling"]["reason"] == "paper_broker_proof_not_submitted"
    assert payload["next_windows"][0]["name"] == "intraday"
    assert payload["warnings"]
    assert any("paper cleanup" in recommendation for recommendation in payload["recommendations"])


def test_paper_dashboard_report_tracks_exposure_monitors_strategies_and_orders(tmp_path):
    report = build_paper_dashboard_report(
        exposures=[
            {"symbol": "SPY", "expected_quantity": 1.0, "broker_quantity": 1.0, "notional": 500.0, "tolerance": 0.001},
            {"symbol": "QQQ", "expected_quantity": 0.0, "broker_quantity": 0.25, "notional": 100.0},
        ],
        monitors=[
            {"name": "broker_account_state", "status": "passed", "source_artifact": "reports/account.json"},
            {"name": "open_orders", "status": "failed", "reason": "stale_order"},
        ],
        strategies=[
            {"name": "buyHold", "enabled": True, "state": "active", "current_signal": "BUY", "scorecard_status": "passed"},
            {"name": "meanReversion", "enabled": True, "state": "paused", "scorecard_status": "blocked"},
        ],
        open_orders=[{"symbol": "QQQ", "side": "BUY", "quantity": 0.25, "status": "new"}],
        pnl={"day_pnl": 12.5, "open_pnl": -1.0},
        risk_state={"status": "ok"},
        next_action={"name": "intraday_monitor", "scheduled_at": "2026-07-27T15:00:00Z"},
        generated_at="2026-07-27T14:00:00Z",
    )
    output = write_paper_dashboard_report(report, tmp_path / "dashboard.json")
    html_output = write_paper_dashboard_html(report, tmp_path / "dashboard.html")
    payload = json.loads(output.read_text(encoding="utf-8"))
    html = render_paper_dashboard_html(report)

    assert payload["summary"]["ready_for_next_action"] is False
    assert payload["summary"]["exposure_mismatches"] == 1
    assert payload["summary"]["failing_monitors"] == 1
    assert payload["summary"]["active_strategies"] == 1
    assert payload["open_orders"][0]["symbol"] == "QQQ"
    assert "Paper Trading Dashboard" in html
    assert html_output.read_text(encoding="utf-8") == html


def test_strategy_review_report_renders_research_trades_and_scorecards(tmp_path):
    report = build_strategy_review_report(
        "hurstCycleReversion",
        enabled=True,
        state="active",
        research_evidence=[{"artifact": "reports/hurst.json", "status": "passed", "metric": "sharpe", "value": 1.2}],
        latest_trades=[{"timestamp": "2026-07-27T14:00:00Z", "symbol": "SPY", "side": "BUY", "quantity": 1, "pnl": 3.25}],
        paper_scorecards=[{"artifact": "reports/scorecard.json", "status": "passed", "reason": "clean"}],
        notes=("watch regime filter",),
    )
    output = write_strategy_review_report(report, tmp_path / "strategy.json")
    html_output = write_strategy_review_html(report, tmp_path / "strategy.html")
    payload = json.loads(output.read_text(encoding="utf-8"))
    html = render_strategy_review_html(report)

    assert payload["summary"]["ready_for_enablement"] is True
    assert payload["summary"]["research_evidence"] == 1
    assert payload["latest_trades"][0]["pnl"] == 3.25
    assert "hurstCycleReversion Strategy Review" in html
    assert html_output.read_text(encoding="utf-8") == html


def test_order_and_position_lifecycle_timelines_record_required_stages(tmp_path):
    order = build_order_lifecycle_timeline(
        order_id="paper-order-1",
        symbol="SPY",
        side="BUY",
        events=[
            {"timestamp": "2026-07-27T14:00:00Z", "stage": "intent", "status": "passed", "description": "planned"},
            {"timestamp": "2026-07-27T14:00:01Z", "stage": "submit", "status": "passed", "description": "accepted"},
            {"timestamp": "2026-07-27T14:00:02Z", "stage": "reconcile", "status": "passed", "description": "matched"},
        ],
    )
    position = build_position_lifecycle_timeline(
        position_id="SPY-buyHold-20260727",
        symbol="SPY",
        strategy="buyHold",
        events=[
            {"timestamp": "2026-07-27T14:00:02Z", "stage": "entry", "status": "passed"},
            {"timestamp": "2026-07-27T20:00:00Z", "stage": "exit", "status": "passed"},
        ],
    )
    order_path = write_order_lifecycle_timeline(order, tmp_path / "order.json")
    position_path = write_position_lifecycle_timeline(position, tmp_path / "position.json")

    assert json.loads(order_path.read_text(encoding="utf-8"))["summary"]["complete"] is True
    assert json.loads(position_path.read_text(encoding="utf-8"))["summary"]["open"] is False
    assert json.loads(position_path.read_text(encoding="utf-8"))["summary"]["clean"] is True


def test_paper_run_comparison_report_ranks_repeated_pilots(tmp_path):
    report = build_paper_run_comparison_report(
        runs=[
            {"run_id": "session-a", "strategy": "buyHold", "total_pnl": 1.0, "orders": 1},
            {"run_id": "session-b", "strategy": "hurstCycleReversion", "total_pnl": 3.5, "orders": 2},
            {"run_id": "session-c", "strategy": "volumePressureBreakout", "total_pnl": -0.5, "orders": 0},
        ],
        metric="total_pnl",
        generated_at="2026-07-27T16:00:00Z",
    )
    output = write_paper_run_comparison_report(report, tmp_path / "comparison.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["summary"]["runs"] == 3
    assert payload["summary"]["best_run_id"] == "session-b"
    assert [run["run_id"] for run in payload["runs"]] == ["session-b", "session-a", "session-c"]
