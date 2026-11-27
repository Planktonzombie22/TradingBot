from datetime import datetime, timezone

from src.deployment import (
    AlertRoutingReport,
    ArtifactRetentionReport,
    BrokerAuditLogReport,
    CommandIdempotencyReport,
    DailyOperatorCycleReport,
    DeploymentHealthCheckReport,
    DeploymentMachineRehearsalReport,
    GuiExecutablePackagingReport,
    JobLeaseReport,
    NotificationSinkReport,
    OperatorInboxReport,
    ProcessSupervisionReport,
    ReadinessPageRefreshReport,
    SecretManagementGuidanceReport,
    ServiceEntrypointReport,
    WindowsTaskSchedulerConfigReport,
    build_alert_routing_report,
    build_artifact_retention_report,
    build_broker_audit_log_report,
    build_command_idempotency_report,
    build_daily_operator_cycle_report,
    build_deployment_health_check_report,
    build_deployment_machine_rehearsal_report,
    build_gui_executable_packaging_report,
    build_job_lease_report,
    build_notification_sink_report,
    build_operator_inbox_report,
    build_process_supervision_report,
    build_readiness_page_refresh_report,
    build_secret_management_guidance_report,
    build_service_entrypoint_report,
    build_windows_task_scheduler_config_report,
)


def test_daily_operator_cycle_report_tracks_all_required_operator_steps():
    report = build_daily_operator_cycle_report(
        {
            "data_sync": {"passed": True, "artifact_path": "reports/data-sync.json"},
            "research_refresh_check": {"passed": True},
            "scheduled_paper_pilot": {"passed": False, "reason": "market_closed"},
            "paper_monitor": {"passed": True},
            "daily_report": {"passed": True},
            "readiness_update": {"passed": True},
            "alert_summary": {"passed": True},
        },
        now=datetime(2026, 7, 27, 13, 0, tzinfo=timezone.utc),
    )

    assert isinstance(report, DailyOperatorCycleReport)
    assert not report.passed
    assert report.reason == "market_closed"
    assert [step.name for step in report.steps] == [
        "data_sync",
        "research_refresh_check",
        "scheduled_paper_pilot",
        "paper_monitor",
        "daily_report",
        "readiness_update",
        "alert_summary",
    ]


def test_windows_task_scheduler_config_generates_session_jobs():
    report = build_windows_task_scheduler_config_report(python_executable="py", base_command="main.py")

    assert isinstance(report, WindowsTaskSchedulerConfigReport)
    assert report.passed
    names = {entry.name for entry in report.entries}
    assert {"tradingbot-pre-market", "tradingbot-market-open", "tradingbot-intraday-monitor", "tradingbot-close", "tradingbot-end-of-day"} <= names
    assert all(entry.command.startswith("py main.py") for entry in report.entries)


def test_gui_executable_packaging_report_builds_pyinstaller_plan():
    report = build_gui_executable_packaging_report(
        project_root=".",
        app_name="TradingBotOperator",
        pyinstaller_executable="pyinstaller",
        pyinstaller_available=False,
    )

    assert isinstance(report, GuiExecutablePackagingReport)
    assert report.passed
    assert report.reason == "gui_packaging_plan_ready_pyinstaller_unverified"
    assert report.build_command[:8] == ("pyinstaller", "--noconfirm", "--clean", "--onefile", "--windowed", "--name", "TradingBotOperator", "--distpath")
    assert "gui_app.py" == report.build_command[-1]
    assert "README.md" in report.included_paths
    assert "matplotlib.backends.backend_tkagg" in report.hidden_imports


def test_service_entrypoint_report_separates_monitor_and_scheduled_commands():
    report = build_service_entrypoint_report(profile_name="docker", python_command="python", base_command="main.py")

    assert isinstance(report, ServiceEntrypointReport)
    assert report.passed
    assert "paper-monitor" in report.continuous_monitor_command
    assert "paper-session-schedule" in report.scheduled_command
    assert report.environment["ALLOW_LIVE_TRADING"] == "false"


def test_process_supervision_blocks_auto_restart_for_order_submission_jobs():
    report = build_process_supervision_report(
        [
            {"job_name": "monitor", "job_type": "monitor", "restart_allowed": True, "max_restarts": 3},
            {"job_name": "submit", "job_type": "order_submission", "restart_allowed": True, "max_restarts": 1},
            {"job_name": "cleanup", "job_type": "order_submission", "restart_allowed": False},
        ]
    )

    assert isinstance(report, ProcessSupervisionReport)
    assert not report.passed
    decisions = {decision.job_name: decision for decision in report.decisions}
    assert decisions["monitor"].passed
    assert decisions["submit"].reason == "order_submission_auto_restart_forbidden"
    assert decisions["cleanup"].passed


def test_job_lease_report_blocks_overlapping_active_leases():
    now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
    report = build_job_lease_report(
        [{"job_name": "paper-session", "lease_key": "broker-submit"}, {"job_name": "monitor", "lease_key": "monitor"}],
        active_leases={"broker-submit": "2026-07-27T14:10:00+00:00"},
        now=now,
        ttl_seconds=600,
    )

    assert isinstance(report, JobLeaseReport)
    assert not report.passed
    decisions = {decision.job_name: decision for decision in report.decisions}
    assert decisions["paper-session"].reason == "job_lease_already_active"
    assert decisions["monitor"].acquired
    assert decisions["monitor"].expires_at == "2026-07-27T14:10:00+00:00"


def test_command_idempotency_report_detects_duplicate_daily_command_keys():
    report = build_command_idempotency_report(
        [
            {"command_name": "paper-pilot", "run_date": "2026-07-27", "scope": "SPY"},
            {"command_name": "paper-monitor", "run_date": "2026-07-27", "scope": "SPY"},
            {"command_name": "paper-pilot", "run_date": "2026-07-27", "scope": "SPY"},
        ],
        existing_keys=("paper-cleanup:2026-07-27:global",),
    )

    assert isinstance(report, CommandIdempotencyReport)
    assert not report.passed
    assert report.keys[0].key == "paper-pilot:2026-07-27:SPY"
    assert report.keys[2].duplicate
    assert report.reason == "command_idempotency_duplicate"


def test_artifact_retention_report_archives_old_artifacts_but_preserves_live_evidence():
    report = build_artifact_retention_report(
        [
            {"path": "runs/old.json", "age_days": 45},
            {"path": "reports/live-evidence.json", "age_days": 45, "preserve_for_live_readiness": True},
            {"path": "runs/new.json", "age_days": 2},
        ],
        retention_days=30,
        evidence_retention_days=120,
    )

    assert isinstance(report, ArtifactRetentionReport)
    assert report.passed
    actions = {decision.path: decision.action for decision in report.decisions}
    assert actions["runs/old.json"] == "archive"
    assert actions["reports/live-evidence.json"] == "preserve"
    assert actions["runs/new.json"] == "keep"


def test_secret_management_guidance_report_blocks_unsafe_environment_combinations():
    clean = build_secret_management_guidance_report(
        {
            "profile": "local",
            "env_file_present": True,
            "env_gitignored": True,
            "allow_live_trading": False,
            "paper_url_configured": True,
            "plaintext_secrets_in_reports": False,
        }
    )
    dirty = build_secret_management_guidance_report(
        {
            "profile": "docker",
            "env_file_present": True,
            "env_gitignored": False,
            "allow_live_trading": True,
            "paper_url_configured": False,
            "plaintext_secrets_in_reports": True,
        }
    )

    assert isinstance(clean, SecretManagementGuidanceReport)
    assert clean.passed
    assert not dirty.passed
    assert dirty.reason == "env_file_not_gitignored"


def test_broker_audit_log_report_requires_run_config_evidence_and_decision_status():
    report = build_broker_audit_log_report(
        [
            {
                "run_id": "run-1",
                "command": "paper-session",
                "config_hash": "abc",
                "evidence_paths": ["reports/session.json"],
                "decision_status": "submitted",
                "broker_touched": True,
            },
            {
                "run_id": "run-2",
                "command": "paper-monitor",
                "config_hash": "def",
                "decision_status": "read_only",
                "broker_touched": False,
            },
            {
                "run_id": "run-3",
                "command": "paper-cleanup",
                "config_hash": "",
                "decision_status": "blocked",
                "broker_touched": True,
            },
        ]
    )

    assert isinstance(report, BrokerAuditLogReport)
    assert not report.passed
    assert report.entries[0].passed
    assert report.entries[1].passed
    assert report.entries[2].to_dict()["reason"] == "broker_audit_log_incomplete"


def test_alert_routing_and_notification_sink_reports_require_local_and_configured_routes():
    routing = build_alert_routing_report(
        [
            {"alert_type": "risk_halt", "severity": "critical", "sink": "local", "routed": True},
            {"alert_type": "broker_outage", "severity": "critical", "sink": "", "routed": False},
        ]
    )
    sinks = build_notification_sink_report(["local", "webhook"])

    assert isinstance(routing, AlertRoutingReport)
    assert not routing.passed
    assert routing.reason == "alert_route_missing"
    assert isinstance(sinks, NotificationSinkReport)
    assert sinks.passed
    assert "webhook" in sinks.enabled_sinks


def test_deployment_health_check_report_covers_provider_broker_stream_storage_scheduler_and_artifacts():
    report = build_deployment_health_check_report(
        {
            "data_provider": True,
            "broker_rest": {"healthy": True, "reason": "ok"},
            "broker_account_state": True,
            "websocket_stream": False,
            "storage": True,
            "scheduler": True,
            "artifact_write_path": True,
        }
    )

    assert isinstance(report, DeploymentHealthCheckReport)
    assert not report.passed
    assert report.reason == "websocket_stream_unhealthy"


def test_readiness_page_refresh_report_requires_source_artifacts_and_output_page():
    report = build_readiness_page_refresh_report(["reports/schedule.json", "reports/monitor.json"], "reports/readiness.html", refreshed=True)
    dirty = build_readiness_page_refresh_report([], "reports/readiness.html", refreshed=True)

    assert isinstance(report, ReadinessPageRefreshReport)
    assert report.passed
    assert not dirty.passed
    assert dirty.to_dict()["reason"] == "readiness_page_refresh_incomplete"


def test_operator_inbox_report_lists_open_review_items():
    report = build_operator_inbox_report(
        [
            {"name": "review_slippage", "severity": "warning", "action": "inspect fill quality", "source_artifact": "reports/slippage.json"},
            {"name": "ack_daily_report", "severity": "info", "action": "read report", "resolved": True},
        ]
    )

    assert isinstance(report, OperatorInboxReport)
    assert not report.passed
    assert report.reason == "operator_review_required"
    assert report.open_items[0].name == "review_slippage"


def test_deployment_machine_rehearsal_report_requires_actual_machine_evidence():
    clean = build_deployment_machine_rehearsal_report(
        {
            "machine_id": "desktop-tradingbot",
            "profile_name": "windows-task",
            "artifact_paths": ["reports/rehearsal.json"],
            "environment_captured": True,
            "scheduler_verified": True,
            "state_paths_verified": True,
        }
    )
    dirty = build_deployment_machine_rehearsal_report(
        {
            "machine_id": "server",
            "profile_name": "docker",
            "artifact_paths": ["reports/rehearsal.json"],
            "environment_captured": True,
            "scheduler_verified": False,
            "state_paths_verified": True,
        }
    )

    assert isinstance(clean, DeploymentMachineRehearsalReport)
    assert clean.passed
    assert not dirty.passed
    assert dirty.reason == "deployment_scheduler_not_verified"
