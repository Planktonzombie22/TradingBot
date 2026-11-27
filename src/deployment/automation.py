import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class DailyOperatorCycleStep:
    name: str
    command: str
    required: bool = True
    passed: bool = False
    artifact_path: str | None = None
    reason: str = "pending"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "required": self.required,
            "passed": self.passed,
            "artifact_path": self.artifact_path,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DailyOperatorCycleReport:
    steps: tuple[DailyOperatorCycleStep, ...]
    generated_at: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(step.passed for step in self.steps if step.required)

    @property
    def reason(self) -> str:
        if self.passed:
            return "daily_operator_cycle_ready"
        return next(step.reason for step in self.steps if step.required and not step.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "generated_at": self.generated_at,
            "steps": [step.to_dict() for step in self.steps],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class WindowsTaskScheduleEntry:
    name: str
    trigger: str
    command: str
    enabled: bool = True
    allow_broker_submission: bool = False

    @property
    def passed(self) -> bool:
        return bool(self.name and self.trigger and self.command)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "command": self.command,
            "enabled": self.enabled,
            "allow_broker_submission": self.allow_broker_submission,
            "passed": self.passed,
            "reason": "windows_task_schedule_entry_valid" if self.passed else "windows_task_schedule_entry_incomplete",
        }


@dataclass(frozen=True)
class WindowsTaskSchedulerConfigReport:
    entries: tuple[WindowsTaskScheduleEntry, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(entry.passed for entry in self.entries)

    @property
    def reason(self) -> str:
        return "windows_task_scheduler_config_valid" if self.passed else "windows_task_scheduler_config_incomplete"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "entries": [entry.to_dict() for entry in self.entries],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class GuiExecutablePackagingReport:
    app_name: str
    entrypoint: str
    output_dir: str
    build_command: tuple[str, ...]
    included_paths: tuple[str, ...] = ()
    hidden_imports: tuple[str, ...] = ()
    required_files_present: bool = True
    pyinstaller_available: bool | None = None
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.app_name and self.entrypoint and self.output_dir and self.build_command and self.required_files_present)

    @property
    def reason(self) -> str:
        if not self.required_files_present:
            return "gui_packaging_required_files_missing"
        if not self.build_command:
            return "gui_packaging_command_missing"
        if not self.app_name or not self.entrypoint or not self.output_dir:
            return "gui_packaging_config_incomplete"
        if self.pyinstaller_available is False:
            return "gui_packaging_plan_ready_pyinstaller_unverified"
        return "gui_packaging_plan_ready"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "app_name": self.app_name,
            "entrypoint": self.entrypoint,
            "output_dir": self.output_dir,
            "build_command": list(self.build_command),
            "included_paths": list(self.included_paths),
            "hidden_imports": list(self.hidden_imports),
            "required_files_present": self.required_files_present,
            "pyinstaller_available": self.pyinstaller_available,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ServiceEntrypointReport:
    profile_name: str
    command: str
    continuous_monitor_command: str
    scheduled_command: str
    environment: Mapping[str, str] = field(default_factory=dict)
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.command and self.continuous_monitor_command and self.scheduled_command)

    @property
    def reason(self) -> str:
        return "service_entrypoint_ready" if self.passed else "service_entrypoint_incomplete"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "profile_name": self.profile_name,
            "command": self.command,
            "continuous_monitor_command": self.continuous_monitor_command,
            "scheduled_command": self.scheduled_command,
            "environment": dict(self.environment),
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ProcessSupervisionDecision:
    job_name: str
    job_type: str
    restart_allowed: bool
    max_restarts: int
    reason: str

    @property
    def passed(self) -> bool:
        return self.job_type != "order_submission" or not self.restart_allowed

    def to_dict(self) -> dict:
        return {
            "job_name": self.job_name,
            "job_type": self.job_type,
            "restart_allowed": self.restart_allowed,
            "max_restarts": self.max_restarts,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProcessSupervisionReport:
    decisions: tuple[ProcessSupervisionDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "process_supervision_policy_valid"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class JobLeaseDecision:
    job_name: str
    lease_key: str
    acquired: bool
    expires_at: str | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.acquired

    def to_dict(self) -> dict:
        return {
            "job_name": self.job_name,
            "lease_key": self.lease_key,
            "acquired": self.acquired,
            "expires_at": self.expires_at,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class JobLeaseReport:
    decisions: tuple[JobLeaseDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "job_leases_acquired"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class CommandIdempotencyKey:
    command_name: str
    run_date: str
    scope: str
    key: str
    duplicate: bool
    reason: str

    @property
    def passed(self) -> bool:
        return not self.duplicate

    def to_dict(self) -> dict:
        return {
            "command_name": self.command_name,
            "run_date": self.run_date,
            "scope": self.scope,
            "key": self.key,
            "duplicate": self.duplicate,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CommandIdempotencyReport:
    keys: tuple[CommandIdempotencyKey, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(key.passed for key in self.keys)

    @property
    def reason(self) -> str:
        if self.passed:
            return "command_idempotency_keys_valid"
        return next(key.reason for key in self.keys if key.duplicate)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "keys": [key.to_dict() for key in self.keys],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ArtifactRetentionDecision:
    path: str
    age_days: int
    action: str
    preserve_for_live_readiness: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.action in {"keep", "archive", "preserve"}

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "age_days": self.age_days,
            "action": self.action,
            "preserve_for_live_readiness": self.preserve_for_live_readiness,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ArtifactRetentionReport:
    decisions: tuple[ArtifactRetentionDecision, ...]
    retention_days: int = 30
    evidence_retention_days: int = 120
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "artifact_retention_policy_valid"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "retention_days": self.retention_days,
            "evidence_retention_days": self.evidence_retention_days,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class SecretManagementCheck:
    name: str
    passed: bool
    reason: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "reason": self.reason, "details": dict(self.details)}


@dataclass(frozen=True)
class SecretManagementGuidanceReport:
    checks: tuple[SecretManagementCheck, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "secret_management_guidance_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class BrokerAuditLogEntry:
    run_id: str
    command: str
    config_hash: str
    evidence_paths: tuple[str, ...]
    decision_status: str
    broker_touched: bool
    reason: str

    @property
    def passed(self) -> bool:
        return bool(self.run_id and self.command and self.config_hash and self.decision_status and (not self.broker_touched or self.evidence_paths))

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "command": self.command,
            "config_hash": self.config_hash,
            "evidence_paths": list(self.evidence_paths),
            "decision_status": self.decision_status,
            "broker_touched": self.broker_touched,
            "passed": self.passed,
            "reason": self.reason if self.passed else "broker_audit_log_incomplete",
        }


@dataclass(frozen=True)
class BrokerAuditLogReport:
    entries: tuple[BrokerAuditLogEntry, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(entry.passed for entry in self.entries)

    @property
    def reason(self) -> str:
        if self.passed:
            return "broker_audit_log_valid"
        return next(entry.to_dict()["reason"] for entry in self.entries if not entry.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "entries": [entry.to_dict() for entry in self.entries],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class AlertRoutingDecision:
    alert_type: str
    severity: str
    sink: str
    routed: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.routed

    def to_dict(self) -> dict:
        return {
            "alert_type": self.alert_type,
            "severity": self.severity,
            "sink": self.sink,
            "routed": self.routed,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AlertRoutingReport:
    decisions: tuple[AlertRoutingDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "alert_routing_valid"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class NotificationSinkReport:
    enabled_sinks: tuple[str, ...]
    optional_sinks: tuple[str, ...]
    local_sink_enabled: bool
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.local_sink_enabled

    @property
    def reason(self) -> str:
        return "notification_sinks_valid" if self.passed else "local_notification_sink_missing"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "enabled_sinks": list(self.enabled_sinks),
            "optional_sinks": list(self.optional_sinks),
            "local_sink_enabled": self.local_sink_enabled,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class DeploymentHealthCheckStatus:
    name: str
    healthy: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.healthy

    def to_dict(self) -> dict:
        return {"name": self.name, "healthy": self.healthy, "passed": self.passed, "reason": self.reason}


@dataclass(frozen=True)
class DeploymentHealthCheckReport:
    checks: tuple[DeploymentHealthCheckStatus, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "deployment_health_checks_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ReadinessPageRefreshReport:
    source_artifacts: tuple[str, ...]
    readiness_page_path: str
    refreshed: bool
    reason: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.refreshed and bool(self.source_artifacts and self.readiness_page_path)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason if self.passed else "readiness_page_refresh_incomplete",
            "source_artifacts": list(self.source_artifacts),
            "readiness_page_path": self.readiness_page_path,
            "refreshed": self.refreshed,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class OperatorInboxItem:
    name: str
    severity: str
    action: str
    source_artifact: str | None = None
    resolved: bool = False

    @property
    def passed(self) -> bool:
        return self.resolved

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "severity": self.severity,
            "action": self.action,
            "source_artifact": self.source_artifact,
            "resolved": self.resolved,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class OperatorInboxReport:
    items: tuple[OperatorInboxItem, ...]
    artifact_path: str | None = None

    @property
    def open_items(self) -> tuple[OperatorInboxItem, ...]:
        return tuple(item for item in self.items if not item.resolved)

    @property
    def passed(self) -> bool:
        return not self.open_items

    @property
    def reason(self) -> str:
        return "operator_inbox_clear" if self.passed else "operator_review_required"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "open_count": len(self.open_items),
            "items": [item.to_dict() for item in self.items],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class DeploymentMachineRehearsalReport:
    machine_id: str
    profile_name: str
    artifact_paths: tuple[str, ...]
    environment_captured: bool
    scheduler_verified: bool
    state_paths_verified: bool
    passed: bool
    reason: str
    artifact_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "machine_id": self.machine_id,
            "profile_name": self.profile_name,
            "artifact_paths": list(self.artifact_paths),
            "environment_captured": self.environment_captured,
            "scheduler_verified": self.scheduler_verified,
            "state_paths_verified": self.state_paths_verified,
            "artifact_path": self.artifact_path,
        }


def build_daily_operator_cycle_report(
    step_results: Mapping[str, Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> DailyOperatorCycleReport:
    observed = now or datetime.now(timezone.utc)
    results = step_results or {}
    defaults = (
        ("data_sync", "main.py validate-profile --profile fast"),
        ("research_refresh_check", "main.py validate-profile --profile release"),
        ("scheduled_paper_pilot", "main.py paper-session-schedule"),
        ("paper_monitor", "main.py paper-monitor"),
        ("daily_report", "main.py report"),
        ("readiness_update", "main.py release-checklist"),
        ("alert_summary", "main.py validate"),
    )
    steps = tuple(_daily_cycle_step(name, command, results.get(name, {})) for name, command in defaults)
    return DailyOperatorCycleReport(steps=steps, generated_at=observed.isoformat())


def build_windows_task_scheduler_config_report(
    python_executable: str = r"trading_env\Scripts\python.exe",
    base_command: str = "main.py",
) -> WindowsTaskSchedulerConfigReport:
    entries = (
        WindowsTaskScheduleEntry("tradingbot-pre-market", "08:00", f"{python_executable} {base_command} validate-profile --profile fast"),
        WindowsTaskScheduleEntry("tradingbot-market-open", "09:35", f"{python_executable} {base_command} paper-session-schedule"),
        WindowsTaskScheduleEntry("tradingbot-intraday-monitor", "12:00", f"{python_executable} {base_command} paper-monitor"),
        WindowsTaskScheduleEntry("tradingbot-close", "15:45", f"{python_executable} {base_command} paper-cleanup"),
        WindowsTaskScheduleEntry("tradingbot-end-of-day", "16:30", f"{python_executable} {base_command} release-checklist"),
    )
    return WindowsTaskSchedulerConfigReport(entries)


def build_gui_executable_packaging_report(
    *,
    project_root: str | Path = ".",
    app_name: str = "TradingBot",
    entrypoint: str = "gui_app.py",
    output_dir: str = "dist",
    pyinstaller_executable: str = "pyinstaller",
    pyinstaller_available: bool | None = None,
    included_paths: Sequence[str] = ("configs", "docs", "README.md", "ROADMAP.md"),
    hidden_imports: Sequence[str] = ("matplotlib.backends.backend_tkagg", "tkinter"),
) -> GuiExecutablePackagingReport:
    root = Path(project_root)
    required_paths = (root / entrypoint, root / "main.py", root / "src")
    included = tuple(str(path) for path in included_paths)
    hidden = tuple(str(name) for name in hidden_imports)
    command = [
        pyinstaller_executable,
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        app_name,
        "--distpath",
        output_dir,
    ]
    for path in included:
        command.extend(["--add-data", f"{path};{path}"])
    for name in hidden:
        command.extend(["--hidden-import", name])
    command.append(entrypoint)
    return GuiExecutablePackagingReport(
        app_name=app_name,
        entrypoint=entrypoint,
        output_dir=output_dir,
        build_command=tuple(command),
        included_paths=included,
        hidden_imports=hidden,
        required_files_present=all(path.exists() for path in required_paths),
        pyinstaller_available=pyinstaller_available,
    )


def build_service_entrypoint_report(
    profile_name: str = "docker",
    python_command: str = "python",
    base_command: str = "main.py",
) -> ServiceEntrypointReport:
    return ServiceEntrypointReport(
        profile_name=profile_name,
        command=f"{python_command} {base_command} paper --provider alpaca --execution-mode paper",
        continuous_monitor_command=f"{python_command} {base_command} paper-monitor",
        scheduled_command=f"{python_command} {base_command} paper-session-schedule",
        environment={"PAPER_TRADING": "true", "EXECUTION_MODE": "paper", "ALLOW_LIVE_TRADING": "false"},
    )


def build_process_supervision_report(rows: Sequence[Mapping[str, Any]]) -> ProcessSupervisionReport:
    return ProcessSupervisionReport(tuple(_supervision_decision(row) for row in rows))


def build_job_lease_report(
    rows: Sequence[Mapping[str, Any]],
    active_leases: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    ttl_seconds: int = 900,
) -> JobLeaseReport:
    observed = now or datetime.now(timezone.utc)
    active = active_leases or {}
    return JobLeaseReport(tuple(_job_lease_decision(row, active, observed, ttl_seconds) for row in rows))


def build_command_idempotency_report(
    rows: Sequence[Mapping[str, Any]],
    existing_keys: Sequence[str] = (),
) -> CommandIdempotencyReport:
    seen = set(existing_keys)
    keys = []
    for row in rows:
        item = _idempotency_key(row, seen)
        keys.append(item)
        seen.add(item.key)
    return CommandIdempotencyReport(tuple(keys))


def build_artifact_retention_report(
    rows: Sequence[Mapping[str, Any]],
    retention_days: int = 30,
    evidence_retention_days: int = 120,
) -> ArtifactRetentionReport:
    return ArtifactRetentionReport(
        tuple(_artifact_retention_decision(row, retention_days, evidence_retention_days) for row in rows),
        retention_days=retention_days,
        evidence_retention_days=evidence_retention_days,
    )


def build_secret_management_guidance_report(config: Mapping[str, Any]) -> SecretManagementGuidanceReport:
    checks = (
        _secret_check("env_file_present", bool(config.get("env_file_present", False)), "env_file_missing", config),
        _secret_check("env_gitignored", bool(config.get("env_gitignored", False)), "env_file_not_gitignored", config),
        _secret_check("live_trading_locked", not bool(config.get("allow_live_trading", False)), "live_trading_not_locked", config),
        _secret_check("paper_url_configured", bool(config.get("paper_url_configured", False)), "paper_url_missing", config),
        _secret_check("no_plaintext_secrets_in_reports", not bool(config.get("plaintext_secrets_in_reports", False)), "plaintext_secrets_in_reports", config),
    )
    return SecretManagementGuidanceReport(checks)


def build_broker_audit_log_report(rows: Sequence[Mapping[str, Any]]) -> BrokerAuditLogReport:
    return BrokerAuditLogReport(tuple(_broker_audit_log_entry(row) for row in rows))


def build_alert_routing_report(rows: Sequence[Mapping[str, Any]]) -> AlertRoutingReport:
    return AlertRoutingReport(tuple(_alert_routing_decision(row) for row in rows))


def build_notification_sink_report(enabled_sinks: Sequence[str], optional_sinks: Sequence[str] = ("email", "slack", "discord", "webhook")) -> NotificationSinkReport:
    enabled = tuple(str(sink) for sink in enabled_sinks)
    return NotificationSinkReport(enabled_sinks=enabled, optional_sinks=tuple(optional_sinks), local_sink_enabled="local" in enabled)


def build_deployment_health_check_report(statuses: Mapping[str, Any]) -> DeploymentHealthCheckReport:
    required = ("data_provider", "broker_rest", "broker_account_state", "websocket_stream", "storage", "scheduler", "artifact_write_path")
    return DeploymentHealthCheckReport(tuple(_health_check_status(name, statuses.get(name, False)) for name in required))


def build_readiness_page_refresh_report(
    source_artifacts: Sequence[str],
    readiness_page_path: str,
    refreshed: bool,
) -> ReadinessPageRefreshReport:
    sources = tuple(str(path) for path in source_artifacts)
    reason = "readiness_page_refreshed" if refreshed and sources and readiness_page_path else "readiness_page_refresh_incomplete"
    return ReadinessPageRefreshReport(sources, readiness_page_path, refreshed, reason)


def build_operator_inbox_report(rows: Sequence[Mapping[str, Any]]) -> OperatorInboxReport:
    return OperatorInboxReport(tuple(_operator_inbox_item(row) for row in rows))


def build_deployment_machine_rehearsal_report(row: Mapping[str, Any]) -> DeploymentMachineRehearsalReport:
    artifacts = tuple(str(path) for path in row.get("artifact_paths", ()) or ())
    environment = bool(row.get("environment_captured", False))
    scheduler = bool(row.get("scheduler_verified", False))
    state = bool(row.get("state_paths_verified", False))
    if not row.get("machine_id"):
        reason = "deployment_machine_id_missing"
    elif not artifacts:
        reason = "deployment_machine_artifacts_missing"
    elif not environment:
        reason = "deployment_environment_not_captured"
    elif not scheduler:
        reason = "deployment_scheduler_not_verified"
    elif not state:
        reason = "deployment_state_paths_not_verified"
    else:
        reason = "deployment_machine_rehearsal_passed"
    return DeploymentMachineRehearsalReport(
        machine_id=str(row.get("machine_id") or ""),
        profile_name=str(row.get("profile_name") or "unknown"),
        artifact_paths=artifacts,
        environment_captured=environment,
        scheduler_verified=scheduler,
        state_paths_verified=state,
        passed=reason == "deployment_machine_rehearsal_passed",
        reason=reason,
    )


def write_daily_operator_cycle_report(report: DailyOperatorCycleReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_windows_task_scheduler_config_report(report: WindowsTaskSchedulerConfigReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_gui_executable_packaging_report(report: GuiExecutablePackagingReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_service_entrypoint_report(report: ServiceEntrypointReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_process_supervision_report(report: ProcessSupervisionReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_job_lease_report(report: JobLeaseReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_command_idempotency_report(report: CommandIdempotencyReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_artifact_retention_report(report: ArtifactRetentionReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_secret_management_guidance_report(report: SecretManagementGuidanceReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_broker_audit_log_report(report: BrokerAuditLogReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_alert_routing_report(report: AlertRoutingReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_notification_sink_report(report: NotificationSinkReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_deployment_health_check_report(report: DeploymentHealthCheckReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_readiness_page_refresh_report(report: ReadinessPageRefreshReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_operator_inbox_report(report: OperatorInboxReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_deployment_machine_rehearsal_report(report: DeploymentMachineRehearsalReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def _daily_cycle_step(name: str, command: str, result: Mapping[str, Any]) -> DailyOperatorCycleStep:
    passed = bool(result.get("passed", False))
    required = bool(result.get("required", True))
    return DailyOperatorCycleStep(
        name=name,
        command=str(result.get("command") or command),
        required=required,
        passed=passed,
        artifact_path=str(result.get("artifact_path")) if result.get("artifact_path") else None,
        reason=str(result.get("reason") or ("passed" if passed else f"{name}_pending")),
    )


def _supervision_decision(row: Mapping[str, Any]) -> ProcessSupervisionDecision:
    job_type = str(row.get("job_type") or "monitor")
    restart_allowed = bool(row.get("restart_allowed", job_type in {"monitor", "report", "schedule"}))
    max_restarts = int(row.get("max_restarts", 3 if restart_allowed else 0) or 0)
    if job_type == "order_submission" and restart_allowed:
        reason = "order_submission_auto_restart_forbidden"
    elif restart_allowed:
        reason = "safe_job_restart_allowed"
    else:
        reason = "restart_disabled"
    return ProcessSupervisionDecision(
        job_name=str(row.get("job_name") or row.get("name") or "job"),
        job_type=job_type,
        restart_allowed=restart_allowed,
        max_restarts=max_restarts,
        reason=reason,
    )


def _job_lease_decision(row: Mapping[str, Any], active: Mapping[str, Any], observed: datetime, ttl_seconds: int) -> JobLeaseDecision:
    job_name = str(row.get("job_name") or row.get("name") or "job")
    lease_key = str(row.get("lease_key") or job_name)
    existing_expiry = _parse_datetime(active.get(lease_key))
    if existing_expiry and existing_expiry > observed:
        acquired = False
        expires_at = existing_expiry.isoformat()
        reason = "job_lease_already_active"
    else:
        acquired = True
        expires_at = (observed + timedelta(seconds=ttl_seconds)).isoformat()
        reason = "job_lease_acquired"
    return JobLeaseDecision(job_name, lease_key, acquired, expires_at, reason)


def _idempotency_key(row: Mapping[str, Any], seen: set[str]) -> CommandIdempotencyKey:
    command = str(row.get("command_name") or row.get("command") or "command")
    run_date = str(row.get("run_date") or _date_text(datetime.now(timezone.utc)))
    scope = str(row.get("scope") or row.get("symbol") or "global")
    key = str(row.get("key") or f"{command}:{run_date}:{scope}")
    duplicate = key in seen
    return CommandIdempotencyKey(
        command_name=command,
        run_date=run_date,
        scope=scope,
        key=key,
        duplicate=duplicate,
        reason="command_idempotency_duplicate" if duplicate else "command_idempotency_key_available",
    )


def _artifact_retention_decision(row: Mapping[str, Any], retention_days: int, evidence_retention_days: int) -> ArtifactRetentionDecision:
    path = str(row.get("path") or row.get("artifact_path") or "")
    age_days = int(row.get("age_days", 0) or 0)
    preserve = bool(row.get("preserve_for_live_readiness", row.get("required_evidence", False)))
    if preserve and age_days <= evidence_retention_days:
        action = "preserve"
        reason = "live_readiness_evidence_preserved"
    elif age_days > retention_days:
        action = "archive"
        reason = "artifact_archive_due"
    else:
        action = "keep"
        reason = "artifact_within_retention"
    return ArtifactRetentionDecision(path, age_days, action, preserve, reason)


def _secret_check(name: str, passed: bool, failure_reason: str, config: Mapping[str, Any]) -> SecretManagementCheck:
    return SecretManagementCheck(name, passed, "passed" if passed else failure_reason, {"profile": config.get("profile", "local")})


def _broker_audit_log_entry(row: Mapping[str, Any]) -> BrokerAuditLogEntry:
    evidence_paths = tuple(str(path) for path in row.get("evidence_paths", ()) or ())
    return BrokerAuditLogEntry(
        run_id=str(row.get("run_id") or ""),
        command=str(row.get("command") or ""),
        config_hash=str(row.get("config_hash") or ""),
        evidence_paths=evidence_paths,
        decision_status=str(row.get("decision_status") or ""),
        broker_touched=bool(row.get("broker_touched", False)),
        reason=str(row.get("reason") or "broker_audit_log_recorded"),
    )


def _alert_routing_decision(row: Mapping[str, Any]) -> AlertRoutingDecision:
    sink = str(row.get("sink") or "")
    routed = bool(row.get("routed", bool(sink)))
    if not routed:
        reason = "alert_route_missing"
    else:
        reason = "alert_route_ready"
    return AlertRoutingDecision(
        alert_type=str(row.get("alert_type") or row.get("type") or "alert"),
        severity=str(row.get("severity") or "info"),
        sink=sink,
        routed=routed,
        reason=reason,
    )


def _health_check_status(name: str, value: Any) -> DeploymentHealthCheckStatus:
    if isinstance(value, Mapping):
        healthy = bool(value.get("healthy", value.get("passed", False)))
        reason = str(value.get("reason") or ("healthy" if healthy else f"{name}_unhealthy"))
    else:
        healthy = bool(value)
        reason = "healthy" if healthy else f"{name}_unhealthy"
    return DeploymentHealthCheckStatus(name, healthy, reason)


def _operator_inbox_item(row: Mapping[str, Any]) -> OperatorInboxItem:
    return OperatorInboxItem(
        name=str(row.get("name") or row.get("item") or "review_item"),
        severity=str(row.get("severity") or "info"),
        action=str(row.get("action") or "review"),
        source_artifact=str(row.get("source_artifact")) if row.get("source_artifact") else None,
        resolved=bool(row.get("resolved", False)),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _date_text(value: datetime) -> str:
    return value.date().isoformat()


def _write_report(payload: dict, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)
