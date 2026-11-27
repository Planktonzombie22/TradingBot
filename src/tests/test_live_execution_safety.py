import json

import pytest

from src.config import AlpacaConfig
from src.execution import (
    LockedAlpacaLiveBroker,
    build_account_allowlist_report,
    build_audit_log_integrity_report,
    build_compliance_awareness_report,
    build_emergency_procedure_report,
    build_live_kill_switch_drill_report,
    build_live_order_boundary_report,
    build_live_order_cap_report,
    build_live_still_locked_report,
    build_live_unlock_report,
    build_manual_approval_workflow_report,
    build_no_live_submit_report,
    build_read_only_reporting_mode_report,
    build_redaction_regression_report,
    build_secret_scan_report,
    write_live_safety_report,
)
from src.models import Order


def test_live_adapter_boundary_exists_but_refuses_live_submission():
    report = build_live_order_boundary_report()
    broker = LockedAlpacaLiveBroker(AlpacaConfig(base_url="https://api.alpaca.markets"))

    assert report.passed
    with pytest.raises(RuntimeError, match="Live Alpaca order submission is locked"):
        broker.submit_order(Order(symbol="SPY", side="BUY", quantity=1))


def test_live_unlock_requires_every_independent_gate_and_adapter_implementation(tmp_path):
    report = build_live_unlock_report(
        {
            "config_flag": True,
            "env_flag": True,
            "base_url": "https://api.alpaca.markets",
            "risk_profile": True,
            "approval_artifact": True,
            "command_flag": True,
            "live_adapter_implemented": False,
        }
    )
    path = write_live_safety_report(report, tmp_path / "unlock.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["live_unlocked"] is False
    assert payload["blockers"][0]["name"] == "live_adapter_implemented"
    assert payload["blockers"][0]["reason"] == "live_adapter_not_implemented"


def test_account_allowlist_uses_fingerprints_without_exposing_raw_account_ids():
    raw_account = "ACCT-LIVE-123456789"
    report = build_account_allowlist_report(raw_account, [raw_account])
    payload = report.to_dict()

    assert payload["passed"] is True
    assert raw_account not in json.dumps(payload)
    assert len(payload["account_fingerprint"]) == 16


def test_live_order_caps_block_oversized_orders_and_position_exposure():
    report = build_live_order_cap_report(
        orders=[Order(symbol="SPY", side="BUY", quantity=2), {"symbol": "QQQ", "quantity": 1}],
        prices={"SPY": 100.0, "QQQ": 50.0},
        max_order_notional=150.0,
        max_daily_notional=300.0,
        max_daily_loss=25.0,
        max_open_positions=2,
        max_gross_exposure=225.0,
        current_open_positions=1,
        current_gross_exposure=25.0,
        current_daily_loss=-10.0,
    )
    reasons = {check["name"]: check["reason"] for check in report.to_dict()["checks"] if not check["passed"]}

    assert report.passed is False
    assert reasons["max_order_notional"] == "max_order_notional_exceeded"
    assert reasons["max_open_positions"] == "max_open_positions_exceeded"
    assert reasons["max_gross_exposure"] == "max_gross_exposure_exceeded"


def test_live_kill_switch_drill_requires_dry_run_and_paper_before_unlock():
    report = build_live_kill_switch_drill_report(dry_run_passed=True, paper_passed=False, live_unlock_requested=True)

    assert report.passed is False
    assert report.live_unlock_allowed is False


def test_no_live_submit_report_flags_non_live_commands_touching_live_endpoint():
    report = build_no_live_submit_report(
        [
            {"command": "paper-session", "execution_mode": "paper", "touches_live_endpoint": False, "submits_live_order": False},
            {"command": "validate", "execution_mode": "dry-run", "touches_live_endpoint": True, "submits_live_order": False},
        ]
    )
    payload = report.to_dict()

    assert payload["passed"] is False
    assert payload["violations"][0]["command"] == "validate"


def test_secret_scan_and_redaction_reports_find_sensitive_material_without_logging_values():
    secret = "ALPACA_API_KEY=PKABCDEF123456789"
    scan = build_secret_scan_report({"reports/proof.json": secret})
    redaction = build_redaction_regression_report([{"api_key": "***", "account": "acct_****"}], ["PKABCDEF123456789", "ACCT-LIVE-123"])

    assert scan.passed is False
    assert scan.to_dict()["findings"][0]["findings"] == ["alpaca_key"]
    assert secret not in json.dumps(scan.to_dict())
    assert redaction.passed is True


def test_audit_log_integrity_builds_hash_chain_and_detects_tampering():
    report = build_audit_log_integrity_report(
        [
            {"run_id": "run-1", "command": "paper-session", "decision": "blocked"},
            {"run_id": "run-2", "command": "paper-monitor", "decision": "passed"},
        ]
    )
    tampered_entries = list(report.entries)
    tampered_entries[1] = {**tampered_entries[1], "decision": "changed"}

    assert report.passed is True
    assert report.to_dict()["entries"][1]["previous_digest"] == report.to_dict()["entries"][0]["digest"]
    assert type(report)(tuple(tampered_entries)).passed is False


def test_read_only_mode_and_manual_approval_workflow_keep_risky_actions_explicit():
    read_only = build_read_only_reporting_mode_report("read-only", broker_submit_requested=False)
    approvals = build_manual_approval_workflow_report(
        [
            {"action": "increase_paper_notional", "operator": "local", "timestamp": "2026-07-28T12:00:00Z", "approved": True},
            {"action": "enable_live_mode", "operator": "local", "timestamp": "2026-07-28T12:05:00Z", "approved": False},
        ],
        required_actions=("increase_paper_notional", "enable_live_mode"),
    )

    assert read_only.passed is True
    assert approvals.passed is False
    assert approvals.missing_actions == ("enable_live_mode",)


def test_emergency_and_compliance_reports_require_documented_operating_procedures():
    emergency = build_emergency_procedure_report(
        [
            {"name": "cancel_all", "documented": True, "tested_in_paper": True},
            {"name": "flatten_all", "documented": True, "tested_in_paper": True},
        ]
    )
    compliance = build_compliance_awareness_report(
        [
            {"topic": "pdt", "documented": True},
            {"topic": "margin", "documented": True},
            {"topic": "short_sales", "documented": True},
        ]
    )

    assert emergency.passed is False
    assert "rotate_keys" in emergency.missing_procedures
    assert compliance.passed is False
    assert "wash_sales" in compliance.missing_topics


def test_live_still_locked_report_must_pass_until_live_milestone_is_intentional():
    unlock = build_live_unlock_report({"config_flag": False})
    no_live = build_no_live_submit_report(
        [{"command": "paper-session", "execution_mode": "paper", "touches_live_endpoint": False, "submits_live_order": False}]
    )
    report = build_live_still_locked_report(unlock, no_live, live_adapter_available=False)

    assert report.passed is True
    assert report.to_dict()["live_locked"] is True
