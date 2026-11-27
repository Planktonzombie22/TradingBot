import json

from src.operations import (
    build_live_account_monitor_report,
    build_live_broker_adapter_boundary_report,
    build_live_command_confirmation_report,
    build_live_micro_trade_proof_report,
    build_live_order_lifecycle_reconciliation_report,
    build_live_order_preview_report,
    build_live_paper_parity_replay_report,
    build_live_position_flatten_plan_report,
    build_live_post_order_lockout_report,
    build_live_readiness_validation_evidence_report,
    build_live_release_bundle_report,
    build_live_risk_cap_report,
    build_live_scheduler_mode_report,
    build_one_live_order_per_day_report,
    write_live_readiness_report,
)


def test_live_broker_adapter_boundary_separates_endpoints_and_redacts_account(tmp_path):
    account_id = "ACCT-LIVE-001"
    report = build_live_broker_adapter_boundary_report(
        account_id=account_id,
        approved_account_ids=[account_id],
        shared_submit_defaults=False,
        live_submit_default_enabled=False,
    )
    payload = json.loads(write_live_readiness_report(report, tmp_path / "boundary.json").read_text(encoding="utf-8"))

    assert payload["passed"] is True
    assert payload["paper_endpoint"] != payload["live_endpoint"]
    assert account_id not in json.dumps(payload)


def test_live_order_preview_refuses_submit_but_records_final_intended_order():
    report = build_live_order_preview_report(
        [{"symbol": "SPY", "side": "BUY", "quantity": 0.01, "price": 500.0}],
        {"max_first_order_notional": 10.0, "max_daily_notional": 10.0},
    )
    payload = report.to_dict()

    assert payload["passed"] is True
    assert payload["refused_to_submit"] is True
    assert payload["total_notional"] == 5.0


def test_live_micro_trade_proof_requires_operator_approval_and_monitor_artifact_without_submit():
    report = build_live_micro_trade_proof_report(
        "SPY",
        planned_notional=5.0,
        operator_approved=True,
        submitted=False,
        monitor_artifact="reports/live-monitor-preview.json",
    )

    assert report.passed is True
    assert report.to_dict()["submitted"] is False


def test_live_account_monitor_uses_stricter_position_tolerance():
    clean = build_live_account_monitor_report(
        [{"symbol": "SPY", "quantity": 1.0}],
        [{"symbol": "SPY", "quantity": 1.0000001}],
        tolerance_quantity=0.000001,
    )
    dirty = build_live_account_monitor_report(
        [{"symbol": "SPY", "quantity": 1.0}],
        [{"symbol": "SPY", "quantity": 1.01}],
        tolerance_quantity=0.000001,
    )

    assert clean.passed is True
    assert dirty.passed is False
    assert dirty.mismatches[0]["symbol"] == "SPY"


def test_live_order_lifecycle_requires_intent_submit_and_reconcile_stages():
    report = build_live_order_lifecycle_reconciliation_report(
        [
            {"order_id": "live-preview-1", "stage": "intent", "status": "passed"},
            {"order_id": "live-preview-1", "stage": "submit", "status": "passed"},
            {"order_id": "live-preview-1", "stage": "reconcile", "status": "passed"},
        ]
    )
    missing = build_live_order_lifecycle_reconciliation_report(
        [{"order_id": "live-preview-2", "stage": "intent", "status": "passed"}]
    )

    assert report.passed is True
    assert missing.passed is False
    assert missing.missing_order_ids == ("live-preview-2",)


def test_live_position_flatten_plan_requires_approval_and_emergency_path():
    report = build_live_position_flatten_plan_report(
        [{"symbol": "SPY", "quantity": 1.25}, {"symbol": "QQQ", "quantity": -0.5}],
        operator_approved=True,
        emergency_path="docs/emergency/live-flatten.md",
    )
    payload = report.to_dict()

    assert payload["passed"] is True
    assert payload["submitted"] is False
    assert payload["planned_orders"] == [
        {"symbol": "SPY", "side": "SELL", "quantity": 1.25, "order_type": "MARKET", "reason": "live_position_flatten_preview"},
        {"symbol": "QQQ", "side": "BUY", "quantity": 0.5, "order_type": "MARKET", "reason": "live_position_flatten_preview"},
    ]


def test_live_validation_evidence_cannot_be_satisfied_by_paper_artifacts():
    report = build_live_readiness_validation_evidence_report(
        [
            {"check_id": "live_order_preview", "status": "passed", "evidence_type": "live"},
            {"check_id": "live_micro_proof", "status": "passed", "evidence_type": "paper"},
        ]
    )

    assert report.passed is False
    assert "live_micro_proof" in report.missing_checks


def test_live_release_bundle_requires_current_paper_deployment_monitor_risk_and_approval():
    blocked = build_live_release_bundle_report(
        paper_soak_current=True,
        deployment_proof_current=True,
        monitor_proof_current=False,
        risk_settings_current=True,
        operator_approved=True,
    )
    ready = build_live_release_bundle_report(True, True, True, True, True)

    assert blocked.passed is False
    assert blocked.to_dict()["blockers"] == ["monitor_proof_current"]
    assert ready.passed is True


def test_live_risk_caps_cover_first_order_daily_loss_positions_and_gross_exposure():
    report = build_live_risk_cap_report(
        [{"symbol": "SPY", "quantity": 1, "price": 20.0}],
        {
            "max_first_order_notional": 10.0,
            "max_daily_notional": 100.0,
            "max_daily_loss": 25.0,
            "max_open_positions": 1,
            "max_gross_exposure": 100.0,
        },
        current_open_positions=1,
    )

    assert report.passed is False
    assert report.blockers == ("max_first_order_notional", "max_open_positions")


def test_live_scheduler_stays_disabled_until_micro_proof_passes():
    disabled = build_live_scheduler_mode_report(enabled=False, mode="manual", micro_proof_passed=False)
    blocked = build_live_scheduler_mode_report(enabled=True, mode="scheduled", micro_proof_passed=False)

    assert disabled.passed is True
    assert blocked.passed is False


def test_live_command_confirmation_records_account_strategy_order_and_risk_without_raw_account():
    account_id = "ACCT-LIVE-002"
    report = build_live_command_confirmation_report(
        "2026-07-28T14:00:00Z",
        account_id,
        "buyHold",
        5.0,
        {"symbol": "SPY", "side": "BUY", "quantity": 0.01},
        {"max_first_order_notional": 10.0},
        operator_approved=True,
    )
    payload = report.to_dict()

    assert payload["passed"] is True
    assert account_id not in json.dumps(payload)


def test_one_live_order_per_day_blocks_prior_or_multiple_requested_orders():
    clean = build_one_live_order_per_day_report("2026-07-28", [], [{"symbol": "SPY"}])
    blocked = build_one_live_order_per_day_report("2026-07-28", [{"symbol": "QQQ"}], [{"symbol": "SPY"}])

    assert clean.passed is True
    assert blocked.passed is False


def test_live_post_order_lockout_persists_until_monitor_reconciliation_and_daily_report_pass():
    report = build_live_post_order_lockout_report(
        live_order_seen=True,
        monitor_passed=True,
        reconciliation_passed=False,
        daily_report_passed=True,
    )

    assert report.locked is True
    assert report.passed is False


def test_live_paper_parity_replay_compares_live_paper_and_backtest_results():
    clean = build_live_paper_parity_replay_report(
        {"signal": "BUY", "notional": 5.0},
        {"signal": "BUY", "notional": 5.4},
        {"signal": "BUY", "notional": 5.2},
        max_notional_diff=1.0,
    )
    dirty = build_live_paper_parity_replay_report(
        {"signal": "BUY", "notional": 5.0},
        {"signal": "SELL", "notional": 10.0},
        {"signal": "BUY", "notional": 5.0},
        max_notional_diff=1.0,
    )

    assert clean.passed is True
    assert dirty.passed is False
    assert dirty.signal_diff == 1
