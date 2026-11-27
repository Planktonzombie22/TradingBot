from datetime import datetime, timedelta, timezone
import json
import os

from src.operations import (
    build_paper_daemon_daily_summary_report,
    build_paper_daemon_activation_checklist_report,
    build_paper_daemon_flatten_drill_report,
    build_paper_daemon_notification_report,
    build_paper_daemon_notional_decision_report,
    build_paper_daemon_recovery_report,
    build_paper_daemon_retention_plan,
    build_paper_daemon_restart_drill_report,
    build_paper_daemon_soak_readiness_rollup_report,
    build_paper_daemon_supervised_soak_report,
    build_paper_daemon_window_capture_plan_report,
    build_paper_exposure_acknowledgement_template_report,
    build_paper_position_stewardship_report,
    write_paper_daemon_ops_report,
)
from main import build_parser, run_paper_daemon_ops_app


def test_paper_daemon_recovery_report_flags_stale_running_state_and_lock(tmp_path):
    now = datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc)
    state_path = tmp_path / "state.json"
    lock_path = tmp_path / "paper-daemon.lock"
    state_path.write_text(
        json.dumps(
            {
                "status": "running",
                "iteration": 4,
                "last_heartbeat_at": (now - timedelta(minutes=45)).isoformat(),
                "last_reason": "daemon_started",
            }
        ),
        encoding="utf-8",
    )
    lock_path.write_text(
        json.dumps(
            {
                "token": "prior-daemon",
                "acquired_at": (now - timedelta(minutes=45)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    report = build_paper_daemon_recovery_report(
        state_path,
        lock_path,
        now=now,
        stale_after_seconds=600,
    )

    assert not report.passed
    assert report.recovery_required
    assert report.stale_heartbeat
    assert report.unresolved_running_state
    assert report.lock_active
    assert report.lock_stale
    assert report.recommended_action == "review_prior_state_then_clear_stale_lock"


def test_paper_daemon_recovery_report_allows_clean_completed_state(tmp_path):
    now = datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc)
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "iteration": 2,
                "last_heartbeat_at": now.isoformat(),
                "last_reason": "max_iterations_completed",
            }
        ),
        encoding="utf-8",
    )

    report = build_paper_daemon_recovery_report(
        state_path,
        tmp_path / "missing.lock",
        now=now,
        stale_after_seconds=600,
    )

    assert report.passed
    assert not report.recovery_required
    assert report.recommended_action == "resume_allowed_after_operator_review"


def test_paper_daemon_daily_summary_counts_iterations_and_artifacts():
    payload = {
        "artifact_path": "runs/state.json",
        "state": {"status": "completed", "last_reason": "max_iterations_completed"},
        "iterations": [
            {
                "status": "skipped",
                "reason": "no_active_paper_session_window",
                "passed": True,
                "submitted": False,
                "artifact_paths": ["runs/schedule-1.json"],
            },
            {
                "status": "completed",
                "reason": "passed",
                "passed": True,
                "submitted": True,
                "active_window": "market_open",
                "cleanup_planned_orders": 1,
                "cleanup_submitted_orders": 0,
                "monitor_passed": True,
                "artifact_paths": ["runs/schedule-2.json", "runs/session-2.json"],
            },
            {
                "status": "completed",
                "reason": "paper_session_schedule_failed",
                "passed": False,
                "submitted": False,
                "active_window": "market_close",
                "cleanup_planned_orders": 2,
                "monitor_passed": False,
                "monitor_stale_open_orders": 1,
                "monitor_position_mismatches": 1,
                "data_parity_passed": False,
                "data_parity_failed_checks": 2,
                "artifact_paths": ["runs/schedule-3.json"],
            },
        ],
    }

    report = build_paper_daemon_daily_summary_report(payload, report_date="2026-01-05")

    assert not report.passed
    assert report.total_iterations == 3
    assert report.passed_iterations == 2
    assert report.failed_iterations == 1
    assert report.skipped_iterations == 1
    assert report.submitted_iterations == 1
    assert report.cleanup_planned_orders == 3
    assert report.cleanup_submitted_orders == 0
    assert report.monitor_failed_iterations == 1
    assert report.monitor_stale_open_orders == 1
    assert report.monitor_position_mismatches == 1
    assert report.data_parity_failed_iterations == 1
    assert report.data_parity_failed_checks == 2
    assert report.active_windows == ("market_open", "market_close")
    assert "runs/session-2.json" in report.artifact_paths
    assert "stale_open_orders_present" in report.warnings
    assert "position_mismatches_present" in report.warnings
    assert "data_parity_failures_present" in report.warnings
    assert report.recommended_action == "review_failures_before_next_daemon_start"


def test_paper_daemon_notification_report_routes_kill_switch_and_recovery_events():
    recovery = {
        "stale_heartbeat": True,
        "heartbeat_age_seconds": 1_200,
        "lock_active": True,
        "lock_stale": True,
        "lock_path": "runs/paper-daemon.lock",
    }

    report = build_paper_daemon_notification_report(
        {"status": "kill_switch_active", "last_reason": "operator_requested_stop"},
        recovery_report=recovery,
        sinks=("local", "webhook"),
    )

    event_types = {event.event_type for event in report.events}
    assert not report.passed
    assert report.sinks == ("local", "webhook")
    assert {"kill_switch_active", "stale_heartbeat", "daemon_lock_active"}.issubset(event_types)


def test_paper_daemon_retention_plan_is_non_destructive_and_preserves_recent(tmp_path):
    now = datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc)
    old_file = tmp_path / "old.json"
    recent_file = tmp_path / "recent.json"
    old_file.write_text("{}", encoding="utf-8")
    recent_file.write_text("{}", encoding="utf-8")
    old_timestamp = (now - timedelta(days=45)).timestamp()
    recent_timestamp = (now - timedelta(days=2)).timestamp()
    os.utime(old_file, (old_timestamp, old_timestamp))
    os.utime(recent_file, (recent_timestamp, recent_timestamp))

    plan = build_paper_daemon_retention_plan(
        [old_file, recent_file, tmp_path / "missing.json"],
        now=now,
        keep_days=30,
        preserve_recent=1,
    )

    decisions = {candidate.path: candidate for candidate in plan.candidates}
    assert plan.passed
    assert decisions[str(recent_file)].action == "keep"
    assert decisions[str(old_file)].action == "delete"
    assert decisions[str(tmp_path / "missing.json")].action == "ignore"
    assert old_file.exists()


def test_paper_daemon_notional_decision_downshifts_on_monitor_and_cleanup_triggers():
    report = build_paper_daemon_notional_decision_report(
        {
            "daemon_status": "completed",
            "passed_iterations": 8,
            "submitted_iterations": 4,
            "failed_iterations": 1,
            "cleanup_planned_orders": 2,
            "cleanup_submitted_orders": 0,
            "monitor_failed_iterations": 1,
            "monitor_stale_open_orders": 1,
            "monitor_position_mismatches": 1,
            "data_parity_failed_iterations": 1,
            "data_parity_failed_checks": 2,
            "warnings": ["stale_open_orders_present"],
        },
        current_notional=250.0,
    )

    assert not report.passed
    assert report.action == "downshift"
    assert report.recommended_notional == 100.0
    assert report.triggers == (
        "failed_daemon_iteration",
        "failed_monitor",
        "stale_open_order",
        "position_mismatch",
        "data_parity_failed",
        "data_parity_check_failed",
        "cleanup_review_required",
    )


def test_paper_daemon_notional_decision_holds_without_submitted_clean_evidence():
    report = build_paper_daemon_notional_decision_report(
        {
            "daemon_status": "completed",
            "passed_iterations": 12,
            "submitted_iterations": 0,
            "failed_iterations": 0,
            "warnings": ["no_orders_submitted"],
        },
        current_notional=25.0,
    )

    assert report.passed
    assert report.action == "hold"
    assert report.recommended_notional == 25.0
    assert report.reason == "requires_clean_submitted_daemon_iterations"


def test_paper_daemon_notional_decision_escalates_after_clean_submitted_iterations():
    report = build_paper_daemon_notional_decision_report(
        {
            "daemon_status": "completed",
            "passed_iterations": 11,
            "submitted_iterations": 3,
            "failed_iterations": 0,
            "monitor_failed_iterations": 0,
            "cleanup_planned_orders": 0,
            "warnings": [],
        },
        current_notional=25.0,
        required_clean_iterations=10,
    )

    assert report.passed
    assert report.action == "escalate"
    assert report.recommended_notional == 50.0
    assert report.reason == "clean_daemon_evidence_supports_next_tier"


def test_paper_daemon_restart_drill_report_passes_clean_evidence_pack():
    report = build_paper_daemon_restart_drill_report(
        {
            "drills": [
                {
                    "name": "clean_stop_resume",
                    "stopped_cleanly": True,
                    "resumed": True,
                    "recovery_passed": True,
                },
                {
                    "name": "stale_lock_replacement",
                    "stale_lock_detected": True,
                    "stale_lock_replaced": True,
                    "resumed": True,
                    "recovery_passed": True,
                },
                {
                    "name": "kill_switch_resume",
                    "kill_switch_written": True,
                    "blocked_start": True,
                    "kill_switch_cleared": True,
                    "resumed_after_clear": True,
                },
                {"name": "duplicate_client_order_id_guard", "guard_enabled": True},
            ],
            "order_artifacts": [
                {"submitted_orders": [{"client_order_id": "daemon-1"}]},
                {"submitted_orders": [{"client_order_id": "daemon-2"}]},
            ],
        }
    )

    assert report.passed
    assert report.missing_drills == ()
    assert report.duplicate_client_order_ids == ()


def test_paper_daemon_restart_drill_report_blocks_unguarded_duplicate_client_ids():
    report = build_paper_daemon_restart_drill_report(
        {
            "drills": [
                {
                    "name": "clean_stop_resume",
                    "stopped_cleanly": True,
                    "resumed": True,
                    "recovery_passed": True,
                },
                {
                    "name": "stale_lock_replacement",
                    "stale_lock_detected": True,
                    "stale_lock_replaced": True,
                    "resumed": True,
                    "recovery_passed": True,
                },
                {
                    "name": "kill_switch_resume",
                    "kill_switch_written": True,
                    "blocked_start": True,
                    "kill_switch_cleared": True,
                    "resumed_after_clear": True,
                },
                {"name": "duplicate_client_order_id_guard", "guard_enabled": True},
            ],
            "order_artifacts": [
                {"submitted_orders": [{"client_order_id": "dup-1", "status": "FILLED"}]},
                {"submitted_orders": [{"client_order_id": "dup-1", "status": "FILLED"}]},
            ],
        }
    )

    duplicate_drill = {drill.name: drill for drill in report.drills}["duplicate_client_order_id_guard"]
    assert not report.passed
    assert report.missing_drills == ("duplicate_client_order_id_guard",)
    assert report.duplicate_client_order_ids == ("dup-1",)
    assert duplicate_drill.reason == "duplicate_client_order_ids_detected"


def test_paper_daemon_activation_checklist_passes_with_clean_submitted_evidence():
    daemon = {
        "state": {"status": "completed", "last_reason": "max_iterations_completed"},
        "iterations": [
            {
                "status": "completed",
                "passed": True,
                "submitted": True,
                "monitor_passed": True,
                "data_parity_passed": True,
            }
        ],
    }
    kill_proof = {
        "passed": True,
        "stopped_by_kill_switch": True,
        "state": {"status": "kill_switch_active", "last_reason": "kill_switch_present_before_start"},
    }
    command_center = {
        "passed": True,
        "daemon": {"heartbeat_state": "fresh", "kill_switch_active": False},
        "paper": {"observed_positions": 0, "observed_notional": 0.0},
    }

    report = build_paper_daemon_activation_checklist_report(
        daemon,
        command_center=command_center,
        kill_switch_proof=kill_proof,
    )

    assert report.passed is True
    assert report.blockers == ()
    assert report.recommended_action == "ready_for_guarded_unattended_paper_soak"


def test_paper_daemon_activation_checklist_blocks_off_hours_monitor_mismatch():
    daemon = {
        "state": {"status": "completed", "last_reason": "max_iterations_completed"},
        "iterations": [
            {
                "status": "skipped",
                "passed": False,
                "submitted": False,
                "monitor_passed": False,
                "monitor_position_mismatches": 2,
                "cleanup_planned_orders": 2,
                "cleanup_submitted_orders": 0,
                "data_parity_passed": True,
            }
        ],
    }
    kill_proof = {"passed": True, "stopped_by_kill_switch": True}
    command_center = {
        "passed": False,
        "daemon": {"heartbeat_state": "fresh", "kill_switch_active": False},
        "paper": {"observed_positions": 2, "observed_notional": 25.18},
    }

    report = build_paper_daemon_activation_checklist_report(
        daemon,
        command_center=command_center,
        kill_switch_proof=kill_proof,
    )

    assert report.passed is False
    assert "active_submit_observed" in report.blockers
    assert "broker_monitor_clean" in report.blockers
    assert "cleanup_review_resolved" in report.blockers
    assert report.recommended_action == "flatten_or_acknowledge_existing_paper_exposure_before_next_submit"


def test_paper_daemon_activation_checklist_allows_bounded_acknowledged_exposure_but_still_requires_submit():
    daemon = {
        "state": {"status": "completed", "last_reason": "max_iterations_completed"},
        "iterations": [
            {
                "status": "skipped",
                "passed": False,
                "submitted": False,
                "monitor_passed": False,
                "monitor_position_mismatches": 2,
                "cleanup_planned_orders": 2,
                "cleanup_submitted_orders": 0,
                "data_parity_passed": True,
            }
        ],
    }
    command_center = {
        "passed": False,
        "daemon": {"heartbeat_state": "fresh", "kill_switch_active": False},
        "paper": {"observed_positions": 2, "observed_notional": 25.18},
    }
    acknowledgement = {
        "acknowledged": True,
        "max_positions": 2,
        "max_notional": 30.0,
        "expires_at": "2026-01-06T00:00:00+00:00",
    }

    report = build_paper_daemon_activation_checklist_report(
        daemon,
        command_center=command_center,
        kill_switch_proof={"passed": True, "stopped_by_kill_switch": True},
        acknowledged_exposure=acknowledgement,
        now=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )

    assert report.passed is False
    assert report.checks["broker_monitor_clean"] is True
    assert report.checks["cleanup_review_resolved"] is True
    assert report.checks["paper_exposure_acknowledged"] is True
    assert report.checks["active_submit_observed"] is False
    assert report.blockers == ("active_submit_observed",)
    assert report.recommended_action == "run_micro_notional_daemon_during_active_submit_window"


def test_paper_daemon_activation_checklist_uses_cleanup_evidence_reason():
    daemon = {
        "state": {"status": "completed", "last_reason": "max_iterations_completed"},
        "iterations": [
            {
                "status": "skipped",
                "submitted": False,
                "monitor_position_mismatches": 2,
                "cleanup_planned_orders": 2,
                "cleanup_submitted_orders": 0,
            }
        ],
    }
    cleanup = {
        "submitted": False,
        "attempted": False,
        "reason": "market_session_not_tradable",
        "planned_orders": [{"symbol": "DIA"}, {"symbol": "SPY"}],
        "artifact_path": "reports/cleanup.json",
    }

    report = build_paper_daemon_activation_checklist_report(
        daemon,
        cleanup_evidence=cleanup,
        command_center={"daemon": {"heartbeat_state": "fresh", "kill_switch_active": False}, "paper": {"observed_positions": 2, "observed_notional": 25.0}},
        kill_switch_proof={"passed": True, "stopped_by_kill_switch": True},
    )

    assert report.checks["cleanup_review_resolved"] is False
    assert report.evidence["latest_cleanup_reason"] == "market_session_not_tradable"
    assert report.recommended_action == "run_guarded_cleanup_during_regular_session_or_provide_operator_acknowledgement"


def test_paper_daemon_activation_checklist_accepts_fresh_passing_command_center_monitor():
    daemon = {
        "state": {"status": "completed", "last_reason": "max_iterations_completed"},
        "iterations": [
            {
                "status": "skipped",
                "submitted": False,
                "monitor_passed": False,
                "monitor_position_mismatches": 2,
                "cleanup_planned_orders": 2,
                "cleanup_submitted_orders": 0,
            }
        ],
    }
    cleanup = {
        "submitted": True,
        "submitted_orders": [{"symbol": "DIA", "side": "SELL", "quantity": 0.02, "status": "FILLED"}],
        "reconciliation_clean": True,
        "reason": "flatten_orders_submitted",
    }
    command_center = {
        "passed": True,
        "daemon": {"heartbeat_state": "fresh", "kill_switch_active": False},
        "paper": {"monitor_status": "passed", "observed_positions": 0, "observed_notional": 0.0},
    }

    report = build_paper_daemon_activation_checklist_report(
        daemon,
        cleanup_evidence=cleanup,
        command_center=command_center,
        kill_switch_proof={"passed": True, "stopped_by_kill_switch": True},
        require_submitted_iteration=False,
    )

    assert report.checks["broker_monitor_clean"] is True
    assert report.checks["cleanup_review_resolved"] is True
    assert report.checks["paper_exposure_acknowledged"] is True
    assert report.blockers == ()
    assert report.warnings == ()


def test_paper_daemon_activation_checklist_rejects_expired_exposure_acknowledgement():
    daemon = {
        "state": {"status": "completed", "last_reason": "max_iterations_completed"},
        "iterations": [{"status": "completed", "passed": True, "submitted": True, "monitor_position_mismatches": 1}],
    }
    command_center = {
        "daemon": {"heartbeat_state": "fresh", "kill_switch_active": False},
        "paper": {"observed_positions": 1, "observed_notional": 10.0},
    }

    report = build_paper_daemon_activation_checklist_report(
        daemon,
        command_center=command_center,
        kill_switch_proof={"passed": True, "stopped_by_kill_switch": True},
        acknowledged_exposure={"acknowledged": True, "max_positions": 1, "max_notional": 25.0, "expires_at": "2026-01-04T00:00:00+00:00"},
        now=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )

    assert report.checks["paper_exposure_acknowledged"] is False
    assert report.evidence["paper_exposure_acknowledgement_reason"] == "paper_exposure_acknowledgement_expired"


def test_paper_daemon_supervised_soak_blocks_until_enough_clean_windows():
    activation = {
        "passed": True,
        "blockers": [],
        "warnings": [],
        "artifact_path": "reports/activation.json",
        "evidence": {
            "submitted_iterations": 1,
            "observed_notional": 25.0,
            "artifact_paths": ["runs/paper-daemon/iteration-0001/20260731T153725Z-intraday-paper-session/session-report.json"],
        },
    }

    report = build_paper_daemon_supervised_soak_report(
        [activation],
        required_clean_activations=3,
        required_active_windows=2,
    )

    assert report.passed is False
    assert report.clean_activations == 1
    assert report.submitted_activations == 1
    assert report.active_windows == ("intraday",)
    assert "insufficient_clean_daemon_activations" in report.blockers
    assert "insufficient_active_window_coverage" in report.blockers
    assert report.recommended_action == "run_daemon_across_additional_active_windows"


def test_paper_daemon_supervised_soak_passes_clean_submitted_activations():
    activations = [
        {
            "passed": True,
            "blockers": [],
            "warnings": [],
            "artifact_path": f"reports/activation-{index}.json",
            "evidence": {
                "submitted_iterations": 1,
                "observed_notional": 25.0,
                "artifact_paths": [path],
            },
        }
        for index, path in enumerate(
            [
                "reports/paper-daemon-market_open-schedule.json",
                "reports/paper-daemon-intraday-schedule.json",
                "reports/paper-daemon-market_close-schedule.json",
            ],
            start=1,
        )
    ]

    report = build_paper_daemon_supervised_soak_report(
        activations,
        required_clean_activations=3,
        required_active_windows=2,
        max_total_observed_notional=100.0,
    )

    assert report.passed is True
    assert report.clean_activations == 3
    assert report.active_windows == ("market_open", "intraday", "market_close")
    assert report.total_observed_notional == 75.0
    assert report.recommended_action == "continue_supervised_always_on_paper_soak"


def test_paper_position_stewardship_passes_fresh_expected_position():
    monitor = {
        "passed": True,
        "unexpected_symbols": [],
        "missing_symbols": [],
        "closed_symbols": [],
        "lifecycle": {
            "positions": [
                {
                    "symbol": "SPY",
                    "status": "fresh",
                    "owner_type": "promoted_strategy",
                    "expected_quantity": 0.033723,
                    "observed_quantity": 0.033723,
                    "market_value": 25.0,
                    "age_hours": 0.5,
                    "forced_exit_needed": False,
                }
            ]
        },
    }

    report = build_paper_position_stewardship_report(monitor)

    assert report.passed is True
    assert report.active_positions == 1
    assert report.positions[0].action == "continue_monitoring"
    assert report.recommended_action == "continue_monitoring_active_paper_positions"


def test_paper_position_stewardship_blocks_stale_without_closure_evidence():
    monitor = {
        "passed": True,
        "unexpected_symbols": [],
        "missing_symbols": [],
        "closed_symbols": [],
        "lifecycle": {
            "positions": [
                {
                    "symbol": "SPY",
                    "status": "stale",
                    "owner_type": "promoted_strategy",
                    "expected_quantity": 0.033723,
                    "observed_quantity": 0.033723,
                    "market_value": 25.0,
                    "age_hours": 80.0,
                    "forced_exit_needed": True,
                }
            ]
        },
    }

    report = build_paper_position_stewardship_report(monitor, max_active_age_hours=72.0)

    assert report.passed is False
    assert report.blockers == ("unstewarded_or_stale_positions_present",)
    assert report.positions[0].action == "close_or_flatten_position"


def test_paper_position_stewardship_accepts_stale_position_with_cleanup_closure():
    monitor = {
        "passed": True,
        "unexpected_symbols": [],
        "missing_symbols": [],
        "closed_symbols": ["SPY"],
        "lifecycle": {
            "positions": [
                {
                    "symbol": "SPY",
                    "status": "stale",
                    "owner_type": "promoted_strategy",
                    "expected_quantity": 0.033723,
                    "observed_quantity": 0.0,
                    "market_value": None,
                    "age_hours": 80.0,
                    "forced_exit_needed": True,
                }
            ]
        },
    }
    cleanup = {"submitted_orders": [{"symbol": "SPY", "side": "SELL", "quantity": 0.033723, "status": "FILLED"}]}

    report = build_paper_position_stewardship_report(monitor, cleanup_evidence=cleanup)

    assert report.passed is True
    assert report.positions[0].closure_evidence_present is True
    assert report.positions[0].action == "closed_by_cleanup_evidence"


def test_paper_daemon_flatten_drill_passes_clean_close_cycle():
    pre_monitor = {
        "passed": True,
        "observed_positions": {"SPY": 0.033723},
        "observed_notional": 25.0,
        "unexpected_symbols": [],
        "missing_symbols": [],
    }
    flatten_plan = {
        "passed": True,
        "blocked_symbols": [],
        "orders": [{"symbol": "SPY", "side": "SELL", "quantity": 0.033723}],
    }
    cleanup = {
        "attempted": True,
        "submitted": True,
        "submitted_orders": [{"symbol": "SPY", "side": "SELL", "quantity": 0.033723, "status": "FILLED"}],
        "reconciliation_clean": True,
        "fill_poll_attempts": 1,
        "reason": "flatten_orders_submitted",
    }
    post_monitor = {
        "passed": True,
        "observed_positions": {},
        "unexpected_symbols": [],
        "missing_symbols": [],
        "closed_symbols": ["SPY"],
        "observed_notional": 0,
    }

    report = build_paper_daemon_flatten_drill_report(
        pre_monitor,
        flatten_plan,
        cleanup,
        post_monitor,
        stewardship={"passed": True, "active_positions": 0},
    )

    assert report.passed is True
    assert report.target_symbols == ("SPY",)
    assert report.closed_symbols == ("SPY",)
    assert report.submitted_orders == 1
    assert report.filled_orders == 1
    assert report.recommended_action == "flatten_drill_passed_continue_next_supervised_daemon_window"


def test_paper_daemon_flatten_drill_blocks_unsubmitted_cleanup():
    report = build_paper_daemon_flatten_drill_report(
        {"passed": True, "observed_positions": {"SPY": 0.033723}},
        {"passed": True, "orders": [{"symbol": "SPY", "side": "SELL"}]},
        {"attempted": False, "submitted": False, "submitted_orders": [], "reconciliation_clean": None},
        {"passed": False, "observed_positions": {"SPY": 0.033723}, "closed_symbols": []},
    )

    assert report.passed is False
    assert "cleanup_submitted" in report.blockers
    assert "post_monitor_flat" in report.blockers
    assert report.recommended_action == "submit_or_reconcile_guarded_flatten_orders_before_next_activation"


def test_paper_daemon_soak_readiness_rollup_blocks_until_supervised_soak_passes():
    report = build_paper_daemon_soak_readiness_rollup_report(
        {"passed": True},
        {
            "passed": False,
            "clean_activations": 1,
            "submitted_activations": 1,
            "active_windows": ["intraday"],
            "required_clean_activations": 3,
            "required_active_windows": 2,
            "blockers": ["insufficient_active_window_coverage"],
        },
        command_center={"passed": True},
        monitor={"passed": True, "observed_positions": {}, "closed_symbols": ["SPY"]},
        cleanup={"reason": "flatten_orders_submitted", "planned_orders": [{"symbol": "SPY"}], "submitted": True, "reconciliation_clean": True},
        data_parity={"passed": True},
        notional_decision={"passed": True, "action": "hold", "recommended_notional": 25.0},
        stewardship={"passed": True, "active_positions": 0},
        flatten_drill={"passed": True, "target_symbols": ["SPY"], "closed_symbols": ["SPY"]},
    )

    assert report.passed is False
    assert report.blockers == ("supervised_soak_passed",)
    assert report.evidence["active_windows"] == ["intraday"]
    assert report.recommended_action == "collect_more_clean_submitted_daemon_windows_before_escalation"


def test_paper_daemon_soak_readiness_rollup_passes_complete_clean_pack():
    report = build_paper_daemon_soak_readiness_rollup_report(
        {"passed": True},
        {
            "passed": True,
            "clean_activations": 3,
            "submitted_activations": 3,
            "active_windows": ["market_open", "intraday"],
            "required_clean_activations": 3,
            "required_active_windows": 2,
        },
        command_center={"passed": True},
        monitor={"passed": True, "observed_positions": {}, "closed_symbols": ["SPY"]},
        cleanup={"reason": "flatten_orders_submitted", "planned_orders": [{"symbol": "SPY"}], "submitted": True, "reconciliation_clean": True},
        data_parity={"passed": True},
        notional_decision={"passed": True, "action": "escalate", "recommended_notional": 50.0},
        stewardship={"passed": True, "active_positions": 0},
        flatten_drill={"passed": True, "target_symbols": ["SPY"], "closed_symbols": ["SPY"]},
    )

    assert report.passed is True
    assert report.blockers == ()
    assert report.recommended_action == "ready_to_continue_operator_managed_always_on_paper"


def test_paper_daemon_window_capture_plan_targets_missing_submit_windows():
    report = build_paper_daemon_window_capture_plan_report(
        {
            "passed": False,
            "clean_activations": 1,
            "submitted_activations": 1,
            "active_windows": ["intraday"],
            "required_clean_activations": 3,
            "required_active_windows": 2,
            "activations": [
                {
                    "passed": True,
                    "active_window": "intraday",
                    "submitted_iterations": 1,
                }
            ],
        },
        symbol="QQQ",
        strategy="tuffSystem",
        interval_seconds=60,
    )

    targets = {target.name: target for target in report.targets}
    assert report.passed is False
    assert report.captured_windows == ("intraday",)
    assert report.missing_windows == ("market_open", "market_close")
    assert "pending_window_captures" in report.blockers
    assert report.recommended_action == "run_guarded_daemon_during_market_open"
    assert targets["intraday"].action == "retain_evidence"
    assert targets["market_open"].action == "capture_next"
    assert "--submit-orders" in targets["market_open"].command
    assert "QQQ" in targets["market_open"].command
    assert "tuffSystem" in targets["market_open"].command


def test_paper_daemon_window_capture_plan_passes_complete_window_pack():
    report = build_paper_daemon_window_capture_plan_report(
        {
            "passed": True,
            "clean_activations": 3,
            "submitted_activations": 3,
            "active_windows": ["market_open", "intraday", "market_close"],
            "required_clean_activations": 3,
            "required_active_windows": 2,
            "activations": [
                {"passed": True, "active_window": "market_open", "submitted_iterations": 1},
                {"passed": True, "active_window": "intraday", "submitted_iterations": 1},
                {"passed": True, "active_window": "market_close", "submitted_iterations": 1},
            ],
        }
    )

    assert report.passed is True
    assert report.blockers == ()
    assert report.missing_windows == ()
    assert report.recommended_action == "multi_window_capture_complete_continue_supervised_soak_review"


def test_write_paper_daemon_ops_report_serializes_report(tmp_path):
    report = build_paper_daemon_daily_summary_report(
        {"state": {"status": "completed", "last_reason": "max_iterations_completed"}, "iterations": []},
        report_date="2026-01-05",
    )

    output = write_paper_daemon_ops_report(report, tmp_path / "daemon-summary.json")

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["report_date"] == "2026-01-05"
    assert payload["passed"] is True


def test_paper_daemon_ops_cli_writes_recovery_artifact(tmp_path, capsys):
    now = datetime.now(timezone.utc)
    state_path = tmp_path / "state.json"
    output_path = tmp_path / "ops.json"
    state_path.write_text(
        json.dumps(
                {
                    "status": "completed",
                    "iteration": 1,
                    "last_heartbeat_at": now.isoformat(),
                    "last_reason": "max_iterations_completed",
                }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "recovery",
            "--paper-daemon-state-output",
            str(state_path),
            "--paper-daemon-lock-path",
            str(tmp_path / "missing.lock"),
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["status"] == "completed"
    assert payload["recovery_required"] is False


def test_paper_daemon_ops_cli_writes_notional_recommendation(tmp_path, capsys):
    report_path = tmp_path / "daemon-report.json"
    output_path = tmp_path / "notional.json"
    report_path.write_text(
        json.dumps(
            {
                "state": {"status": "completed", "last_reason": "max_iterations_completed"},
                "iterations": [
                    {
                        "status": "completed",
                        "passed": True,
                        "submitted": True,
                        "monitor_passed": True,
                    }
                    for _ in range(10)
                ],
            }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "notional",
            "--paper-daemon-report-input",
            str(report_path),
            "--paper-daemon-current-notional",
            "25",
            "--paper-daemon-required-clean-iterations",
            "10",
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["action"] == "escalate"
    assert payload["recommended_notional"] == 50.0


def test_paper_daemon_ops_cli_writes_restart_drill_report(tmp_path, capsys):
    input_path = tmp_path / "restart-drills.json"
    output_path = tmp_path / "restart-report.json"
    input_path.write_text(
        json.dumps(
            {
                "drills": [
                    {"name": "clean_stop_resume", "stopped_cleanly": True, "resumed": True, "recovery_passed": True},
                    {"name": "stale_lock_replacement", "stale_lock_detected": True, "stale_lock_replaced": True, "resumed": True, "recovery_passed": True},
                    {"name": "kill_switch_resume", "kill_switch_written": True, "blocked_start": True, "kill_switch_cleared": True, "resumed_after_clear": True},
                    {"name": "duplicate_client_order_id_guard", "guard_enabled": True},
                ],
                "order_artifacts": [{"submitted_orders": [{"client_order_id": "safe-1"}]}],
            }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "restart-drill",
            "--paper-daemon-restart-drills-input",
            str(input_path),
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["passed"] is True
    assert payload["missing_drills"] == []


def test_paper_daemon_ops_cli_writes_activation_checklist(tmp_path, capsys):
    daemon_path = tmp_path / "daemon-report.json"
    center_path = tmp_path / "command-center.json"
    kill_path = tmp_path / "kill-proof.json"
    output_path = tmp_path / "activation-checklist.json"
    daemon_path.write_text(
        json.dumps(
            {
                "state": {"status": "completed", "last_reason": "max_iterations_completed"},
                "iterations": [{"status": "completed", "passed": True, "submitted": True, "monitor_passed": True}],
            }
        ),
        encoding="utf-8",
    )
    center_path.write_text(
        json.dumps({"passed": True, "daemon": {"heartbeat_state": "fresh", "kill_switch_active": False}, "paper": {}}),
        encoding="utf-8",
    )
    kill_path.write_text(json.dumps({"passed": True, "stopped_by_kill_switch": True}), encoding="utf-8")
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "activation-checklist",
            "--paper-daemon-report-input",
            str(daemon_path),
            "--paper-command-center-input",
            str(center_path),
            "--paper-daemon-kill-proof-input",
            str(kill_path),
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["passed"] is True
    assert payload["checks"]["active_submit_observed"] is True


def test_paper_exposure_acknowledgement_template_defaults_to_unacknowledged():
    report = build_paper_exposure_acknowledgement_template_report(
        {
            "artifact_path": "reports/cleanup.json",
            "positions_seen": [
                {"symbol": "DIA", "market_value": 12.5},
                {"symbol": "SPY", "market_value": 12.5},
            ],
        },
        max_notional_buffer_pct=20.0,
        expires_at="2026-01-06T00:00:00+00:00",
    )

    payload = report.to_dict()
    assert payload["acknowledged"] is False
    assert payload["symbols"] == ["DIA", "SPY"]
    assert payload["max_positions"] == 2
    assert payload["max_notional"] == 30.0
    assert payload["expires_at"] == "2026-01-06T00:00:00+00:00"


def test_paper_daemon_ops_cli_writes_exposure_ack_template(tmp_path, capsys):
    cleanup_path = tmp_path / "cleanup.json"
    output_path = tmp_path / "ack-template.json"
    cleanup_path.write_text(
        json.dumps(
            {
                "artifact_path": str(cleanup_path),
                "positions_seen": [{"symbol": "SPY", "market_value": 10.0}],
            }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "exposure-ack-template",
            "--paper-daemon-cleanup-input",
            str(cleanup_path),
            "--paper-daemon-ack-template-buffer-pct",
            "10",
            "--paper-daemon-ack-template-expires-at",
            "2026-01-06T00:00:00+00:00",
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["acknowledged"] is False
    assert payload["max_notional"] == 11.0


def test_paper_daemon_ops_cli_writes_supervised_soak_report(tmp_path, capsys):
    activation_path = tmp_path / "activation.json"
    output_path = tmp_path / "supervised-soak.json"
    activation_path.write_text(
        json.dumps(
            {
                "passed": True,
                "blockers": [],
                "warnings": [],
                "evidence": {
                    "submitted_iterations": 1,
                    "observed_notional": 25.0,
                    "artifact_paths": ["reports/paper-daemon-intraday-schedule.json"],
                },
            }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "supervised-soak",
            "--paper-daemon-activation-inputs",
            str(activation_path),
            "--paper-daemon-soak-required-clean-activations",
            "1",
            "--paper-daemon-soak-required-active-windows",
            "1",
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["passed"] is True
    assert payload["clean_activations"] == 1
    assert payload["active_windows"] == ["intraday"]


def test_paper_daemon_ops_cli_writes_position_stewardship_report(tmp_path, capsys):
    monitor_path = tmp_path / "monitor.json"
    output_path = tmp_path / "stewardship.json"
    monitor_path.write_text(
        json.dumps(
            {
                "passed": True,
                "unexpected_symbols": [],
                "missing_symbols": [],
                "lifecycle": {
                    "positions": [
                        {
                            "symbol": "SPY",
                            "status": "fresh",
                            "owner_type": "promoted_strategy",
                            "expected_quantity": 0.033723,
                            "observed_quantity": 0.033723,
                            "market_value": 25.0,
                            "age_hours": 0.5,
                            "forced_exit_needed": False,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "position-stewardship",
            "--paper-daemon-position-monitor-input",
            str(monitor_path),
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["passed"] is True
    assert payload["active_positions"] == 1


def test_paper_daemon_ops_cli_writes_flatten_drill_report(tmp_path, capsys):
    pre_path = tmp_path / "pre-monitor.json"
    plan_path = tmp_path / "flatten-plan.json"
    cleanup_path = tmp_path / "cleanup-submit.json"
    post_path = tmp_path / "post-monitor.json"
    stewardship_path = tmp_path / "stewardship.json"
    output_path = tmp_path / "flatten-drill.json"
    pre_path.write_text(
        json.dumps({"passed": True, "observed_positions": {"SPY": 0.033723}, "observed_notional": 25.0}),
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps({"passed": True, "orders": [{"symbol": "SPY", "side": "SELL", "quantity": 0.033723}]}),
        encoding="utf-8",
    )
    cleanup_path.write_text(
        json.dumps(
            {
                "attempted": True,
                "submitted": True,
                "submitted_orders": [{"symbol": "SPY", "side": "SELL", "quantity": 0.033723, "status": "FILLED"}],
                "reconciliation_clean": True,
            }
        ),
        encoding="utf-8",
    )
    post_path.write_text(
        json.dumps({"passed": True, "observed_positions": {}, "unexpected_symbols": [], "missing_symbols": [], "closed_symbols": ["SPY"]}),
        encoding="utf-8",
    )
    stewardship_path.write_text(json.dumps({"passed": True, "active_positions": 0}), encoding="utf-8")
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "flatten-drill",
            "--paper-daemon-flatten-pre-monitor-input",
            str(pre_path),
            "--paper-daemon-flatten-plan-input",
            str(plan_path),
            "--paper-daemon-flatten-cleanup-input",
            str(cleanup_path),
            "--paper-daemon-flatten-post-monitor-input",
            str(post_path),
            "--paper-daemon-flatten-stewardship-input",
            str(stewardship_path),
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["passed"] is True
    assert payload["target_symbols"] == ["SPY"]


def test_paper_daemon_ops_cli_writes_soak_rollup_report(tmp_path, capsys):
    activation_path = tmp_path / "activation.json"
    soak_path = tmp_path / "soak.json"
    center_path = tmp_path / "center.json"
    monitor_path = tmp_path / "monitor.json"
    cleanup_path = tmp_path / "cleanup.json"
    parity_path = tmp_path / "parity.json"
    notional_path = tmp_path / "notional.json"
    stewardship_path = tmp_path / "stewardship.json"
    drill_path = tmp_path / "flatten-drill.json"
    output_path = tmp_path / "soak-rollup.json"
    activation_path.write_text(json.dumps({"passed": True}), encoding="utf-8")
    soak_path.write_text(
        json.dumps(
            {
                "passed": False,
                "clean_activations": 1,
                "submitted_activations": 1,
                "active_windows": ["intraday"],
                "required_clean_activations": 3,
                "required_active_windows": 2,
                "blockers": ["insufficient_active_window_coverage"],
            }
        ),
        encoding="utf-8",
    )
    center_path.write_text(json.dumps({"passed": True}), encoding="utf-8")
    monitor_path.write_text(json.dumps({"passed": True, "observed_positions": {}, "closed_symbols": ["SPY"]}), encoding="utf-8")
    cleanup_path.write_text(json.dumps({"planned_orders": [{"symbol": "SPY"}], "submitted": True, "reconciliation_clean": True}), encoding="utf-8")
    parity_path.write_text(json.dumps({"passed": True}), encoding="utf-8")
    notional_path.write_text(json.dumps({"passed": True, "action": "hold", "recommended_notional": 25.0}), encoding="utf-8")
    stewardship_path.write_text(json.dumps({"passed": True, "active_positions": 0}), encoding="utf-8")
    drill_path.write_text(json.dumps({"passed": True, "target_symbols": ["SPY"], "closed_symbols": ["SPY"]}), encoding="utf-8")
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "soak-rollup",
            "--paper-daemon-activation-checklist-input",
            str(activation_path),
            "--paper-daemon-supervised-soak-input",
            str(soak_path),
            "--paper-command-center-input",
            str(center_path),
            "--paper-daemon-position-monitor-input",
            str(monitor_path),
            "--paper-daemon-position-cleanup-input",
            str(cleanup_path),
            "--paper-daemon-data-parity-input",
            str(parity_path),
            "--paper-daemon-notional-input",
            str(notional_path),
            "--paper-daemon-stewardship-input",
            str(stewardship_path),
            "--paper-daemon-flatten-drill-input",
            str(drill_path),
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["passed"] is False
    assert payload["blockers"] == ["supervised_soak_passed"]
    assert payload["recommended_action"] == "collect_more_clean_submitted_daemon_windows_before_escalation"


def test_paper_daemon_ops_cli_writes_window_capture_plan(tmp_path, capsys):
    soak_path = tmp_path / "supervised-soak.json"
    output_path = tmp_path / "window-capture-plan.json"
    soak_path.write_text(
        json.dumps(
            {
                "passed": False,
                "clean_activations": 1,
                "submitted_activations": 1,
                "active_windows": ["intraday"],
                "required_clean_activations": 3,
                "required_active_windows": 2,
                "activations": [{"passed": True, "active_window": "intraday", "submitted_iterations": 1}],
            }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "paper-daemon-ops",
            "--paper-daemon-ops-type",
            "window-capture-plan",
            "--paper-daemon-supervised-soak-input",
            str(soak_path),
            "--paper-daemon-window-capture-windows",
            "market_open,intraday,market_close",
            "--symbol",
            "QQQ",
            "--strategy",
            "tuffSystem",
            "--paper-daemon-ops-output",
            str(output_path),
        ]
    )

    run_paper_daemon_ops_app(args)

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Paper daemon ops report written" in captured.out
    assert payload["passed"] is False
    assert payload["captured_windows"] == ["intraday"]
    assert payload["missing_windows"] == ["market_open", "market_close"]
    assert payload["targets"][0]["command"][8] == "QQQ"
