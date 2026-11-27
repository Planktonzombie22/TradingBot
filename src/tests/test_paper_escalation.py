import json

from src.operations import (
    build_cash_decision_respect_report,
    build_paper_active_evidence_report,
    build_paper_live_fire_drill_report,
    build_paper_month_end_review_report,
    build_paper_notional_downshift_decision,
    build_paper_notional_escalation_report,
    build_regime_performance_review_report,
    build_scheduler_uptime_evidence_report,
    build_strategy_family_overnight_gate_report,
    build_strategy_paper_capital_ladder_report,
    build_undertrading_evidence_report,
    write_paper_escalation_report,
)


def test_paper_notional_escalation_requires_clean_session_ladder_evidence(tmp_path):
    report = build_paper_notional_escalation_report(
        {
            "clean_monitored_sessions": 20,
            "clean_exit_tests": True,
            "unresolved_orders": False,
            "scorecards_acceptable": False,
        },
        current_notional=25.0,
    )
    payload = json.loads(write_paper_escalation_report(report, tmp_path / "ladder.json").read_text(encoding="utf-8"))

    assert payload["approved_notional"] == 100.0
    assert payload["next_blocked_tier"]["target_notional"] == 250.0
    assert payload["next_blocked_tier"]["reason"] == "requires_acceptable_scorecards_slippage_pnl_drift_and_benchmark_behavior"


def test_notional_downshift_triggers_on_operational_or_strategy_failures():
    report = build_paper_notional_downshift_decision(
        250.0,
        {
            "failed_monitor": True,
            "reject_streak": 2,
            "unresolved_order": False,
            "strategy_scorecard_failed": True,
            "data_outage": False,
        },
    )

    assert report.downshifted
    assert report.recommended_notional == 100.0
    assert report.triggers == ("failed_monitor", "reject_streak", "strategy_scorecard_failed")


def test_strategy_capital_ladders_can_graduate_or_downshift_independently():
    report = build_strategy_paper_capital_ladder_report(
        [
            {
                "strategy": "buyHold",
                "current_notional": 25.0,
                "evidence": {"clean_monitored_sessions": 10},
            },
            {
                "strategy": "cycle",
                "current_notional": 100.0,
                "evidence": {"failed_monitor": True},
            },
        ]
    )
    payload = report.to_dict()

    assert payload["decisions"][0]["approved_notional"] == 50.0
    assert payload["decisions"][1]["approved_notional"] == 50.0
    assert payload["decisions"][1]["reason"] == "failed_monitor"


def test_live_fire_and_overnight_reports_require_drills_and_clean_flatten_proof():
    drills = build_paper_live_fire_drill_report(
        [
            {"name": "flatten_all", "passed": True, "paper_evidence_path": "reports/flatten.json"},
            {"name": "cancel_all", "passed": True, "paper_evidence_path": "reports/cancel.json"},
        ]
    )
    overnight = build_strategy_family_overnight_gate_report(
        [
            {"family": "trend", "holds_overnight": True, "clean_flatten_proven": True},
            {"family": "mean_reversion", "holds_overnight": True, "clean_flatten_proven": False},
        ]
    )

    assert drills.passed is False
    assert "broker_outage" in drills.missing_drills
    assert overnight.passed is False
    assert overnight.blocked_families[0]["family"] == "mean_reversion"


def test_paper_active_and_regime_reviews_gate_live_micro_readiness():
    active = build_paper_active_evidence_report(trading_days=29, clean_days=29)
    regimes = build_regime_performance_review_report(
        [
            {"regime": "trend", "reviewed": True, "paper_scorecard_passed": True},
            {"regime": "chop", "reviewed": True, "paper_scorecard_passed": True},
            {"regime": "high_volatility", "reviewed": True, "paper_scorecard_passed": True},
        ]
    )

    assert active.passed is False
    assert active.to_dict()["remaining_days"] == 1
    assert regimes.passed is False
    assert regimes.missing_regimes == ("low_volatility", "event_driven")


def test_undertrading_and_cash_decision_reports_prove_the_bot_can_stay_out():
    undertrading = build_undertrading_evidence_report(
        [
            {"symbol": "SPY", "decision": "BUY"},
            {"symbol": "QQQ", "decision": "HOLD"},
            {"symbol": "IWM", "decision": "cash"},
        ],
        min_no_trade_rate=0.50,
    )
    cash = build_cash_decision_respect_report(
        [
            {"symbol": "SPY", "out_of_regime": True, "decision": "HOLD"},
            {"symbol": "QQQ", "out_of_regime": True, "decision": "BUY"},
        ]
    )

    assert undertrading.passed is True
    assert undertrading.no_trade_rate == 2 / 3
    assert cash.passed is False
    assert cash.violations[0]["symbol"] == "QQQ"


def test_month_end_review_and_scheduler_uptime_require_complete_operating_evidence():
    month_end = build_paper_month_end_review_report(
        {
            "drawdown": {"max": 0.02},
            "exposure": {"gross": 250},
            "slippage": {"avg_bps": 1.2},
            "rejects": {"count": 0},
            "missed_fills": {"count": 0},
        }
    )
    uptime = build_scheduler_uptime_evidence_report(days_observed=14, missed_jobs=0, failed_jobs=0)

    assert month_end.passed is False
    assert month_end.missing_sections == ("operator_actions",)
    assert uptime.passed is True
