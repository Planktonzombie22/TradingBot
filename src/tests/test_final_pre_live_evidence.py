import json

from src.validation import (
    artifact_digest,
    build_deployment_environment_evidence_report,
    build_drill_count_report,
    build_final_pre_live_evidence_report,
    build_first_live_micro_order_authorization_report,
    build_live_candidate_strategy_evidence_report,
    build_live_preview_block_proof_report,
    build_operator_emergency_capability_report,
    build_paper_trading_day_evidence_report,
    build_promoted_portfolio_submit_exit_report,
    build_release_candidate_evidence_bundle_report,
    build_secret_leakage_evidence_report,
    build_validation_profile_gate_report,
    build_written_pre_live_review_report,
    pre_live_gate,
    write_pre_live_evidence_report,
)


def test_validation_profile_gate_requires_fast_paper_release_and_live_gate_profiles():
    report = build_validation_profile_gate_report(
        [
            {"profile": "fast", "status": "passed", "stale": False},
            {"profile": "paper-dry-run", "status": "passed", "stale": False},
            {"profile": "paper-submit", "status": "passed", "stale": False},
            {"profile": "release", "status": "passed", "stale": False},
            {"profile": "live-gate", "status": "failed", "stale": False},
        ]
    )

    assert report.passed is False
    assert report.missing_profiles == ("live-gate",)


def test_release_candidate_bundle_requires_code_config_artifact_digests_and_readiness_html(tmp_path):
    artifact = tmp_path / "bundle.json"
    artifact.write_text('{"passed": true}', encoding="utf-8")
    report = build_release_candidate_evidence_bundle_report(
        "abc123",
        "cfg456",
        {str(artifact): artifact_digest(artifact)},
        "reports/readiness.html",
    )
    payload = json.loads(write_pre_live_evidence_report(report, tmp_path / "candidate.json").read_text(encoding="utf-8"))

    assert payload["passed"] is True
    assert payload["artifact_digests"][str(artifact)]


def test_paper_days_portfolio_cycles_and_drills_require_minimum_clean_counts():
    paper_days = build_paper_trading_day_evidence_report(29)
    portfolio = build_promoted_portfolio_submit_exit_report(10, ["SPY", "QQQ"])
    recovery = build_drill_count_report("restart_recovery", 5)
    outage = build_drill_count_report("broker_outage", 4)

    assert paper_days.passed is False
    assert paper_days.to_dict()["remaining_days"] == 1
    assert portfolio.passed is True
    assert recovery.passed is True
    assert outage.passed is False


def test_strategy_deployment_secret_preview_capability_and_review_gates():
    strategies = build_live_candidate_strategy_evidence_report(
        [
            {
                "strategy": "buyHold",
                "paper_scorecard_stable": True,
                "slippage_stable": True,
                "drift_stable": True,
                "pnl_stable": True,
                "rejects_clean": True,
                "missed_fills_clean": True,
                "benchmark_comparison_passed": True,
                "walk_forward_current": True,
                "holdout_current": True,
                "cost_stress_current": True,
                "market_cluster_current": True,
            },
            {"strategy": "cycle", "paper_scorecard_stable": True},
        ]
    )
    deployment = build_deployment_environment_evidence_report(2, 1, missed_artifacts=0)
    secrets = build_secret_leakage_evidence_report([])
    preview = build_live_preview_block_proof_report(
        {"symbol": "SPY", "side": "BUY", "notional": 5.0},
        preview_created=True,
        live_submit_blocked=True,
        final_approval_present=False,
    )
    operator = build_operator_emergency_capability_report(True, True, True, False)
    review = build_written_pre_live_review_report(
        {
            "strategy": "buyHold",
            "rationale": "stable paper evidence",
            "max_live_notional": 5,
            "stop_conditions": "any mismatch",
            "rollback_procedure": "lock live mode and flatten",
        },
        approved=True,
        stored=True,
    )

    assert strategies.passed is False
    assert strategies.blockers[0]["strategy"] == "cycle"
    assert deployment.passed is True
    assert secrets.passed is True
    assert preview.passed is True
    assert operator.passed is False
    assert review.passed is True


def test_final_pre_live_report_blocks_micro_order_until_every_prior_gate_passes():
    paper_days = build_paper_trading_day_evidence_report(30)
    live_preview = build_live_preview_block_proof_report({"symbol": "SPY", "notional": 5}, True, True)
    review = build_written_pre_live_review_report(
        {
            "strategy": "buyHold",
            "rationale": "passed",
            "max_live_notional": 5,
            "stop_conditions": "lockout",
            "rollback_procedure": "flatten",
        },
        approved=False,
        stored=True,
    )
    final = build_final_pre_live_evidence_report(
        [
            pre_live_gate("paper_days", paper_days),
            pre_live_gate("live_preview_block", live_preview),
            pre_live_gate("written_review", review),
        ]
    )
    blocked_micro = build_first_live_micro_order_authorization_report(
        pre_live_gates_passed=final.passed,
        tiny_capital=True,
        immediate_reconciliation=True,
        immediate_monitor=True,
        automatic_lockout=True,
    )

    assert final.passed is False
    assert final.blockers[0].name == "written_review"
    assert blocked_micro.authorized is False


def test_first_live_micro_order_authorization_only_passes_after_all_controls_are_enabled():
    report = build_first_live_micro_order_authorization_report(
        pre_live_gates_passed=True,
        tiny_capital=True,
        immediate_reconciliation=True,
        immediate_monitor=True,
        automatic_lockout=True,
    )

    assert report.authorized is True
    assert report.to_dict()["passed"] is True
