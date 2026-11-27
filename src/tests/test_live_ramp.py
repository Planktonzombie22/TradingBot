import json

from src.operations import (
    build_live_capital_ramp_approval_report,
    build_live_issue_response_report,
    build_live_loss_budget_report,
    build_live_micro_order_evidence_report,
    build_live_micro_phase_scope_report,
    build_live_notional_ramp_report,
    build_live_paper_fill_comparison_report,
    build_live_strategy_quarantine_report,
    build_parallel_paper_control_report,
    build_post_micro_capital_boundary_report,
    write_live_ramp_report,
)


def test_live_micro_phase_scope_keeps_first_phase_tiny_and_narrow(tmp_path):
    clean = build_live_micro_phase_scope_report(["buyHold"], ["SPY"], max_orders_per_day=1, max_notional=5.0)
    broad = build_live_micro_phase_scope_report(["buyHold", "cycle"], ["SPY", "QQQ", "IWM"], max_orders_per_day=2, max_notional=5.0)
    payload = json.loads(write_live_ramp_report(clean, tmp_path / "scope.json").read_text(encoding="utf-8"))

    assert payload["passed"] is True
    assert clean.passed is True
    assert broad.passed is False


def test_live_micro_order_evidence_requires_preview_monitor_reconcile_report_and_parity():
    report = build_live_micro_order_evidence_report(
        "live-order-1",
        preview_passed=True,
        monitor_passed=True,
        reconciliation_passed=True,
        daily_report_passed=False,
        parity_passed=True,
    )
    payload = report.to_dict()

    assert payload["passed"] is False
    assert payload["blockers"] == ["daily_report_passed"]


def test_live_notional_ramp_requires_clean_live_trades_current_paper_and_approval():
    blocked = build_live_notional_ramp_report(5.0, 10.0, clean_live_micro_trades=4, required_clean_trades=5, current_paper_evidence=True, operator_approved=True)
    approved = build_live_notional_ramp_report(5.0, 10.0, clean_live_micro_trades=5, required_clean_trades=5, current_paper_evidence=True, operator_approved=True)

    assert blocked.passed is False
    assert blocked.approved_notional == 5.0
    assert approved.passed is True
    assert approved.approved_notional == 10.0


def test_live_issue_response_locks_and_downshifts_on_any_micro_phase_issue():
    report = build_live_issue_response_report(
        10.0,
        {
            "live_monitor_mismatch": True,
            "unresolved_order": False,
            "data_outage": False,
            "rejected_order": True,
            "slippage_breach": False,
            "drawdown_breach": False,
        },
        downshift_notional=5.0,
    )

    assert report.locked is True
    assert report.recommended_notional == 5.0
    assert report.active_issues == ("live_monitor_mismatch", "rejected_order")


def test_parallel_paper_control_requires_matching_paper_orders_for_live_symbols():
    report = build_parallel_paper_control_report(
        live_orders=[{"symbol": "SPY"}, {"symbol": "QQQ"}],
        paper_orders=[{"symbol": "SPY"}],
        control_active=True,
    )

    assert report.passed is False
    assert report.missing_symbols == ("QQQ",)


def test_live_paper_fill_comparison_detects_fill_quality_differences():
    clean = build_live_paper_fill_comparison_report(
        [{"symbol": "SPY", "live_fill_price": 100.01, "paper_fill_price": 100.0}],
        max_price_diff_bps=2.0,
    )
    breach = build_live_paper_fill_comparison_report(
        [{"symbol": "SPY", "live_fill_price": 101.0, "paper_fill_price": 100.0}],
        max_price_diff_bps=2.0,
    )

    assert clean.passed is True
    assert breach.passed is False
    assert round(breach.breaches[0]["price_diff_bps"], 2) == 100.0


def test_live_strategy_quarantine_retires_bad_live_behavior():
    report = build_live_strategy_quarantine_report(
        "buyHold",
        fill_quality_passed=True,
        behavior_parity_passed=False,
        divergence_count=1,
        max_divergence_count=0,
    )

    assert report.quarantined is True
    assert report.to_dict()["passed"] is False


def test_live_capital_ramp_approval_requires_operator_timestamp_and_notional():
    blocked = build_live_capital_ramp_approval_report(
        [{"operator": "local", "timestamp": "2026-07-28T15:00:00Z", "approved": True, "approved_notional": 5.0}],
        requested_notional=10.0,
    )
    approved = build_live_capital_ramp_approval_report(
        [{"operator": "local", "timestamp": "2026-07-28T15:00:00Z", "approved": True, "approved_notional": 10.0}],
        requested_notional=10.0,
    )

    assert blocked.passed is False
    assert approved.passed is True


def test_live_loss_budget_requires_budget_compliance_and_three_clean_micro_months():
    blocked = build_live_loss_budget_report(realized_loss=3.0, unrealized_loss=1.0, max_loss_budget=5.0, clean_micro_months=2)
    breached = build_live_loss_budget_report(realized_loss=4.0, unrealized_loss=2.0, max_loss_budget=5.0, clean_micro_months=3)
    clean = build_live_loss_budget_report(realized_loss=2.0, unrealized_loss=1.0, max_loss_budget=5.0, clean_micro_months=3)

    assert blocked.passed is False
    assert breached.passed is False
    assert clean.passed is True


def test_post_micro_capital_requires_fresh_review_for_any_next_phase():
    micro = build_post_micro_capital_boundary_report("micro")
    scale = build_post_micro_capital_boundary_report("scale", fresh_review_required=True, fresh_review_approved=False)
    reviewed = build_post_micro_capital_boundary_report("scale", fresh_review_required=True, fresh_review_approved=True)

    assert micro.passed is True
    assert scale.passed is False
    assert reviewed.passed is True
