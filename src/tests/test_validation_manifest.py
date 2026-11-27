import argparse
import json
from types import SimpleNamespace

from main import run_profile_app, run_release_checklist_app, run_release_rehearsal_app, run_validate_app, run_validation_profile_app
from src.app import TradingApplication
from src.config import MarketDataConfig, RuntimeConfig, StrategyConfig
from src.utils.profiling import BenchmarkTask, run_benchmark_suite
from src.validation import (
    ValidationEvidence,
    build_not_live_ready_report,
    build_readiness_index,
    default_cli_smoke_specs,
    default_performance_budgets,
    default_release_checklist,
    default_validation_manifest,
    default_validation_profiles,
    evaluate_paper_profile_validation,
    evaluate_performance_budgets,
)


def test_default_validation_manifest_covers_cli_smokes_and_performance_budgets():
    manifest = default_validation_manifest()
    check_ids = {check.check_id for check in manifest.checks}

    assert "unit_test_suite" in check_ids
    assert "alpaca_paper_order_lifecycle" in check_ids
    assert "paper_account_cleanup" in check_ids
    assert {spec.check_id for spec in default_cli_smoke_specs()} <= check_ids
    assert {
        "cli_smoke_validate",
        "cli_smoke_validate_profile",
        "cli_smoke_profile",
        "cli_smoke_release_checklist",
        "cli_smoke_paper_session_schedule",
        "cli_smoke_paper_broker_proof",
        "cli_smoke_paper_broker_schedule",
        "cli_smoke_paper_pilot",
    } <= check_ids
    assert {budget.check_id for budget in default_performance_budgets()} <= check_ids
    assert len(manifest.required_checks("paper_readiness")) > 20
    assert manifest.by_id()["unit_test_suite"].timeout_seconds >= 300


def test_default_validation_profiles_select_ci_and_paper_check_subsets():
    manifest = default_validation_manifest()
    profiles = {profile.name: profile for profile in default_validation_profiles(manifest)}

    assert {"smoke", "fast", "full", "paper-dry-run", "paper-submit", "release", "live-gate"} <= set(profiles)
    assert profiles["smoke"].check_ids == ("paper_profile_validation", "security_configuration")
    assert profiles["fast"].target == "release_readiness"
    assert "unit_test_suite" in profiles["fast"].check_ids
    assert "paper_session_schedule" in profiles["paper-dry-run"].check_ids
    assert "cli_smoke_paper_session_schedule" in profiles["paper-dry-run"].check_ids
    assert manifest.by_id()["paper_session_schedule"].command is not None
    assert "alpaca_paper_order_lifecycle" in profiles["paper-submit"].check_ids
    assert "paper_account_cleanup" in profiles["paper-submit"].check_ids
    assert set(profiles["release"].check_ids) == {check.check_id for check in manifest.required_checks("release_readiness")}
    assert profiles["full"].missing_check_ids(manifest) == ()
    assert profiles["paper-dry-run"].select_checks(manifest)


def test_readiness_index_tracks_missing_failed_and_passed_required_checks():
    evidence = (
        ValidationEvidence("unit_test_suite", "passed", artifact_path="reports/tests.txt"),
        ValidationEvidence("alpaca_data_connectivity", "failed", reason="auth_failed"),
    )

    index = build_readiness_index(evidence)

    assert not index.passed
    assert index.passed_required == 1
    assert "alpaca_data_connectivity" in {check.check_id for check in index.failed_required}
    assert "alpaca_paper_order_lifecycle" in {check.check_id for check in index.missing_required}
    assert 0 < index.readiness_score < 1


def test_performance_budget_report_marks_pass_fail_and_missing_benchmarks():
    report = run_benchmark_suite(
        [
            BenchmarkTask("indicator-calculation", lambda: sum(range(10)), category="indicator", repeats=1),
            BenchmarkTask("single-backtest", lambda: sum(range(10_000)), category="backtest_loop", repeats=1),
        ]
    )

    budget_report = evaluate_performance_budgets(report)
    evidence = {item.check_id: item for item in budget_report.evidence}

    assert evidence["perf_indicator_calculation"].status == "passed"
    assert evidence["perf_single_backtest"].status == "passed"
    assert evidence["perf_paper_session_planning"].status == "missing"
    assert budget_report.acceleration_plan.to_dict()["decisions"] == []


def test_not_live_ready_report_lists_missing_checks_and_next_commands():
    index = build_readiness_index((ValidationEvidence("unit_test_suite", "passed"),))

    report = build_not_live_ready_report(index)
    payload = report.to_dict()

    assert not payload["live_ready"]
    assert payload["status"] == "not_live_ready"
    assert "alpaca_data_connectivity" in payload["missing_checks"]
    assert any("pytest" in command for command in payload["next_commands"]) is False


def test_validate_cli_mode_writes_readiness_bundle(tmp_path):
    output = tmp_path / "validation-readiness.json"
    html_output = tmp_path / "readiness.html"
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "unit.json").write_text(
        json.dumps(ValidationEvidence("unit_test_suite", "passed").to_dict()),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        validation_output=str(output),
        evidence_dir=str(evidence_dir),
        readiness_html_output=str(html_output),
    )

    run_validate_app(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["readiness_index"]["passed"] is False
    assert payload["evidence_bundle"]["passed"]
    assert payload["action_plan"]["actions"]
    assert "unit_test_suite" not in payload["readiness_index"]["missing_required"]
    assert payload["not_live_ready"]["status"] == "not_live_ready"
    assert len(payload["cli_smoke_plan"]) == len(default_cli_smoke_specs())
    assert payload["performance_budgets"]
    assert payload["paper_profile_validation"]["passed"]
    assert payload["release_checklist"]["steps"]
    assert payload["readiness_html_path"] == str(html_output)
    assert "TradingBot Readiness" in html_output.read_text(encoding="utf-8")


def test_paper_profile_validation_proves_safe_profiles_and_blocks_unsafe_combinations():
    report = evaluate_paper_profile_validation()
    payload = report.to_dict()

    assert payload["passed"]
    assert set(payload["profile_results"]) == {
        "sample-data",
        "dry-run",
        "alpaca-data-only",
        "micro-notional",
        "full-paper-rehearsal",
    }
    assert payload["profile_results"]["micro-notional"]["session_options"]["risk_budget"]["max_session_notional"] == 25.0
    assert payload["profile_results"]["sample-data"]["daemon_options"]["interval_seconds"] == 0.0
    assert payload["profile_results"]["alpaca-data-only"]["daemon_options"]["data_parity_each_iteration"]
    assert payload["profile_results"]["micro-notional"]["daemon_options"]["monitor_each_iteration"]
    assert payload["unsafe_combination_results"]["micro_notional_live_url"]["blocked"]
    assert payload["unsafe_combination_results"]["full_rehearsal_missing_keys"]["blocked"]


def test_release_checklist_covers_core_validation_steps():
    checklist = default_release_checklist()
    step_names = {step.name for step in checklist.steps}

    assert {"fast_unit_suite", "validation_manifest", "performance_profile", "paper_dry_run"} <= step_names
    assert any(step.required is False for step in checklist.steps)


def test_release_checklist_cli_mode_writes_bundle(tmp_path):
    output = tmp_path / "release-validation-bundle.json"
    html_output = tmp_path / "release-readiness.html"
    release_candidate_output = tmp_path / "release-candidate-bundle.json"
    args = argparse.Namespace(
        release_output=str(output),
        evidence_dir=str(tmp_path / "missing-evidence"),
        readiness_html_output=str(html_output),
        release_candidate_output=str(release_candidate_output),
    )

    run_release_checklist_app(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["paper_profile_validation"]["passed"]
    assert payload["not_live_ready"]["status"] == "not_live_ready"
    assert payload["release_decision"]["decision"] == "blocked"
    assert payload["evidence_bundle"]["evidence"] == []
    assert payload["release_checklist"]["steps"]
    assert payload["readiness_html_path"] == str(html_output)
    assert payload["scheduled_paper_sessions"]["passed"] is False
    assert payload["rehearsal_report"]["passed"] is False
    assert payload["rehearsal_report"]["release_candidate_bundle"] == str(release_candidate_output)
    assert release_candidate_output.exists()
    assert "TradingBot Readiness" in html_output.read_text(encoding="utf-8")


def test_validate_profile_cli_mode_executes_profile_and_writes_evidence(tmp_path):
    output = tmp_path / "fast-validation.json"
    commands = []
    args = argparse.Namespace(
        validation_profile="fast",
        validation_profile_output=str(output),
        validation_run_id="run-fast-test",
        provider="sample",
        execution_mode="dry-run",
    )

    def fake_runner(command, timeout):
        commands.append((command, timeout))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    run_validation_profile_app(
        args,
        command_runner=fake_runner,
        artifact_exists=lambda path: True,
        performance_evidence_factory=lambda check_ids, app: tuple(
            ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
        ),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    evidence = {item["check_id"]: item for item in payload["evidence"]}
    assert payload["run_metadata"]["run_id"] == "run-fast-test"
    assert payload["run_metadata"]["provider"] == "sample"
    assert payload["run_metadata"]["broker_mode"] == "dry-run"
    assert "unit_test_suite" in evidence
    assert evidence["unit_test_suite"]["status"] == "passed"
    assert evidence["paper_profile_validation"]["status"] == "passed"
    assert evidence["security_configuration"]["status"] == "passed"
    assert evidence["perf_indicator_calculation"]["status"] == "passed"
    assert evidence["perf_single_backtest"]["status"] == "passed"
    assert commands


def test_validate_profile_cli_mode_adds_paper_dry_run_native_evidence(tmp_path):
    output = tmp_path / "paper-dry-run-validation.json"
    args = argparse.Namespace(
        validation_profile="paper-dry-run",
        validation_profile_output=str(output),
        validation_run_id="run-paper-dry-run-test",
        provider="sample",
        execution_mode="dry-run",
        paper_session_schedule_output=str(tmp_path / "missing-paper-session-schedule.json"),
    )

    run_validation_profile_app(
        args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
        performance_evidence_factory=lambda check_ids, app: tuple(
            ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
        ),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    evidence = {item["check_id"]: item for item in payload["evidence"]}
    assert evidence["paper_soak_tiers"]["status"] == "passed"
    assert evidence["paper_session_schedule"]["status"] == "passed"
    assert evidence["paper_session_schedule"]["metadata"]["passed"] is True
    assert evidence["cli_smoke_paper_session_schedule"]["status"] == "passed"
    assert evidence["daily_ops_acceptance"]["status"] == "passed"
    assert evidence["observability_acceptance"]["status"] == "passed"
    assert evidence["perf_paper_session_planning"]["status"] == "passed"
    assert evidence["cli_smoke_paper_session"]["status"] == "passed"
    assert evidence["cli_smoke_paper_soak"]["status"] == "passed"


def test_validate_profile_paper_dry_run_uses_schedule_artifact_truth(tmp_path):
    output = tmp_path / "paper-dry-run-validation.json"
    schedule_artifact = tmp_path / "paper-session-schedule.json"
    schedule_artifact.write_text(
        json.dumps(
            {
                "passed": False,
                "active_window": None,
                "checks": [{"name": "active_window", "passed": False, "reason": "no_active_paper_session_window"}],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        validation_profile="paper-dry-run",
        validation_profile_output=str(output),
        validation_run_id="run-paper-dry-run-artifact-test",
        provider="sample",
        execution_mode="dry-run",
        paper_session_schedule_output=str(schedule_artifact),
    )

    run_validation_profile_app(
        args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
        performance_evidence_factory=lambda check_ids, app: tuple(
            ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
        ),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    evidence = {item["check_id"]: item for item in payload["evidence"]}
    assert evidence["paper_session_schedule"]["status"] == "failed"
    assert evidence["paper_session_schedule"]["reason"] == "no_active_paper_session_window"
    assert evidence["paper_session_schedule"]["artifact_path"] == str(schedule_artifact)
    assert evidence["paper_session_schedule"]["metadata"]["active_window"] is None


def test_validate_profile_paper_submit_uses_broker_proof_artifact_truth(tmp_path):
    output = tmp_path / "paper-submit-validation.json"
    proof = tmp_path / "alpaca-paper-broker-proof.json"
    proof.write_text(
        json.dumps(
            {
                "passed": False,
                "submit_allowed": False,
                "submitted": False,
                "reason": "market_session_not_tradable",
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        validation_profile="paper-submit",
        validation_profile_output=str(output),
        validation_run_id="run-paper-submit-test",
        provider="sample",
        execution_mode="dry-run",
        paper_proof_output=str(proof),
    )

    run_validation_profile_app(
        args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
        performance_evidence_factory=lambda check_ids, app: tuple(
            ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
        ),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    evidence = {item["check_id"]: item for item in payload["evidence"]}
    assert evidence["alpaca_paper_order_lifecycle"]["status"] == "failed"
    assert evidence["alpaca_paper_order_lifecycle"]["reason"] == "market_session_not_tradable"
    assert evidence["alpaca_paper_order_lifecycle"]["metadata"]["paper_broker_proof"]["submitted"] is False
    assert evidence["broker_account_parity"]["status"] == "failed"
    assert evidence["broker_account_parity"]["reason"] == "paper_broker_proof_not_submitted"
    assert evidence["paper_account_parity"]["status"] == "failed"
    assert evidence["paper_account_parity"]["reason"] == "paper_broker_proof_not_submitted"
    assert evidence["real_alpaca_fill_polling"]["status"] == "failed"
    assert evidence["real_alpaca_fill_polling"]["reason"] == "paper_broker_proof_not_submitted"


def test_validate_profile_paper_submit_uses_cleanup_artifact_truth(tmp_path):
    output = tmp_path / "paper-submit-validation.json"
    proof = tmp_path / "alpaca-paper-broker-proof.json"
    cleanup = tmp_path / "paper-cleanup-report.json"
    proof.write_text(
        json.dumps(
            {
                "passed": True,
                "submit_allowed": True,
                "submitted": True,
                "cancelled": True,
                "reason": "passed",
                "account_snapshot": {"cash": 1000, "equity": 1000},
                "post_account_snapshot": {"cash": 1000, "equity": 1000, "account_blocked": False, "trading_blocked": False},
                "open_orders_after": [],
                "polled_execution_reports": [{"order_id": "local-1", "status": "CANCELLED"}],
                "probes": [
                    {
                        "name": "fill_polling_completed",
                        "passed": True,
                        "reason": "passed",
                        "evidence": {"source": "broker_poll_execution_reports", "reports": 1},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cleanup.write_text(
        json.dumps(
            {
                "submit_requested": True,
                "attempted": False,
                "submitted": False,
                "positions_seen": [{"symbol": "SPY", "quantity": 0.033521, "market_value": 25.0, "raw": {"id": "<redacted>"}}],
                "planned_orders": [{"symbol": "SPY", "side": "SELL", "quantity": 0.033521, "id": "order-1"}],
                "submitted_orders": [],
                "reconciliation_clean": None,
                "polled_execution_reports": 0,
                "submission_guard": {"reason": "market_session_not_tradable"},
                "reason": "market_session_not_tradable",
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        validation_profile="paper-submit",
        validation_profile_output=str(output),
        validation_run_id="run-paper-submit-cleanup-test",
        provider="sample",
        execution_mode="dry-run",
        paper_proof_output=str(proof),
        paper_cleanup_output=str(cleanup),
        paper_session_schedule_output=str(tmp_path / "missing-paper-session-schedule.json"),
    )

    run_validation_profile_app(
        args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
        performance_evidence_factory=lambda check_ids, app: tuple(
            ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
        ),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    evidence = {item["check_id"]: item for item in payload["evidence"]}
    cleanup_evidence = evidence["paper_account_cleanup"]
    assert cleanup_evidence["status"] == "failed"
    assert cleanup_evidence["reason"] == "market_session_not_tradable"
    assert cleanup_evidence["artifact_path"] == str(cleanup)
    assert cleanup_evidence["metadata"]["positions_seen"] == 1
    assert cleanup_evidence["metadata"]["planned_orders"] == 1
    assert cleanup_evidence["metadata"]["position_summary"] == [{"symbol": "SPY", "quantity": 0.033521, "market_value": 25.0}]


def test_validate_profile_paper_submit_passes_cleanup_when_account_is_flat(tmp_path):
    output = tmp_path / "paper-submit-validation.json"
    cleanup = tmp_path / "paper-cleanup-report.json"
    cleanup.write_text(
        json.dumps(
            {
                "submit_requested": False,
                "attempted": False,
                "submitted": False,
                "positions_seen": [],
                "planned_orders": [],
                "submitted_orders": [],
                "reconciliation_clean": None,
                "reason": "preview_only",
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        validation_profile="paper-submit",
        validation_profile_output=str(output),
        validation_run_id="run-paper-submit-flat-cleanup-test",
        provider="sample",
        execution_mode="dry-run",
        paper_proof_output=str(tmp_path / "missing-proof.json"),
        paper_cleanup_output=str(cleanup),
        paper_session_schedule_output=str(tmp_path / "missing-paper-session-schedule.json"),
    )

    run_validation_profile_app(
        args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
        performance_evidence_factory=lambda check_ids, app: tuple(
            ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
        ),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    evidence = {item["check_id"]: item for item in payload["evidence"]}
    assert evidence["paper_account_cleanup"]["status"] == "passed"
    assert evidence["paper_account_cleanup"]["reason"] == "passed"
    assert evidence["paper_account_cleanup"]["metadata"]["positions_seen"] == 0


def test_validate_profile_can_consume_existing_paper_submit_artifact_without_commands(tmp_path):
    output = tmp_path / "paper-submit-existing-validation.json"
    proof = tmp_path / "alpaca-paper-broker-proof.json"
    proof.write_text(
        json.dumps(
            {
                "passed": True,
                "submit_allowed": True,
                "submitted": True,
                "cancelled": True,
                "reason": "passed",
                "account_snapshot": {"cash": 1000, "equity": 1000, "raw": {"account_number": "<redacted>"}},
                "post_account_snapshot": {"cash": 1000, "equity": 1000, "account_blocked": False, "trading_blocked": False},
                "open_orders_after": [],
                "polled_execution_reports": [{"order_id": "local-1", "status": "CANCELLED"}],
                "probes": [
                    {
                        "name": "fill_polling_completed",
                        "passed": True,
                        "reason": "passed",
                        "evidence": {"source": "broker_poll_execution_reports", "reports": 1},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    commands = []
    args = argparse.Namespace(
        validation_profile="paper-submit",
        validation_profile_output=str(output),
        validation_run_id="run-paper-submit-existing-test",
        provider="sample",
        execution_mode="dry-run",
        paper_proof_output=str(proof),
        paper_session_schedule_output=str(tmp_path / "missing-paper-session-schedule.json"),
        consume_existing_evidence=True,
    )

    run_validation_profile_app(
        args,
        command_runner=lambda command, timeout: commands.append((command, timeout)),
        artifact_exists=lambda path: True,
        performance_evidence_factory=lambda check_ids, app: tuple(
            ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
        ),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    evidence = {item["check_id"]: item for item in payload["evidence"]}
    assert commands == []
    assert evidence["alpaca_paper_order_lifecycle"]["status"] == "passed"
    assert evidence["broker_account_parity"]["status"] == "passed"
    assert evidence["paper_account_parity"]["status"] == "passed"
    assert evidence["real_alpaca_fill_polling"]["status"] == "passed"
    assert evidence["alpaca_data_connectivity"]["status"] == "skipped"
    assert evidence["alpaca_data_connectivity"]["reason"] == "consume_existing_evidence"


def test_validate_profile_cli_mode_adds_release_native_evidence(tmp_path):
    output = tmp_path / "release-validation.json"
    args = argparse.Namespace(
        validation_profile="release",
        validation_profile_output=str(output),
        validation_run_id="run-release-test",
        provider="sample",
        execution_mode="dry-run",
    )

    run_validation_profile_app(
        args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    evidence = {item["check_id"]: item for item in payload["evidence"]}
    assert evidence["unit_test_suite"]["status"] == "passed"
    assert evidence["failure_injection_suite"]["status"] == "passed"
    assert evidence["data_quality_torture"]["status"] == "passed"
    assert evidence["backtester_differential"]["status"] == "passed"
    assert evidence["optimizer_validation"]["status"] == "passed"
    assert evidence["daily_ops_acceptance"]["status"] == "passed"
    assert evidence["observability_acceptance"]["status"] == "passed"
    assert evidence["security_configuration"]["status"] == "passed"
    assert evidence["deployment_rehearsal"]["status"] == "passed"
    assert evidence["golden_artifacts"]["status"] == "passed"
    assert evidence["paper_profile_validation"]["status"] == "passed"
    assert evidence["release_checklist_bundle"]["status"] == "passed"


def test_release_checklist_consumes_release_and_schedule_evidence_for_rehearsal(tmp_path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    release_output = evidence_dir / "release-validation.json"
    paper_output = evidence_dir / "paper-dry-run-validation.json"
    release_args = argparse.Namespace(
        validation_profile="release",
        validation_profile_output=str(release_output),
        validation_run_id="run-release-test",
        provider="sample",
        execution_mode="dry-run",
    )
    paper_args = argparse.Namespace(
        validation_profile="paper-dry-run",
        validation_profile_output=str(paper_output),
        validation_run_id="run-paper-test",
        provider="sample",
        execution_mode="dry-run",
        paper_session_schedule_output=str(tmp_path / "missing-release-paper-session-schedule.json"),
    )
    fake_performance = lambda check_ids, app: tuple(
        ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
    )

    run_validation_profile_app(
        release_args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
    )
    run_validation_profile_app(
        paper_args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
        performance_evidence_factory=fake_performance,
    )
    output = tmp_path / "release-validation-bundle.json"
    html_output = tmp_path / "release-readiness.html"
    release_candidate_output = tmp_path / "release-candidate-bundle.json"

    run_release_checklist_app(
        argparse.Namespace(
            release_output=str(output),
            evidence_dir=str(evidence_dir),
            readiness_html_output=str(html_output),
            release_candidate_output=str(release_candidate_output),
        )
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["release_decision"]["decision"] == "release_ready"
    assert payload["scheduled_paper_sessions"]["passed"] is True
    assert payload["rehearsal_report"]["passed"] is True
    assert payload["live_unlock_blockers"]["status"] == "live_locked"
    assert "broker_statement_ingestion" in payload["live_unlock_blockers"]["blocked_gate_names"]


def test_release_rehearsal_cli_mode_generates_profiles_and_candidate_bundle(tmp_path):
    evidence_dir = tmp_path / "rehearsal-evidence"
    summary_output = tmp_path / "rehearsal-summary.json"
    release_output = tmp_path / "release-validation-bundle.json"
    html_output = tmp_path / "release-readiness.html"
    release_candidate_output = tmp_path / "release-candidate-bundle.json"
    args = argparse.Namespace(
        rehearsal_evidence_dir=str(evidence_dir),
        rehearsal_output=str(summary_output),
        release_output=str(release_output),
        readiness_html_output=str(html_output),
        release_candidate_output=str(release_candidate_output),
        validation_run_id="run-rehearsal-test",
        provider="sample",
        execution_mode="dry-run",
        paper_session_schedule_output=str(tmp_path / "missing-rehearsal-paper-session-schedule.json"),
    )

    run_release_rehearsal_app(
        args,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: True,
        performance_evidence_factory=lambda check_ids, app: tuple(
            ValidationEvidence(check_id, "passed", reason="passed") for check_id in check_ids
        ),
    )

    summary = json.loads(summary_output.read_text(encoding="utf-8"))
    candidate = json.loads(release_candidate_output.read_text(encoding="utf-8"))
    assert (evidence_dir / "release-validation.json").exists()
    assert (evidence_dir / "paper-dry-run-validation.json").exists()
    assert summary["release_decision"]["decision"] == "release_ready"
    assert summary["rehearsal_report"]["passed"] is True
    assert candidate["rehearsal_report"]["passed"] is True
    assert summary["not_live_ready"]["status"] == "not_live_ready"
    assert summary["live_unlock_blockers"]["status"] == "live_locked"
    assert summary["live_unlock_blockers"]["live_unlock_allowed"] is False


def test_profile_cli_mode_writes_budget_report(tmp_path):
    output = tmp_path / "profiling-report.json"
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )
    args = argparse.Namespace(
        profiling_output=str(output),
        profiling_repeats=1,
        store_dir=str(tmp_path / "runs"),
    )

    run_profile_app(app, args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "benchmark_report" in payload
    assert "acceleration_plan" in payload
    assert {item["check_id"] for item in payload["evidence"]} >= {"perf_single_backtest", "perf_paper_session_planning"}
