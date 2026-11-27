import json

from src.reporting import (
    build_anomaly_highlight_report,
    build_data_drift_chart_report,
    build_live_readiness_score_report,
    build_operator_decision_log_report,
    build_paper_pnl_attribution_chart_report,
    build_paper_review_summary_report,
    build_readiness_trend_report,
    build_release_candidate_signoff_report,
    build_slippage_fill_quality_report,
    build_why_no_live_yet_report,
    write_anomaly_highlight_report,
    write_data_drift_chart_report,
    write_live_readiness_score_report,
    write_operator_decision_log_report,
    write_paper_pnl_attribution_chart_report,
    write_paper_review_summary_report,
    write_readiness_trend_report,
    write_release_candidate_signoff_report,
    write_slippage_fill_quality_report,
    write_why_no_live_yet_report,
)


def test_slippage_fill_quality_report_outputs_chart_ready_points(tmp_path):
    report = build_slippage_fill_quality_report(
        [
            {"timestamp": "2026-07-27T14:00:00Z", "symbol": "SPY", "strategy": "buyHold", "order_type": "limit", "slippage_bps": 1.5},
            {"timestamp": "2026-07-27T15:00:00Z", "symbol": "QQQ", "strategy": "buyHold", "order_type": "market", "slippage_bps": 4.5},
        ],
        generated_at="2026-07-27T16:00:00Z",
    )
    path = write_slippage_fill_quality_report(report, tmp_path / "slippage.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["summary"]["fills"] == 2
    assert payload["summary"]["average_slippage_bps"] == 3.0
    assert payload["chart_points"][0]["series"] == "buyHold|SPY|limit"


def test_data_drift_and_readiness_trend_reports_detect_breaches_and_regressions(tmp_path):
    drift = build_data_drift_chart_report(
        [
            {"timestamp": "2026-07-27", "provider": "alpaca", "comparison_provider": "yfinance", "symbol": "SPY", "close_diff_bps": 2.0, "status": "passed"},
            {"timestamp": "2026-07-27", "provider": "alpaca", "comparison_provider": "yfinance", "symbol": "QQQ", "close_diff_bps": 18.0, "status": "passed"},
        ],
        max_close_diff_bps=10.0,
        generated_at="2026-07-27T16:00:00Z",
    )
    trend = build_readiness_trend_report(
        [
            {"timestamp": "2026-07-25", "readiness_score": 0.8, "missing_required": [], "failed_required": [], "stale_check_ids": []},
            {"timestamp": "2026-07-27", "readiness_score": 0.6, "missing_required": ["deployment"], "failed_required": [], "stale_check_ids": ["paper_soak"]},
        ],
        generated_at="2026-07-27T16:00:00Z",
    )
    drift_payload = json.loads(write_data_drift_chart_report(drift, tmp_path / "drift.json").read_text(encoding="utf-8"))
    trend_payload = json.loads(write_readiness_trend_report(trend, tmp_path / "trend.json").read_text(encoding="utf-8"))

    assert drift_payload["summary"]["breaches"] == 1
    assert drift_payload["chart_points"][1]["y"] == 18.0
    assert trend_payload["summary"]["trend"] == "regressing"
    assert trend_payload["summary"]["latest_stale"] == 1


def test_pnl_attribution_and_review_summary_reports_group_operator_context(tmp_path):
    pnl = build_paper_pnl_attribution_chart_report(
        [
            {"strategy": "buyHold", "regime": "trend", "symbol": "SPY", "holding_period": "intraday", "pnl": 5.0},
            {"strategy": "buyHold", "regime": "trend", "symbol": "SPY", "holding_period": "intraday", "pnl": -2.0},
            {"strategy": "cycle", "regime": "chop", "symbol": "QQQ", "holding_period": "overnight", "pnl": -1.0},
        ],
        generated_at="2026-07-27T16:00:00Z",
    )
    summary = build_paper_review_summary_report(
        "daily",
        reports=[
            {"name": "monitor", "status": "passed", "orders_submitted": 1, "warnings": []},
            {"name": "scorecard", "status": "failed", "orders_submitted": 0, "warnings": ["slippage"]},
        ],
        notes=("review before next session",),
        generated_at="2026-07-27T16:00:00Z",
    )
    pnl_payload = json.loads(write_paper_pnl_attribution_chart_report(pnl, tmp_path / "pnl.json").read_text(encoding="utf-8"))
    summary_payload = json.loads(write_paper_review_summary_report(summary, tmp_path / "summary.json").read_text(encoding="utf-8"))

    assert pnl_payload["summary"]["total_pnl"] == 2.0
    assert pnl_payload["grouped_totals"]["buyHold|trend|SPY|intraday"] == 3.0
    assert summary_payload["summary"]["blocking_reports"] == 1
    assert summary_payload["notes"] == ["review before next session"]


def test_anomalies_operator_decisions_and_release_signoff_capture_blockers(tmp_path):
    anomalies = build_anomaly_highlight_report(
        [
            {"metric": "fill_price", "severity": "low", "status": "passed", "reason": "inside_tolerance"},
            {"metric": "position_value", "severity": "high", "status": "failed", "reason": "unexpected_broker_position"},
        ],
        generated_at="2026-07-27T16:00:00Z",
    )
    decisions = build_operator_decision_log_report(
        [
            {"operator": "local", "timestamp": "2026-07-27T16:00:00Z", "decision": "increase_paper_notional", "approved": False},
            {"operator": "local", "timestamp": "2026-07-27T16:05:00Z", "decision": "rerun_monitor", "approved": True},
        ],
        generated_at="2026-07-27T16:00:00Z",
    )
    signoff = build_release_candidate_signoff_report(
        "abc123",
        "cfg456",
        checks=[
            {"name": "tests", "status": "passed"},
            {"name": "paper_soak", "status": "missing", "reason": "not_enough_sessions"},
        ],
        operator_approved=True,
        generated_at="2026-07-27T16:00:00Z",
    )
    anomaly_payload = json.loads(write_anomaly_highlight_report(anomalies, tmp_path / "anomalies.json").read_text(encoding="utf-8"))
    decision_payload = json.loads(write_operator_decision_log_report(decisions, tmp_path / "decisions.json").read_text(encoding="utf-8"))
    signoff_payload = json.loads(write_release_candidate_signoff_report(signoff, tmp_path / "signoff.json").read_text(encoding="utf-8"))

    assert anomaly_payload["summary"]["blocking_anomalies"] == 1
    assert decision_payload["summary"]["approvals"] == 1
    assert signoff_payload["summary"]["ready_for_release"] is False
    assert signoff_payload["blockers"][0]["name"] == "paper_soak"


def test_why_no_live_and_live_readiness_score_require_live_evidence(tmp_path):
    gates = [
        {"name": "paper_soak", "status": "passed", "evidence_type": "paper"},
        {"name": "live_order_preview", "status": "passed", "evidence_type": "live"},
        {"name": "live_account_monitor", "status": "missing", "evidence_type": "live"},
    ]
    why = build_why_no_live_yet_report(gates, generated_at="2026-07-27T16:00:00Z")
    score = build_live_readiness_score_report(gates, generated_at="2026-07-27T16:00:00Z")
    why_payload = json.loads(write_why_no_live_yet_report(why, tmp_path / "why.json").read_text(encoding="utf-8"))
    score_payload = json.loads(write_live_readiness_score_report(score, tmp_path / "score.json").read_text(encoding="utf-8"))

    assert why_payload["summary"]["live_unlocked"] is False
    assert why_payload["blockers"][0]["name"] == "live_account_monitor"
    assert score_payload["summary"]["score"] == 1 / 3
    assert score_payload["summary"]["simulated_only_passes"] == 1
    assert score_payload["summary"]["ready"] is False
