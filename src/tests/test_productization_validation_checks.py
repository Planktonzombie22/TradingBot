from datetime import datetime, timezone

from src.deployment import docker_profile, local_windows_task_profile, small_server_profile
from src.validation import (
    DeploymentRunRecord,
    GoldenArtifactCase,
    MarketSessionEvidenceEvent,
    build_autonomous_paper_trading_rehearsal_report,
    default_pre_live_upgrade_gates,
    evaluate_deployment_rehearsal,
    evaluate_deployment_run_evidence,
    evaluate_golden_artifacts,
    evaluate_hard_pre_live_upgrade_gates,
    evaluate_market_session_enforcement,
    generate_golden_artifact_fixture,
    propose_golden_artifact_update,
)


def test_deployment_rehearsal_requires_all_profile_checks_and_safe_profile_metadata():
    complete_checks = {
        "startup": True,
        "graceful_stop": True,
        "watchdog_timeout": True,
        "log_rotation": True,
        "artifact_persistence": True,
        "state_db_persistence": True,
        "restart_recovery": True,
    }
    evidence = {
        "windows-task": complete_checks,
        "docker": complete_checks,
        "small-server": complete_checks,
    }
    profiles = (local_windows_task_profile(), docker_profile(), small_server_profile())

    clean = evaluate_deployment_rehearsal(evidence, profiles)
    dirty = evaluate_deployment_rehearsal(
        {"docker": {**complete_checks, "state_db_persistence": False}},
        profiles,
    )

    assert clean.passed
    assert not dirty.passed
    probes = {probe.name: probe for probe in dirty.probes}
    assert probes["docker"].reason == "deployment_rehearsal_incomplete"
    assert not probes["docker"].evidence["checks"]["state_db_persistence"]
    assert probes["windows-task"].reason == "deployment_rehearsal_incomplete"


def test_market_session_enforcement_blocks_outside_and_unauthorized_submissions():
    clean = evaluate_market_session_enforcement(
        (
            MarketSessionEvidenceEvent(
                "market_open",
                datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc),
                market_open=True,
                order_generated=True,
                order_submitted=True,
                allowed_to_submit=True,
                reason="regular_session",
            ),
            MarketSessionEvidenceEvent(
                "after_close",
                datetime(2026, 7, 16, 22, 0, tzinfo=timezone.utc),
                market_open=False,
                order_generated=True,
                order_submitted=False,
                allowed_to_submit=False,
                reason="market_closed",
            ),
        )
    )
    dirty = evaluate_market_session_enforcement(
        (
            MarketSessionEvidenceEvent(
                "after_close",
                datetime(2026, 7, 16, 22, 0, tzinfo=timezone.utc),
                market_open=False,
                order_generated=True,
                order_submitted=True,
                allowed_to_submit=False,
                reason="market_closed",
            ),
            MarketSessionEvidenceEvent(
                "missing_reason",
                datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc),
                market_open=True,
                order_generated=True,
                order_submitted=False,
                allowed_to_submit=False,
            ),
        )
    )

    assert clean.passed
    assert not dirty.passed
    reasons = {probe.name: probe.reason for probe in dirty.probes if not probe.passed}
    assert reasons["outside_session_orders_blocked"] == "outside_session_order_submission_detected"
    assert reasons["submitted_orders_explicitly_allowed"] == "submission_without_calendar_permission"
    assert reasons["generation_policy_reason_recorded"] == "missing_market_session_policy_reason"


def test_deployment_run_evidence_collects_process_persistence_and_recovery_proof():
    started = datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 7, 16, 14, 5, tzinfo=timezone.utc)
    clean = evaluate_deployment_run_evidence(
        (
            DeploymentRunRecord("windows-task", 0, started, ended, True, False, True, True, True, True),
            DeploymentRunRecord("docker", 0, started, ended, True, False, True, True, True, True),
            DeploymentRunRecord("small-server", 0, started, ended, True, False, True, True, True, True),
        )
    )
    dirty = evaluate_deployment_run_evidence(
        (
            DeploymentRunRecord("docker", 1, started, ended, False, False, False, True, True, False),
        )
    )

    assert clean.passed
    assert not dirty.passed
    reasons = {probe.name: probe.reason for probe in dirty.probes if not probe.passed}
    assert reasons["required_profiles_exercised"] == "missing_deployment_profile_runs"
    assert reasons["docker_deployment_run"] == "deployment_run_evidence_incomplete"


def test_autonomous_paper_trading_rehearsal_report_combines_release_candidate_evidence():
    clean = build_autonomous_paper_trading_rehearsal_report(
        evidence_bundle={"passed": True, "latest_evidence": [{"check_id": "unit_test_suite"}]},
        schedule_report={"passed": True},
        release_decision={"decision": "release_ready"},
        readiness_page_path="reports/readiness.html",
        release_candidate_bundle="reports/release-candidate.json",
    )
    dirty = build_autonomous_paper_trading_rehearsal_report(
        evidence_bundle={"passed": True, "latest_evidence": []},
        schedule_report={"passed": False},
        release_decision={"decision": "blocked"},
    )

    assert clean.passed
    assert clean.reason == "autonomous_paper_rehearsal_passed"
    assert not dirty.passed
    assert dirty.reason == "missing_rehearsal_evidence_bundle"
    assert dirty.to_dict()["steps"][0]["name"] == "evidence_bundle"


def test_golden_artifacts_compare_expected_outputs_with_numeric_tolerances():
    clean = GoldenArtifactCase(
        "backtest_report",
        observed={"summary": {"total_return": 0.1004, "trades": 3}, "status": "complete"},
        expected={"summary": {"total_return": 0.1000, "trades": 3}, "status": "complete"},
        tolerances={"summary.total_return": 0.001},
    )
    dirty = GoldenArtifactCase(
        "daily_report",
        observed={"summary": {"passed": 1}, "warnings": ["late fill"]},
        expected={"summary": {"passed": 2}, "warnings": []},
    )

    report = evaluate_golden_artifacts((clean, dirty))
    probes = {probe.name: probe for probe in report.probes}

    assert not report.passed
    assert probes["backtest_report"].passed
    assert probes["daily_report"].reason == "golden_artifact_mismatch"
    mismatch_paths = {item["path"] for item in probes["daily_report"].evidence["mismatches"]}
    assert {"summary.passed", "warnings"} <= mismatch_paths


def test_golden_artifact_fixture_update_requires_review_until_approved():
    current = generate_golden_artifact_fixture(
        "daily_report",
        {"sessions": 1},
        {"summary": {"passed": 1}},
        approved_by="operator",
        source_digest="old",
    )

    review = propose_golden_artifact_update(current, {"summary": {"passed": 2}}, source_digest="new")
    approved = propose_golden_artifact_update(
        current,
        {"summary": {"passed": 2}},
        approved_by="operator",
        source_digest="new",
    )

    assert review.requires_review
    assert not review.approved
    assert review.mismatches[0]["path"] == "summary.passed"
    assert approved.approved
    assert not approved.requires_review
    assert approved.proposed_fixture.expected_payload["summary"]["passed"] == 2


def test_hard_pre_live_upgrade_gates_require_passing_artifact_backed_evidence():
    complete = {
        gate.name: {"passed": True, "artifact_path": f"reports/{gate.name}.json"}
        for gate in default_pre_live_upgrade_gates()
    }
    dirty = {
        **complete,
        "real_alpaca_fill_polling": {"passed": True},
        "borrow_margin_realism": {"passed": False, "artifact_path": "reports/borrow-margin.json"},
    }

    clean_report = evaluate_hard_pre_live_upgrade_gates(complete)
    dirty_report = evaluate_hard_pre_live_upgrade_gates(dirty)

    assert clean_report.passed
    assert not dirty_report.passed
    reasons = {probe.name: probe.reason for probe in dirty_report.probes if not probe.passed}
    assert reasons["real_alpaca_fill_polling"] == "pre_live_upgrade_gate_missing"
    assert reasons["borrow_margin_realism"] == "pre_live_upgrade_gate_missing"
