from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REQUIRED_DAEMON_RESTART_DRILLS = (
    "clean_stop_resume",
    "stale_lock_replacement",
    "kill_switch_resume",
    "duplicate_client_order_id_guard",
)


DEFAULT_DAEMON_CAPTURE_WINDOWS = (
    ("market_open", "08:30", "10:00"),
    ("intraday", "10:00", "14:30"),
    ("market_close", "14:30", "15:15"),
)


@dataclass(frozen=True)
class PaperDaemonRecoveryReport:
    state_path: str
    lock_path: str
    status: str
    iteration: int | None
    last_reason: str
    last_error: str | None
    last_heartbeat_at: str | None
    heartbeat_age_seconds: float | None
    stale_heartbeat: bool
    unresolved_running_state: bool
    lock_active: bool
    lock_stale: bool
    recommended_action: str

    @property
    def recovery_required(self) -> bool:
        return bool(
            self.unresolved_running_state
            or self.stale_heartbeat
            or self.lock_active
            or self.last_error
        )

    @property
    def passed(self) -> bool:
        return not self.recovery_required

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "recovery_required": self.recovery_required,
            "state_path": self.state_path,
            "lock_path": self.lock_path,
            "status": self.status,
            "iteration": self.iteration,
            "last_reason": self.last_reason,
            "last_error": self.last_error,
            "last_heartbeat_at": self.last_heartbeat_at,
            "heartbeat_age_seconds": self.heartbeat_age_seconds,
            "stale_heartbeat": self.stale_heartbeat,
            "unresolved_running_state": self.unresolved_running_state,
            "lock_active": self.lock_active,
            "lock_stale": self.lock_stale,
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True)
class PaperDaemonDailySummaryReport:
    report_date: str
    daemon_status: str
    latest_reason: str
    total_iterations: int
    passed_iterations: int
    failed_iterations: int
    skipped_iterations: int
    submitted_iterations: int
    cleanup_planned_orders: int
    cleanup_submitted_orders: int
    monitor_failed_iterations: int
    monitor_stale_open_orders: int
    monitor_position_mismatches: int
    data_parity_failed_iterations: int
    data_parity_failed_checks: int
    active_windows: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_action: str

    @property
    def passed(self) -> bool:
        return self.failed_iterations == 0 and self.daemon_status not in {"error", "lock_active"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "report_date": self.report_date,
            "daemon_status": self.daemon_status,
            "latest_reason": self.latest_reason,
            "total_iterations": self.total_iterations,
            "passed_iterations": self.passed_iterations,
            "failed_iterations": self.failed_iterations,
            "skipped_iterations": self.skipped_iterations,
            "submitted_iterations": self.submitted_iterations,
            "cleanup_planned_orders": self.cleanup_planned_orders,
            "cleanup_submitted_orders": self.cleanup_submitted_orders,
            "monitor_failed_iterations": self.monitor_failed_iterations,
            "monitor_stale_open_orders": self.monitor_stale_open_orders,
            "monitor_position_mismatches": self.monitor_position_mismatches,
            "data_parity_failed_iterations": self.data_parity_failed_iterations,
            "data_parity_failed_checks": self.data_parity_failed_checks,
            "active_windows": list(self.active_windows),
            "artifact_paths": list(self.artifact_paths),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True)
class PaperDaemonNotificationEvent:
    event_type: str
    severity: str
    message: str
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "severity": self.severity,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperDaemonNotificationReport:
    events: tuple[PaperDaemonNotificationEvent, ...]
    sinks: tuple[str, ...] = ("local",)

    @property
    def passed(self) -> bool:
        return not any(event.severity in {"critical", "error"} for event in self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "sinks": list(self.sinks),
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True)
class PaperDaemonRetentionCandidate:
    path: str
    exists: bool
    age_days: float | None
    action: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "age_days": self.age_days,
            "action": self.action,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperDaemonRetentionPlan:
    keep_days: int
    preserve_recent: int
    candidates: tuple[PaperDaemonRetentionCandidate, ...]

    @property
    def delete_count(self) -> int:
        return sum(1 for candidate in self.candidates if candidate.action == "delete")

    @property
    def passed(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "keep_days": self.keep_days,
            "preserve_recent": self.preserve_recent,
            "delete_count": self.delete_count,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class PaperDaemonNotionalDecisionReport:
    current_notional: float
    recommended_notional: float
    action: str
    reason: str
    triggers: tuple[str, ...]
    clean_iterations: int
    submitted_iterations: int
    required_clean_iterations: int
    evidence: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return self.action != "downshift"

    @property
    def downshifted(self) -> bool:
        return self.recommended_notional < self.current_notional

    @property
    def escalated(self) -> bool:
        return self.recommended_notional > self.current_notional

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "current_notional": self.current_notional,
            "recommended_notional": self.recommended_notional,
            "action": self.action,
            "reason": self.reason,
            "triggers": list(self.triggers),
            "clean_iterations": self.clean_iterations,
            "submitted_iterations": self.submitted_iterations,
            "required_clean_iterations": self.required_clean_iterations,
            "downshifted": self.downshifted,
            "escalated": self.escalated,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperDaemonRestartDrillResult:
    name: str
    passed: bool
    reason: str
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperDaemonRestartDrillReport:
    drills: tuple[PaperDaemonRestartDrillResult, ...]
    duplicate_client_order_ids: tuple[str, ...] = ()

    @property
    def missing_drills(self) -> tuple[str, ...]:
        passed = {drill.name for drill in self.drills if drill.passed}
        return tuple(name for name in REQUIRED_DAEMON_RESTART_DRILLS if name not in passed)

    @property
    def passed(self) -> bool:
        return not self.missing_drills

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "required_drills": list(REQUIRED_DAEMON_RESTART_DRILLS),
            "missing_drills": list(self.missing_drills),
            "duplicate_client_order_ids": list(self.duplicate_client_order_ids),
            "drills": [drill.to_dict() for drill in self.drills],
        }


@dataclass(frozen=True)
class PaperDaemonActivationChecklistReport:
    checks: Mapping[str, bool]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_action: str
    evidence: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return all(self.checks.values()) and not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": dict(self.checks),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperExposureAcknowledgementTemplateReport:
    acknowledged: bool
    source_artifact: str | None
    symbols: tuple[str, ...]
    observed_positions: int
    observed_notional: float
    max_positions: int
    suggested_max_notional: float
    expires_at: str | None
    instructions: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "acknowledged": self.acknowledged,
            "source_artifact": self.source_artifact,
            "symbols": list(self.symbols),
            "observed_positions": self.observed_positions,
            "observed_notional": self.observed_notional,
            "max_positions": self.max_positions,
            "max_notional": self.suggested_max_notional,
            "expires_at": self.expires_at,
            "instructions": list(self.instructions),
        }


@dataclass(frozen=True)
class PaperDaemonSoakActivationEvidence:
    path: str | None
    passed: bool
    active_window: str | None
    submitted_iterations: int
    observed_notional: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "passed": self.passed,
            "active_window": self.active_window,
            "submitted_iterations": self.submitted_iterations,
            "observed_notional": self.observed_notional,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PaperDaemonSupervisedSoakReport:
    activations: tuple[PaperDaemonSoakActivationEvidence, ...]
    required_clean_activations: int
    required_active_windows: int
    require_submitted_iterations: bool
    max_total_observed_notional: float | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_action: str

    @property
    def clean_activations(self) -> int:
        return sum(1 for activation in self.activations if activation.passed)

    @property
    def submitted_activations(self) -> int:
        return sum(1 for activation in self.activations if activation.submitted_iterations > 0)

    @property
    def active_windows(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                activation.active_window
                for activation in self.activations
                if activation.active_window
            )
        )

    @property
    def total_observed_notional(self) -> float:
        return sum(activation.observed_notional for activation in self.activations)

    @property
    def passed(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "clean_activations": self.clean_activations,
            "submitted_activations": self.submitted_activations,
            "active_windows": list(self.active_windows),
            "total_observed_notional": self.total_observed_notional,
            "required_clean_activations": self.required_clean_activations,
            "required_active_windows": self.required_active_windows,
            "require_submitted_iterations": self.require_submitted_iterations,
            "max_total_observed_notional": self.max_total_observed_notional,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
            "activations": [activation.to_dict() for activation in self.activations],
        }


@dataclass(frozen=True)
class PaperPositionStewardshipLine:
    symbol: str
    status: str
    owner_type: str
    expected_quantity: float
    observed_quantity: float
    market_value: float | None
    age_hours: float | None
    forced_exit_needed: bool
    closure_evidence_present: bool
    action: str

    @property
    def passed(self) -> bool:
        if self.forced_exit_needed:
            return self.closure_evidence_present
        return self.status in {"fresh", "active"} and self.owner_type not in {"", "unknown_broker_position"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "passed": self.passed,
            "status": self.status,
            "owner_type": self.owner_type,
            "expected_quantity": self.expected_quantity,
            "observed_quantity": self.observed_quantity,
            "market_value": self.market_value,
            "age_hours": self.age_hours,
            "forced_exit_needed": self.forced_exit_needed,
            "closure_evidence_present": self.closure_evidence_present,
            "action": self.action,
        }


@dataclass(frozen=True)
class PaperPositionStewardshipReport:
    monitor_passed: bool
    max_active_age_hours: float
    positions: tuple[PaperPositionStewardshipLine, ...]
    closed_symbols: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_action: str

    @property
    def passed(self) -> bool:
        return not self.blockers

    @property
    def active_positions(self) -> int:
        return sum(1 for position in self.positions if position.status in {"fresh", "active"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "monitor_passed": self.monitor_passed,
            "max_active_age_hours": self.max_active_age_hours,
            "active_positions": self.active_positions,
            "closed_symbols": list(self.closed_symbols),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
            "positions": [position.to_dict() for position in self.positions],
        }


@dataclass(frozen=True)
class PaperDaemonFlattenDrillReport:
    checks: Mapping[str, bool]
    target_symbols: tuple[str, ...]
    closed_symbols: tuple[str, ...]
    submitted_orders: int
    filled_orders: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_action: str
    evidence: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return all(self.checks.values()) and not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": dict(self.checks),
            "target_symbols": list(self.target_symbols),
            "closed_symbols": list(self.closed_symbols),
            "submitted_orders": self.submitted_orders,
            "filled_orders": self.filled_orders,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperDaemonSoakReadinessRollupReport:
    checks: Mapping[str, bool]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_action: str
    evidence: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return all(self.checks.values()) and not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": dict(self.checks),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperDaemonWindowCaptureTarget:
    name: str
    start_time: str
    end_time: str
    captured: bool
    clean: bool
    submitted: bool
    action: str
    command: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "captured": self.captured,
            "clean": self.clean,
            "submitted": self.submitted,
            "action": self.action,
            "command": list(self.command),
        }


@dataclass(frozen=True)
class PaperDaemonWindowCapturePlanReport:
    targets: tuple[PaperDaemonWindowCaptureTarget, ...]
    required_clean_activations: int
    required_active_windows: int
    clean_activations: int
    submitted_activations: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_action: str

    @property
    def captured_windows(self) -> tuple[str, ...]:
        return tuple(target.name for target in self.targets if target.clean and target.submitted)

    @property
    def missing_windows(self) -> tuple[str, ...]:
        return tuple(target.name for target in self.targets if target.action == "capture_next")

    @property
    def passed(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "captured_windows": list(self.captured_windows),
            "missing_windows": list(self.missing_windows),
            "required_clean_activations": self.required_clean_activations,
            "required_active_windows": self.required_active_windows,
            "clean_activations": self.clean_activations,
            "submitted_activations": self.submitted_activations,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
            "targets": [target.to_dict() for target in self.targets],
        }


def build_paper_daemon_recovery_report(
    state_path: str | Path = "runs/paper-daemon-state.json",
    lock_path: str | Path = "runs/paper-daemon.lock",
    *,
    now: datetime | None = None,
    stale_after_seconds: float = 900.0,
) -> PaperDaemonRecoveryReport:
    now = _utc_now(now)
    state = _load_json_mapping(state_path, default={"status": "missing"})
    lock = _load_json_mapping(lock_path, default={})

    status = str(state.get("status") or "missing")
    last_reason = str(state.get("last_reason") or state.get("reason") or "unknown")
    last_error = _optional_str(state.get("last_error"))
    heartbeat_at = _parse_time(state.get("last_heartbeat_at"))
    heartbeat_age = _age_seconds(heartbeat_at, now)
    stale_heartbeat = heartbeat_age is not None and heartbeat_age > stale_after_seconds
    unresolved_running_state = status == "running"
    lock_active = Path(lock_path).exists()
    lock_acquired_at = _parse_time(lock.get("acquired_at"))
    lock_age = _age_seconds(lock_acquired_at, now)
    lock_stale = lock_active and lock_age is not None and lock_age > stale_after_seconds

    return PaperDaemonRecoveryReport(
        state_path=str(state_path),
        lock_path=str(lock_path),
        status=status,
        iteration=_optional_int(state.get("iteration")),
        last_reason=last_reason,
        last_error=last_error,
        last_heartbeat_at=heartbeat_at.isoformat() if heartbeat_at else None,
        heartbeat_age_seconds=heartbeat_age,
        stale_heartbeat=stale_heartbeat,
        unresolved_running_state=unresolved_running_state,
        lock_active=lock_active,
        lock_stale=lock_stale,
        recommended_action=_recovery_action(
            status=status,
            last_error=last_error,
            stale_heartbeat=stale_heartbeat,
            unresolved_running_state=unresolved_running_state,
            lock_active=lock_active,
            lock_stale=lock_stale,
        ),
    )


def build_paper_daemon_daily_summary_report(
    daemon_report: Mapping[str, Any] | Any,
    *,
    report_date: str | None = None,
) -> PaperDaemonDailySummaryReport:
    payload = _payload(daemon_report)
    state = _mapping(payload.get("state"))
    iterations = tuple(_mapping(item) for item in _sequence(payload.get("iterations")))
    daemon_status = str(state.get("status") or "unknown")
    latest_reason = str(state.get("last_reason") or state.get("reason") or "unknown")

    passed_iterations = sum(1 for item in iterations if bool(item.get("passed")))
    skipped_iterations = sum(1 for item in iterations if item.get("status") == "skipped")
    submitted_iterations = sum(1 for item in iterations if bool(item.get("submitted")))
    cleanup_planned_orders = sum(_int_value(item.get("cleanup_planned_orders")) for item in iterations)
    cleanup_submitted_orders = sum(_int_value(item.get("cleanup_submitted_orders")) for item in iterations)
    monitor_failed_iterations = sum(1 for item in iterations if item.get("monitor_passed") is False)
    monitor_stale_open_orders = sum(_int_value(item.get("monitor_stale_open_orders")) for item in iterations)
    monitor_position_mismatches = sum(_int_value(item.get("monitor_position_mismatches")) for item in iterations)
    data_parity_failed_iterations = sum(1 for item in iterations if item.get("data_parity_passed") is False)
    data_parity_failed_checks = sum(_int_value(item.get("data_parity_failed_checks")) for item in iterations)
    failed_iterations = sum(
        1
        for item in iterations
        if not bool(item.get("passed")) and item.get("status") != "skipped"
    )
    active_windows = tuple(
        dict.fromkeys(str(item.get("active_window")) for item in iterations if item.get("active_window"))
    )
    artifact_paths = _collect_artifact_paths(payload, iterations)
    warnings = _daily_summary_warnings(
        daemon_status=daemon_status,
        failed_iterations=failed_iterations,
        submitted_iterations=submitted_iterations,
        cleanup_planned_orders=cleanup_planned_orders,
        monitor_failed_iterations=monitor_failed_iterations,
        monitor_stale_open_orders=monitor_stale_open_orders,
        monitor_position_mismatches=monitor_position_mismatches,
        data_parity_failed_iterations=data_parity_failed_iterations,
        data_parity_failed_checks=data_parity_failed_checks,
        last_error=_optional_str(state.get("last_error")),
    )

    return PaperDaemonDailySummaryReport(
        report_date=report_date or _today_utc(),
        daemon_status=daemon_status,
        latest_reason=latest_reason,
        total_iterations=len(iterations),
        passed_iterations=passed_iterations,
        failed_iterations=failed_iterations,
        skipped_iterations=skipped_iterations,
        submitted_iterations=submitted_iterations,
        cleanup_planned_orders=cleanup_planned_orders,
        cleanup_submitted_orders=cleanup_submitted_orders,
        monitor_failed_iterations=monitor_failed_iterations,
        monitor_stale_open_orders=monitor_stale_open_orders,
        monitor_position_mismatches=monitor_position_mismatches,
        data_parity_failed_iterations=data_parity_failed_iterations,
        data_parity_failed_checks=data_parity_failed_checks,
        active_windows=active_windows,
        artifact_paths=artifact_paths,
        warnings=warnings,
        recommended_action=_daily_summary_action(daemon_status, failed_iterations, warnings),
    )


def build_paper_daemon_notification_report(
    daemon_state: Mapping[str, Any],
    *,
    recovery_report: PaperDaemonRecoveryReport | Mapping[str, Any] | None = None,
    sinks: Sequence[str] = ("local",),
) -> PaperDaemonNotificationReport:
    state = _mapping(daemon_state)
    recovery = _payload(recovery_report) if recovery_report is not None else {}
    events: list[PaperDaemonNotificationEvent] = []

    status = str(state.get("status") or "unknown")
    if status == "kill_switch_active":
        events.append(
            PaperDaemonNotificationEvent(
                "kill_switch_active",
                "warning",
                "Paper daemon kill switch is active.",
                {"reason": state.get("last_reason") or state.get("reason")},
            )
        )
    if status == "error" or state.get("last_error"):
        events.append(
            PaperDaemonNotificationEvent(
                "daemon_error",
                "critical",
                "Paper daemon recorded an error.",
                {"last_error": state.get("last_error"), "reason": state.get("last_reason")},
            )
        )

    if bool(recovery.get("stale_heartbeat")):
        events.append(
            PaperDaemonNotificationEvent(
                "stale_heartbeat",
                "warning",
                "Paper daemon heartbeat is stale.",
                {"heartbeat_age_seconds": recovery.get("heartbeat_age_seconds")},
            )
        )
    if bool(recovery.get("lock_active")):
        severity = "critical" if bool(recovery.get("lock_stale")) else "warning"
        events.append(
            PaperDaemonNotificationEvent(
                "daemon_lock_active",
                severity,
                "Paper daemon lock is active.",
                {"lock_path": recovery.get("lock_path"), "lock_stale": recovery.get("lock_stale")},
            )
        )

    return PaperDaemonNotificationReport(events=tuple(events), sinks=tuple(sinks))


def build_paper_daemon_notional_decision_report(
    daemon_evidence: Mapping[str, Any] | Any,
    *,
    current_notional: float = 25.0,
    required_clean_iterations: int = 10,
    tiers: Sequence[float] = (25.0, 50.0, 100.0, 250.0, 500.0, 1_000.0),
) -> PaperDaemonNotionalDecisionReport:
    if current_notional <= 0:
        raise ValueError("current_notional must be positive.")
    if required_clean_iterations <= 0:
        raise ValueError("required_clean_iterations must be positive.")
    evidence = _daemon_notional_evidence(daemon_evidence)
    triggers = _daemon_notional_triggers(evidence)
    clean_iterations = _int_value(evidence.get("passed_iterations"))
    submitted_iterations = _int_value(evidence.get("submitted_iterations"))

    if triggers:
        recommended = _previous_tier(current_notional, tiers)
        return PaperDaemonNotionalDecisionReport(
            current_notional=current_notional,
            recommended_notional=recommended,
            action="downshift" if recommended < current_notional else "hold",
            reason="_".join(triggers),
            triggers=triggers,
            clean_iterations=clean_iterations,
            submitted_iterations=submitted_iterations,
            required_clean_iterations=required_clean_iterations,
            evidence=evidence,
        )

    if clean_iterations >= required_clean_iterations and submitted_iterations > 0:
        recommended = _next_tier(current_notional, tiers)
        action = "escalate" if recommended > current_notional else "hold"
        reason = "clean_daemon_evidence_supports_next_tier" if action == "escalate" else "already_at_max_daemon_notional_tier"
    else:
        recommended = current_notional
        action = "hold"
        reason = "requires_clean_submitted_daemon_iterations"

    return PaperDaemonNotionalDecisionReport(
        current_notional=current_notional,
        recommended_notional=recommended,
        action=action,
        reason=reason,
        triggers=(),
        clean_iterations=clean_iterations,
        submitted_iterations=submitted_iterations,
        required_clean_iterations=required_clean_iterations,
        evidence=evidence,
    )


def build_paper_daemon_restart_drill_report(
    drill_evidence: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    order_artifacts: Sequence[Mapping[str, Any]] = (),
) -> PaperDaemonRestartDrillReport:
    payload = _payload(drill_evidence)
    records = _restart_drill_records(drill_evidence)
    embedded_orders = tuple(_mapping(item) for item in _sequence(payload.get("order_artifacts")))
    duplicate_check = _duplicate_client_order_id_check(tuple(order_artifacts) + embedded_orders)
    by_name = {str(record.get("name") or ""): record for record in records}
    drills = tuple(
        _restart_drill_result(
            name,
            by_name.get(name),
            duplicate_check=duplicate_check,
        )
        for name in REQUIRED_DAEMON_RESTART_DRILLS
    )
    return PaperDaemonRestartDrillReport(
        drills=drills,
        duplicate_client_order_ids=tuple(duplicate_check["duplicates"]),
    )


def build_paper_daemon_activation_checklist_report(
    daemon_evidence: Mapping[str, Any] | Any,
    *,
    daily_summary: Mapping[str, Any] | Any | None = None,
    command_center: Mapping[str, Any] | Any | None = None,
    kill_switch_proof: Mapping[str, Any] | Any | None = None,
    cleanup_evidence: Mapping[str, Any] | Any | None = None,
    acknowledged_exposure: Mapping[str, Any] | Any | None = None,
    require_submitted_iteration: bool = True,
    now: datetime | None = None,
) -> PaperDaemonActivationChecklistReport:
    now = _utc_now(now)
    daemon = _payload(daemon_evidence)
    summary = _payload(daily_summary) if daily_summary is not None else build_paper_daemon_daily_summary_report(daemon).to_dict()
    center = _payload(command_center)
    kill_proof = _payload(kill_switch_proof)
    cleanup = _payload(cleanup_evidence)
    exposure_ack = _payload(acknowledged_exposure)
    state = _mapping(daemon.get("state"))
    iterations = tuple(_mapping(item) for item in _sequence(daemon.get("iterations")))
    paper = _mapping(center.get("paper"))
    daemon_panel = _mapping(center.get("daemon"))

    submitted_iterations = _int_value(summary.get("submitted_iterations"))
    monitor_failures = _int_value(summary.get("monitor_failed_iterations"))
    position_mismatches = _int_value(summary.get("monitor_position_mismatches"))
    stale_open_orders = _int_value(summary.get("monitor_stale_open_orders"))
    cleanup_planned = _int_value(summary.get("cleanup_planned_orders"))
    cleanup_submitted = _int_value(summary.get("cleanup_submitted_orders"))
    data_parity_failures = _int_value(summary.get("data_parity_failed_iterations")) + _int_value(summary.get("data_parity_failed_checks"))
    observed_positions = _int_value(paper.get("observed_positions"))
    observed_notional = _float_value(paper.get("observed_notional"))
    command_center_monitor_clean = str(paper.get("monitor_status") or "").lower() == "passed"
    exposure_acknowledged = _exposure_acknowledgement_passed(
        exposure_ack,
        observed_positions=observed_positions,
        observed_notional=observed_notional,
        now=now,
    )
    position_monitor_clean = (monitor_failures == 0 and position_mismatches == 0) or command_center_monitor_clean
    cleanup_resolved = (
        position_monitor_clean
        or (_cleanup_evidence_resolved(cleanup) if cleanup else cleanup_planned == cleanup_submitted)
    )

    checks = {
        "daemon_completed_without_error": str(summary.get("daemon_status") or state.get("status") or "") in {"completed", "stopped"}
        and not _optional_str(state.get("last_error")),
        "heartbeat_fresh_or_completed": str(summary.get("daemon_status") or state.get("status") or "") in {"completed", "stopped"}
        or str(daemon_panel.get("heartbeat_state") or "fresh") in {"fresh", "missing"},
        "kill_switch_clear_after_proof": not bool(daemon_panel.get("kill_switch_active")),
        "kill_switch_proof_passed": _kill_switch_proof_passed(kill_proof),
        "broker_monitor_clean": (position_monitor_clean or exposure_acknowledged) and stale_open_orders == 0,
        "cleanup_review_resolved": cleanup_resolved or exposure_acknowledged,
        "paper_exposure_acknowledged": position_monitor_clean and cleanup_resolved or exposure_acknowledged,
        "data_parity_clean": data_parity_failures == 0,
        "active_submit_observed": submitted_iterations > 0 or not require_submitted_iteration,
    }
    blockers = tuple(name for name, passed in checks.items() if not passed)
    warnings = _activation_warnings(
        _sequence(summary.get("warnings")) + _sequence(center.get("warnings")),
        position_monitor_clean=position_monitor_clean,
        cleanup_resolved=cleanup_resolved,
        active_submit_observed=submitted_iterations > 0 or not require_submitted_iteration,
    )
    evidence = {
        "daemon_status": summary.get("daemon_status") or state.get("status"),
        "latest_reason": summary.get("latest_reason") or state.get("last_reason"),
        "total_iterations": summary.get("total_iterations", len(iterations)),
        "submitted_iterations": submitted_iterations,
        "monitor_failed_iterations": monitor_failures,
        "monitor_position_mismatches": position_mismatches,
        "monitor_stale_open_orders": stale_open_orders,
        "cleanup_planned_orders": cleanup_planned,
        "cleanup_submitted_orders": cleanup_submitted,
        "latest_cleanup_reason": cleanup.get("reason"),
        "latest_cleanup_submitted": cleanup.get("submitted"),
        "latest_cleanup_attempted": cleanup.get("attempted"),
        "latest_cleanup_planned_orders": len(_sequence(cleanup.get("planned_orders"))) if cleanup else None,
        "latest_cleanup_artifact": cleanup.get("artifact_path"),
        "observed_positions": observed_positions,
        "observed_notional": observed_notional,
        "paper_exposure_acknowledged": exposure_acknowledged,
        "paper_exposure_acknowledgement_reason": _exposure_acknowledgement_reason(
            exposure_ack,
            observed_positions=observed_positions,
            observed_notional=observed_notional,
            now=now,
        ),
        "data_parity_failed_iterations": summary.get("data_parity_failed_iterations"),
        "data_parity_failed_checks": summary.get("data_parity_failed_checks"),
        "command_center_passed": center.get("passed"),
        "command_center_monitor_status": paper.get("monitor_status"),
        "kill_switch_proof_passed": kill_proof.get("passed"),
        "artifact_paths": list(_sequence(summary.get("artifact_paths")) + _sequence(daemon.get("artifact_path"))),
    }
    return PaperDaemonActivationChecklistReport(
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        recommended_action=_activation_action(blockers, warnings, cleanup_reason=_optional_str(cleanup.get("reason"))),
        evidence=evidence,
    )


def build_paper_exposure_acknowledgement_template_report(
    cleanup_evidence: Mapping[str, Any] | Any,
    *,
    max_notional_buffer_pct: float = 20.0,
    expires_at: str | None = None,
) -> PaperExposureAcknowledgementTemplateReport:
    cleanup = _payload(cleanup_evidence)
    positions = tuple(_mapping(item) for item in _sequence(cleanup.get("positions_seen")))
    symbols = tuple(str(position.get("symbol") or "").upper() for position in positions if position.get("symbol"))
    observed_notional = sum(abs(_float_value(position.get("market_value"))) for position in positions)
    buffer_multiplier = 1.0 + max(max_notional_buffer_pct, 0.0) / 100.0
    suggested_max_notional = round(observed_notional * buffer_multiplier, 2)
    return PaperExposureAcknowledgementTemplateReport(
        acknowledged=False,
        source_artifact=_optional_str(cleanup.get("artifact_path")),
        symbols=tuple(dict.fromkeys(symbols)),
        observed_positions=len(positions),
        observed_notional=round(observed_notional, 6),
        max_positions=len(positions),
        suggested_max_notional=suggested_max_notional,
        expires_at=expires_at,
        instructions=(
            "Review the source cleanup artifact and Alpaca paper account before use.",
            "Change acknowledged to true only after operator approval.",
            "Keep max_positions, max_notional, and expires_at tight; expired or over-limit exposure will not satisfy activation checks.",
        ),
    )


def build_paper_daemon_supervised_soak_report(
    activation_reports: Sequence[Mapping[str, Any] | Any],
    *,
    required_clean_activations: int = 3,
    required_active_windows: int = 2,
    require_submitted_iterations: bool = True,
    max_total_observed_notional: float | None = None,
) -> PaperDaemonSupervisedSoakReport:
    if required_clean_activations <= 0:
        raise ValueError("required_clean_activations must be positive.")
    if required_active_windows <= 0:
        raise ValueError("required_active_windows must be positive.")
    activations = tuple(_soak_activation_evidence(item) for item in activation_reports)
    blockers = _supervised_soak_blockers(
        activations,
        required_clean_activations=required_clean_activations,
        required_active_windows=required_active_windows,
        require_submitted_iterations=require_submitted_iterations,
        max_total_observed_notional=max_total_observed_notional,
    )
    warnings = tuple(
        dict.fromkeys(
            warning
            for activation in activations
            for warning in activation.warnings
        )
    )
    return PaperDaemonSupervisedSoakReport(
        activations=activations,
        required_clean_activations=required_clean_activations,
        required_active_windows=required_active_windows,
        require_submitted_iterations=require_submitted_iterations,
        max_total_observed_notional=max_total_observed_notional,
        blockers=blockers,
        warnings=warnings,
        recommended_action=_supervised_soak_action(blockers),
    )


def build_paper_position_stewardship_report(
    monitor_evidence: Mapping[str, Any] | Any,
    *,
    cleanup_evidence: Mapping[str, Any] | Any | None = None,
    max_active_age_hours: float = 72.0,
) -> PaperPositionStewardshipReport:
    if max_active_age_hours <= 0:
        raise ValueError("max_active_age_hours must be positive.")
    monitor = _payload(monitor_evidence)
    cleanup = _payload(cleanup_evidence)
    lifecycle = _mapping(monitor.get("lifecycle"))
    lines = tuple(
        _stewardship_line(
            _mapping(position),
            cleanup,
            max_active_age_hours=max_active_age_hours,
        )
        for position in _sequence(lifecycle.get("positions"))
        if isinstance(position, Mapping)
    )
    closed_symbols = tuple(str(symbol) for symbol in _sequence(monitor.get("closed_symbols")) if symbol)
    blockers = _stewardship_blockers(monitor, lines)
    warnings = _stewardship_warnings(lines, max_active_age_hours=max_active_age_hours)
    return PaperPositionStewardshipReport(
        monitor_passed=bool(monitor.get("passed")),
        max_active_age_hours=max_active_age_hours,
        positions=lines,
        closed_symbols=closed_symbols,
        blockers=blockers,
        warnings=warnings,
        recommended_action=_stewardship_action(blockers, lines),
    )


def build_paper_daemon_flatten_drill_report(
    pre_monitor: Mapping[str, Any] | Any,
    flatten_plan: Mapping[str, Any] | Any,
    cleanup_submit: Mapping[str, Any] | Any,
    post_monitor: Mapping[str, Any] | Any,
    stewardship: Mapping[str, Any] | Any | None = None,
) -> PaperDaemonFlattenDrillReport:
    pre = _payload(pre_monitor)
    plan = _payload(flatten_plan)
    cleanup = _payload(cleanup_submit)
    post = _payload(post_monitor)
    stewardship_payload = _payload(stewardship)
    target_symbols = _flatten_target_symbols(plan, cleanup)
    closed_symbols = tuple(str(symbol).upper() for symbol in _sequence(post.get("closed_symbols")) if symbol)
    submitted_orders = tuple(_mapping(order) for order in _sequence(cleanup.get("submitted_orders")))
    filled_orders = tuple(
        order
        for order in submitted_orders
        if str(order.get("status") or "").upper() in {"FILLED", "PARTIALLY_FILLED"}
    )
    checks = {
        "pre_monitor_passed": bool(pre.get("passed")),
        "flatten_plan_passed": bool(plan.get("passed")) and bool(_sequence(plan.get("orders"))),
        "cleanup_submitted": bool(cleanup.get("submitted")) and bool(cleanup.get("attempted")) and bool(submitted_orders),
        "cleanup_reconciled": cleanup.get("reconciliation_clean") is True,
        "cleanup_filled": bool(submitted_orders) and len(filled_orders) == len(submitted_orders),
        "post_monitor_flat": _post_monitor_flat(post),
        "closed_symbols_recorded": bool(target_symbols) and set(target_symbols).issubset(set(closed_symbols)),
        "stewardship_passed": not stewardship_payload or bool(stewardship_payload.get("passed")),
    }
    blockers = tuple(name for name, passed in checks.items() if not passed)
    warnings = _flatten_drill_warnings(pre, plan, cleanup, post, stewardship_payload)
    return PaperDaemonFlattenDrillReport(
        checks=checks,
        target_symbols=target_symbols,
        closed_symbols=closed_symbols,
        submitted_orders=len(submitted_orders),
        filled_orders=len(filled_orders),
        blockers=blockers,
        warnings=warnings,
        recommended_action=_flatten_drill_action(blockers),
        evidence={
            "pre_monitor_artifact": _optional_str(pre.get("artifact_path")),
            "flatten_plan_artifact": _optional_str(plan.get("artifact_path")),
            "cleanup_artifact": _optional_str(cleanup.get("artifact_path")),
            "post_monitor_artifact": _optional_str(post.get("artifact_path")),
            "stewardship_active_positions": _int_value(stewardship_payload.get("active_positions")) if stewardship_payload else None,
            "observed_notional_before": _float_value(pre.get("observed_notional")),
            "observed_notional_after": _float_value(post.get("observed_notional")),
            "cleanup_reason": _optional_str(cleanup.get("reason")),
        },
    )


def build_paper_daemon_soak_readiness_rollup_report(
    activation_checklist: Mapping[str, Any] | Any,
    supervised_soak: Mapping[str, Any] | Any,
    *,
    command_center: Mapping[str, Any] | Any | None = None,
    monitor: Mapping[str, Any] | Any | None = None,
    cleanup: Mapping[str, Any] | Any | None = None,
    data_parity: Mapping[str, Any] | Any | None = None,
    notional_decision: Mapping[str, Any] | Any | None = None,
    stewardship: Mapping[str, Any] | Any | None = None,
    flatten_drill: Mapping[str, Any] | Any | None = None,
) -> PaperDaemonSoakReadinessRollupReport:
    activation = _payload(activation_checklist)
    soak = _payload(supervised_soak)
    center = _payload(command_center)
    monitor_payload = _payload(monitor)
    cleanup_payload = _payload(cleanup)
    parity = _payload(data_parity)
    notional = _payload(notional_decision)
    stewardship_payload = _payload(stewardship)
    drill = _payload(flatten_drill)
    checks = {
        "activation_checklist_passed": bool(activation.get("passed")),
        "supervised_soak_passed": bool(soak.get("passed")),
        "command_center_passed": bool(center.get("passed")),
        "monitor_passed": bool(monitor_payload.get("passed")),
        "cleanup_closure_resolved": _cleanup_evidence_resolved(cleanup_payload),
        "data_parity_passed": bool(parity.get("passed")),
        "notional_decision_allows_hold_or_escalation": bool(notional.get("passed")) and str(notional.get("action") or "").lower() != "downshift",
        "stewardship_passed": bool(stewardship_payload.get("passed")),
        "flatten_drill_passed": bool(drill.get("passed")),
    }
    blockers = tuple(name for name, passed in checks.items() if not passed)
    warnings = _soak_rollup_warnings(activation, soak, center, monitor_payload, cleanup_payload, parity, notional, stewardship_payload, drill)
    return PaperDaemonSoakReadinessRollupReport(
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        recommended_action=_soak_rollup_action(blockers),
        evidence={
            "clean_activations": _int_value(soak.get("clean_activations")),
            "submitted_activations": _int_value(soak.get("submitted_activations")),
            "active_windows": list(_sequence(soak.get("active_windows"))),
            "required_clean_activations": _int_value(soak.get("required_clean_activations")),
            "required_active_windows": _int_value(soak.get("required_active_windows")),
            "observed_notional": _float_value(monitor_payload.get("observed_notional")),
            "closed_symbols": list(_sequence(monitor_payload.get("closed_symbols"))),
            "cleanup_reason": _optional_str(cleanup_payload.get("reason")),
            "notional_action": _optional_str(notional.get("action")),
            "notional_recommendation": _optional_float(notional.get("recommended_notional")),
            "flatten_drill_target_symbols": list(_sequence(drill.get("target_symbols"))),
            "flatten_drill_closed_symbols": list(_sequence(drill.get("closed_symbols"))),
            "artifact_paths": list(
                _rollup_artifact_paths(
                    activation,
                    soak,
                    center,
                    monitor_payload,
                    cleanup_payload,
                    parity,
                    notional,
                    stewardship_payload,
                    drill,
                )
            ),
        },
    )


def build_paper_daemon_window_capture_plan_report(
    supervised_soak: Mapping[str, Any] | Any,
    *,
    required_window_names: Sequence[str] = ("market_open", "intraday", "market_close"),
    provider: str = "alpaca",
    symbol: str = "SPY",
    strategy: str = "buyHold",
    paper_profile: str = "micro-notional",
    interval_seconds: float = 300.0,
    max_iterations: int = 1,
) -> PaperDaemonWindowCapturePlanReport:
    soak = _payload(supervised_soak)
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be non-negative.")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive.")
    window_specs = _capture_window_specs(required_window_names)
    activation_by_window = _activation_evidence_by_window(soak)
    targets = tuple(
        _window_capture_target(
            spec,
            activation_by_window,
            provider=provider,
            symbol=symbol,
            strategy=strategy,
            paper_profile=paper_profile,
            interval_seconds=interval_seconds,
            max_iterations=max_iterations,
        )
        for spec in window_specs
    )
    required_clean_activations = _int_value(soak.get("required_clean_activations")) or 3
    required_active_windows = _int_value(soak.get("required_active_windows")) or 2
    clean_activations = _int_value(soak.get("clean_activations"))
    submitted_activations = _int_value(soak.get("submitted_activations"))
    blockers = _window_capture_blockers(
        targets,
        clean_activations=clean_activations,
        submitted_activations=submitted_activations,
        required_clean_activations=required_clean_activations,
        required_active_windows=required_active_windows,
    )
    warnings = tuple(str(item) for item in _sequence(soak.get("warnings")) if item)
    return PaperDaemonWindowCapturePlanReport(
        targets=targets,
        required_clean_activations=required_clean_activations,
        required_active_windows=required_active_windows,
        clean_activations=clean_activations,
        submitted_activations=submitted_activations,
        blockers=blockers,
        warnings=warnings,
        recommended_action=_window_capture_action(blockers, targets),
    )


def build_paper_daemon_retention_plan(
    paths: Sequence[str | Path],
    *,
    now: datetime | None = None,
    keep_days: int = 30,
    preserve_recent: int = 20,
) -> PaperDaemonRetentionPlan:
    if keep_days < 0:
        raise ValueError("keep_days must be non-negative.")
    if preserve_recent < 0:
        raise ValueError("preserve_recent must be non-negative.")
    now = _utc_now(now)
    sorted_paths = sorted((Path(path) for path in paths), key=_mtime_or_min, reverse=True)
    candidates: list[PaperDaemonRetentionCandidate] = []
    for index, path in enumerate(sorted_paths):
        exists = path.exists()
        age_days = _path_age_days(path, now) if exists else None
        if not exists:
            action = "ignore"
            reason = "artifact_missing"
        elif index < preserve_recent:
            action = "keep"
            reason = "within_recent_preserve_window"
        elif age_days is not None and age_days > keep_days:
            action = "delete"
            reason = "older_than_retention_window"
        else:
            action = "keep"
            reason = "within_retention_window"
        candidates.append(
            PaperDaemonRetentionCandidate(
                path=str(path),
                exists=exists,
                age_days=age_days,
                action=action,
                reason=reason,
            )
        )
    return PaperDaemonRetentionPlan(
        keep_days=keep_days,
        preserve_recent=preserve_recent,
        candidates=tuple(candidates),
    )


def write_paper_daemon_ops_report(report: Any, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict() if hasattr(report, "to_dict") else report
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def _recovery_action(
    *,
    status: str,
    last_error: str | None,
    stale_heartbeat: bool,
    unresolved_running_state: bool,
    lock_active: bool,
    lock_stale: bool,
) -> str:
    if last_error:
        return "reconcile_broker_state_and_review_last_error_before_restart"
    if lock_active and lock_stale:
        return "review_prior_state_then_clear_stale_lock"
    if lock_active:
        return "wait_for_existing_daemon_or_request_clean_stop"
    if unresolved_running_state or stale_heartbeat:
        return "reconcile_broker_state_before_restart"
    if status in {"completed", "stopped", "kill_switch_active"}:
        return "resume_allowed_after_operator_review"
    if status == "missing":
        return "start_with_fresh_state_after_readiness_check"
    return "review_previous_daemon_state"


def _daily_summary_action(daemon_status: str, failed_iterations: int, warnings: Sequence[str]) -> str:
    if daemon_status == "error" or failed_iterations > 0:
        return "review_failures_before_next_daemon_start"
    if daemon_status == "lock_active":
        return "confirm_only_one_daemon_is_running"
    if warnings:
        return "review_warnings_before_notional_changes"
    return "continue_current_paper_daemon_plan"


def _daily_summary_warnings(
    *,
    daemon_status: str,
    failed_iterations: int,
    submitted_iterations: int,
    cleanup_planned_orders: int,
    monitor_failed_iterations: int,
    monitor_stale_open_orders: int,
    monitor_position_mismatches: int,
    data_parity_failed_iterations: int,
    data_parity_failed_checks: int,
    last_error: str | None,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if last_error:
        warnings.append("last_error_present")
    if failed_iterations:
        warnings.append("failed_iterations_present")
    if daemon_status == "kill_switch_active":
        warnings.append("kill_switch_active")
    if submitted_iterations == 0:
        warnings.append("no_orders_submitted")
    if cleanup_planned_orders:
        warnings.append("cleanup_orders_planned")
    if monitor_failed_iterations:
        warnings.append("monitor_failures_present")
    if monitor_stale_open_orders:
        warnings.append("stale_open_orders_present")
    if monitor_position_mismatches:
        warnings.append("position_mismatches_present")
    if data_parity_failed_iterations:
        warnings.append("data_parity_failures_present")
    if data_parity_failed_checks:
        warnings.append("data_parity_failed_checks_present")
    return tuple(warnings)


def _activation_action(blockers: Sequence[str], warnings: Sequence[str], *, cleanup_reason: str | None = None) -> str:
    blockers = tuple(blockers)
    if cleanup_reason == "market_session_not_tradable" and "cleanup_review_resolved" in blockers:
        return "run_guarded_cleanup_during_regular_session_or_provide_operator_acknowledgement"
    if "broker_monitor_clean" in blockers or "cleanup_review_resolved" in blockers:
        return "flatten_or_acknowledge_existing_paper_exposure_before_next_submit"
    if "active_submit_observed" in blockers:
        return "run_micro_notional_daemon_during_active_submit_window"
    if "kill_switch_proof_passed" in blockers or "kill_switch_clear_after_proof" in blockers:
        return "prove_kill_switch_blocks_start_then_clear_it"
    if "daemon_completed_without_error" in blockers or "heartbeat_fresh_or_completed" in blockers:
        return "repair_daemon_runtime_before_unattended_use"
    if "data_parity_clean" in blockers:
        return "repair_data_parity_before_unattended_use"
    if warnings:
        return "review_warnings_before_unattended_daemon"
    return "ready_for_guarded_unattended_paper_soak"


def _activation_warnings(
    warnings: Sequence[Any],
    *,
    position_monitor_clean: bool,
    cleanup_resolved: bool,
    active_submit_observed: bool,
) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(item) for item in warnings if item))
    suppress: set[str] = set()
    if position_monitor_clean:
        suppress.update({"monitor_failures_present", "position_mismatches_present", "paper_monitor_failed"})
    if cleanup_resolved:
        suppress.add("cleanup_orders_planned")
    if position_monitor_clean and cleanup_resolved and active_submit_observed:
        suppress.update({"failed_iterations_present", "no_orders_submitted"})
    return tuple(warning for warning in normalized if warning not in suppress)


def _cleanup_evidence_resolved(payload: Mapping[str, Any]) -> bool:
    if not payload:
        return False
    planned_orders = _sequence(payload.get("planned_orders"))
    if not planned_orders:
        return True
    if payload.get("reason") == "no_positions_to_flatten":
        return True
    return bool(payload.get("submitted")) and payload.get("reconciliation_clean") is not False


def _soak_activation_evidence(value: Mapping[str, Any] | Any) -> PaperDaemonSoakActivationEvidence:
    payload = _payload(value)
    evidence = _mapping(payload.get("evidence"))
    return PaperDaemonSoakActivationEvidence(
        path=_optional_str(payload.get("artifact_path")) or _first_artifact_path(evidence),
        passed=bool(payload.get("passed")),
        active_window=_first_active_window(evidence),
        submitted_iterations=_int_value(evidence.get("submitted_iterations")),
        observed_notional=_float_value(evidence.get("observed_notional")),
        blockers=tuple(str(item) for item in _sequence(payload.get("blockers")) if item),
        warnings=tuple(str(item) for item in _sequence(payload.get("warnings")) if item),
    )


def _supervised_soak_blockers(
    activations: Sequence[PaperDaemonSoakActivationEvidence],
    *,
    required_clean_activations: int,
    required_active_windows: int,
    require_submitted_iterations: bool,
    max_total_observed_notional: float | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    clean = sum(1 for activation in activations if activation.passed)
    submitted = sum(1 for activation in activations if activation.submitted_iterations > 0)
    active_windows = tuple(dict.fromkeys(activation.active_window for activation in activations if activation.active_window))
    if clean < required_clean_activations:
        blockers.append("insufficient_clean_daemon_activations")
    if require_submitted_iterations and submitted < required_clean_activations:
        blockers.append("insufficient_submitted_daemon_activations")
    if len(active_windows) < required_active_windows:
        blockers.append("insufficient_active_window_coverage")
    if any(activation.blockers for activation in activations):
        blockers.append("activation_blockers_present")
    if any(activation.warnings for activation in activations):
        blockers.append("activation_warnings_present")
    if max_total_observed_notional is not None and sum(activation.observed_notional for activation in activations) > max_total_observed_notional:
        blockers.append("observed_notional_above_supervised_soak_cap")
    return tuple(dict.fromkeys(blockers))


def _supervised_soak_action(blockers: Sequence[str]) -> str:
    if not blockers:
        return "continue_supervised_always_on_paper_soak"
    blocker_set = set(blockers)
    if "activation_blockers_present" in blocker_set or "activation_warnings_present" in blocker_set:
        return "review_activation_artifacts_before_next_soak_iteration"
    if "insufficient_active_window_coverage" in blocker_set:
        return "run_daemon_across_additional_active_windows"
    if "insufficient_clean_daemon_activations" in blocker_set or "insufficient_submitted_daemon_activations" in blocker_set:
        return "collect_more_clean_submitted_daemon_activations"
    if "observed_notional_above_supervised_soak_cap" in blocker_set:
        return "reduce_or_flatten_paper_notional_before_soak_continues"
    return "review_supervised_soak_blockers"


def _stewardship_line(
    position: Mapping[str, Any],
    cleanup: Mapping[str, Any],
    *,
    max_active_age_hours: float,
) -> PaperPositionStewardshipLine:
    symbol = str(position.get("symbol") or "").upper()
    status = str(position.get("status") or "unknown")
    owner_type = str(position.get("owner_type") or "unknown")
    forced_exit_needed = bool(position.get("forced_exit_needed"))
    closure_evidence_present = _cleanup_closes_symbol(cleanup, symbol)
    age_hours = _optional_float(position.get("age_hours"))
    return PaperPositionStewardshipLine(
        symbol=symbol,
        status=status,
        owner_type=owner_type,
        expected_quantity=_float_value(position.get("expected_quantity")),
        observed_quantity=_float_value(position.get("observed_quantity")),
        market_value=_optional_float(position.get("market_value")),
        age_hours=age_hours,
        forced_exit_needed=forced_exit_needed or (age_hours is not None and age_hours > max_active_age_hours),
        closure_evidence_present=closure_evidence_present,
        action=_stewardship_line_action(
            status=status,
            age_hours=age_hours,
            max_active_age_hours=max_active_age_hours,
            forced_exit_needed=forced_exit_needed,
            closure_evidence_present=closure_evidence_present,
        ),
    )


def _stewardship_blockers(
    monitor: Mapping[str, Any],
    positions: Sequence[PaperPositionStewardshipLine],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not monitor.get("passed"):
        blockers.append("paper_monitor_not_passing")
    if _sequence(monitor.get("unexpected_symbols")):
        blockers.append("unexpected_symbols_present")
    if _sequence(monitor.get("missing_symbols")):
        blockers.append("missing_symbols_present")
    if any(not position.passed for position in positions):
        blockers.append("unstewarded_or_stale_positions_present")
    return tuple(dict.fromkeys(blockers))


def _stewardship_warnings(
    positions: Sequence[PaperPositionStewardshipLine],
    *,
    max_active_age_hours: float,
) -> tuple[str, ...]:
    warnings: list[str] = []
    for position in positions:
        if position.age_hours is not None and position.age_hours > max_active_age_hours * 0.75 and not position.forced_exit_needed:
            warnings.append(f"{position.symbol}:approaching_max_active_age")
    return tuple(dict.fromkeys(warnings))


def _stewardship_action(blockers: Sequence[str], positions: Sequence[PaperPositionStewardshipLine]) -> str:
    if not blockers and positions:
        return "continue_monitoring_active_paper_positions"
    if not blockers:
        return "no_active_paper_positions_to_steward"
    if "unstewarded_or_stale_positions_present" in blockers:
        return "create_or_execute_close_plan_for_stale_or_unowned_positions"
    if "paper_monitor_not_passing" in blockers:
        return "repair_paper_monitor_or_reconcile_broker_positions"
    return "review_position_stewardship_blockers"


def _stewardship_line_action(
    *,
    status: str,
    age_hours: float | None,
    max_active_age_hours: float,
    forced_exit_needed: bool,
    closure_evidence_present: bool,
) -> str:
    if closure_evidence_present:
        return "closed_by_cleanup_evidence"
    if forced_exit_needed or (age_hours is not None and age_hours > max_active_age_hours):
        return "close_or_flatten_position"
    if status in {"fresh", "active"}:
        return "continue_monitoring"
    return "review_position_ownership"


def _flatten_target_symbols(
    flatten_plan: Mapping[str, Any],
    cleanup: Mapping[str, Any],
) -> tuple[str, ...]:
    symbols: list[str] = []
    for order in _sequence(flatten_plan.get("orders")):
        symbol = str(_mapping(order).get("symbol") or "").upper()
        if symbol:
            symbols.append(symbol)
    for order in _sequence(cleanup.get("submitted_orders")):
        symbol = str(_mapping(order).get("symbol") or "").upper()
        if symbol:
            symbols.append(symbol)
    return tuple(dict.fromkeys(symbols))


def _post_monitor_flat(post_monitor: Mapping[str, Any]) -> bool:
    return bool(post_monitor.get("passed")) and not any(
        (
            _mapping(post_monitor.get("observed_positions")),
            _sequence(post_monitor.get("unexpected_symbols")),
            _sequence(post_monitor.get("missing_symbols")),
        )
    )


def _flatten_drill_warnings(
    pre_monitor: Mapping[str, Any],
    flatten_plan: Mapping[str, Any],
    cleanup: Mapping[str, Any],
    post_monitor: Mapping[str, Any],
    stewardship: Mapping[str, Any],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if _float_value(pre_monitor.get("observed_notional")) <= 0:
        warnings.append("pre_monitor_had_no_observed_notional")
    if _sequence(flatten_plan.get("blocked_symbols")):
        warnings.append("flatten_plan_blocked_symbols_present")
    if _int_value(cleanup.get("fill_poll_attempts")) > 1:
        warnings.append("cleanup_required_multiple_fill_polls")
    if _float_value(post_monitor.get("observed_notional")) > 0:
        warnings.append("post_monitor_notional_remains")
    if stewardship and _int_value(stewardship.get("active_positions")) > 0:
        warnings.append("stewardship_still_reports_active_positions")
    return tuple(dict.fromkeys(warnings))


def _flatten_drill_action(blockers: Sequence[str]) -> str:
    if not blockers:
        return "flatten_drill_passed_continue_next_supervised_daemon_window"
    blocker_set = set(blockers)
    if "cleanup_submitted" in blocker_set or "cleanup_filled" in blocker_set:
        return "submit_or_reconcile_guarded_flatten_orders_before_next_activation"
    if "cleanup_reconciled" in blocker_set:
        return "repair_cleanup_reconciliation_before_next_activation"
    if "post_monitor_flat" in blocker_set or "closed_symbols_recorded" in blocker_set:
        return "rerun_post_flatten_monitor_and_confirm_broker_exposure_is_clear"
    if "pre_monitor_passed" in blocker_set or "flatten_plan_passed" in blocker_set:
        return "rebuild_flatten_plan_from_clean_pre_monitor_evidence"
    if "stewardship_passed" in blocker_set:
        return "resolve_position_stewardship_blockers"
    return "review_flatten_drill_blockers"


def _soak_rollup_warnings(*payloads: Mapping[str, Any]) -> tuple[str, ...]:
    warnings: list[str] = []
    for payload in payloads:
        warnings.extend(str(item) for item in _sequence(payload.get("warnings")) if item)
        warnings.extend(str(item) for item in _sequence(payload.get("blockers")) if item)
    return tuple(dict.fromkeys(warnings))


def _soak_rollup_action(blockers: Sequence[str]) -> str:
    if not blockers:
        return "ready_to_continue_operator_managed_always_on_paper"
    blocker_set = set(blockers)
    if "supervised_soak_passed" in blocker_set:
        return "collect_more_clean_submitted_daemon_windows_before_escalation"
    if "activation_checklist_passed" in blocker_set:
        return "repair_activation_checklist_before_next_daemon_submit"
    if "flatten_drill_passed" in blocker_set or "cleanup_closure_resolved" in blocker_set:
        return "prove_cleanup_and_flatten_drill_before_next_activation"
    if "command_center_passed" in blocker_set or "monitor_passed" in blocker_set:
        return "repair_command_center_or_monitor_evidence"
    if "data_parity_passed" in blocker_set:
        return "repair_data_parity_before_next_active_window"
    if "notional_decision_allows_hold_or_escalation" in blocker_set:
        return "downshift_or_hold_notional_until_ops_evidence_recovers"
    if "stewardship_passed" in blocker_set:
        return "resolve_position_stewardship_before_next_activation"
    return "review_paper_daemon_soak_rollup_blockers"


def _capture_window_specs(window_names: Sequence[str]) -> tuple[Mapping[str, str], ...]:
    defaults = {name: {"name": name, "start_time": start, "end_time": end} for name, start, end in DEFAULT_DAEMON_CAPTURE_WINDOWS}
    specs: list[Mapping[str, str]] = []
    for name in window_names:
        normalized = str(name).strip()
        if not normalized:
            continue
        specs.append(defaults.get(normalized, {"name": normalized, "start_time": "unknown", "end_time": "unknown"}))
    return tuple(specs)


def _activation_evidence_by_window(soak: Mapping[str, Any]) -> Mapping[str, Mapping[str, bool]]:
    evidence: dict[str, dict[str, bool]] = {}
    for activation in _sequence(soak.get("activations")):
        item = _mapping(activation)
        window = str(item.get("active_window") or "").strip()
        if not window:
            continue
        current = evidence.setdefault(window, {"captured": False, "clean": False, "submitted": False})
        current["captured"] = True
        current["clean"] = current["clean"] or bool(item.get("passed"))
        current["submitted"] = current["submitted"] or _int_value(item.get("submitted_iterations")) > 0
    for window in _sequence(soak.get("active_windows")):
        name = str(window).strip()
        if name:
            evidence.setdefault(name, {"captured": True, "clean": True, "submitted": True})
    return evidence


def _window_capture_target(
    spec: Mapping[str, str],
    activation_by_window: Mapping[str, Mapping[str, bool]],
    *,
    provider: str,
    symbol: str,
    strategy: str,
    paper_profile: str,
    interval_seconds: float,
    max_iterations: int,
) -> PaperDaemonWindowCaptureTarget:
    name = str(spec["name"])
    evidence = _mapping(activation_by_window.get(name))
    clean = bool(evidence.get("clean"))
    submitted = bool(evidence.get("submitted"))
    captured = bool(evidence.get("captured"))
    action = "retain_evidence" if clean and submitted else "capture_next"
    return PaperDaemonWindowCaptureTarget(
        name=name,
        start_time=str(spec["start_time"]),
        end_time=str(spec["end_time"]),
        captured=captured,
        clean=clean,
        submitted=submitted,
        action=action,
        command=_window_capture_command(
            provider=provider,
            symbol=symbol,
            strategy=strategy,
            paper_profile=paper_profile,
            interval_seconds=interval_seconds,
            max_iterations=max_iterations,
        ),
    )


def _window_capture_command(
    *,
    provider: str,
    symbol: str,
    strategy: str,
    paper_profile: str,
    interval_seconds: float,
    max_iterations: int,
) -> tuple[str, ...]:
    command = [
        "trading_env\\Scripts\\python.exe",
        "main.py",
        "paper-daemon",
        "--provider",
        provider,
        "--execution-mode",
        "paper",
        "--symbol",
        symbol,
        "--strategy",
        strategy,
        "--paper-daemon-profile",
        paper_profile,
        "--submit-orders",
        "--paper-daemon-max-iterations",
        str(max_iterations),
        "--paper-daemon-interval-seconds",
        str(interval_seconds),
    ]
    return tuple(command)


def _window_capture_blockers(
    targets: Sequence[PaperDaemonWindowCaptureTarget],
    *,
    clean_activations: int,
    submitted_activations: int,
    required_clean_activations: int,
    required_active_windows: int,
) -> tuple[str, ...]:
    blockers: list[str] = []
    clean_windows = sum(1 for target in targets if target.clean and target.submitted)
    if clean_activations < required_clean_activations:
        blockers.append("insufficient_clean_daemon_activations")
    if submitted_activations < required_clean_activations:
        blockers.append("insufficient_submitted_daemon_activations")
    if clean_windows < required_active_windows:
        blockers.append("insufficient_active_window_coverage")
    if any(target.action == "capture_next" for target in targets):
        blockers.append("pending_window_captures")
    return tuple(dict.fromkeys(blockers))


def _window_capture_action(
    blockers: Sequence[str],
    targets: Sequence[PaperDaemonWindowCaptureTarget],
) -> str:
    if not blockers:
        return "multi_window_capture_complete_continue_supervised_soak_review"
    next_target = next((target for target in targets if target.action == "capture_next"), None)
    if next_target is not None:
        return f"run_guarded_daemon_during_{next_target.name}"
    return "review_window_capture_plan_blockers"


def _rollup_artifact_paths(*payloads: Mapping[str, Any]) -> tuple[str, ...]:
    paths: list[str] = []
    for payload in payloads:
        artifact_path = _optional_str(payload.get("artifact_path"))
        if artifact_path:
            paths.append(artifact_path)
        evidence = _mapping(payload.get("evidence"))
        for path in _sequence(evidence.get("artifact_paths")):
            if path:
                paths.append(str(path))
    return tuple(dict.fromkeys(paths))


def _cleanup_closes_symbol(cleanup: Mapping[str, Any], symbol: str) -> bool:
    if not cleanup or not symbol:
        return False
    for order in _sequence(cleanup.get("submitted_orders")):
        order_payload = _mapping(order)
        if str(order_payload.get("symbol") or "").upper() == symbol and str(order_payload.get("status") or "").upper() in {"FILLED", "PARTIALLY_FILLED"}:
            return True
    return False


def _first_artifact_path(evidence: Mapping[str, Any]) -> str | None:
    for path in _sequence(evidence.get("artifact_paths")):
        if path:
            return str(path)
    return None


def _first_active_window(evidence: Mapping[str, Any]) -> str | None:
    for path in _sequence(evidence.get("artifact_paths")):
        text = str(path)
        for name in ("market_open", "intraday", "market_close", "pre_market", "end_of_day"):
            if name in text:
                return name
    return None


def _kill_switch_proof_passed(payload: Mapping[str, Any]) -> bool:
    if not payload:
        return False
    state = _mapping(payload.get("state"))
    return bool(payload.get("passed")) and (
        bool(payload.get("stopped_by_kill_switch"))
        or state.get("status") == "kill_switch_active"
        or state.get("last_reason") == "kill_switch_present_before_start"
    )


def _exposure_acknowledgement_passed(
    payload: Mapping[str, Any],
    *,
    observed_positions: int,
    observed_notional: float,
    now: datetime,
) -> bool:
    return _exposure_acknowledgement_reason(
        payload,
        observed_positions=observed_positions,
        observed_notional=observed_notional,
        now=now,
    ) == "paper_exposure_acknowledged"


def _exposure_acknowledgement_reason(
    payload: Mapping[str, Any],
    *,
    observed_positions: int,
    observed_notional: float,
    now: datetime,
) -> str:
    if observed_positions <= 0 and observed_notional <= 0:
        return "no_paper_exposure_present"
    if not payload:
        return "paper_exposure_acknowledgement_missing"
    if not bool(payload.get("acknowledged")):
        return "paper_exposure_not_acknowledged"
    expires_at = _parse_time(payload.get("expires_at"))
    if expires_at is not None and expires_at < now:
        return "paper_exposure_acknowledgement_expired"
    max_positions = _optional_int(payload.get("max_positions"))
    if max_positions is not None and observed_positions > max_positions:
        return "paper_exposure_position_count_above_acknowledged_limit"
    max_notional = _optional_float(payload.get("max_notional"))
    if max_notional is not None and observed_notional > max_notional:
        return "paper_exposure_notional_above_acknowledged_limit"
    return "paper_exposure_acknowledged"


def _daemon_notional_evidence(value: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    payload = _payload(value)
    if "iterations" in payload:
        return build_paper_daemon_daily_summary_report(payload).to_dict()
    return payload


def _daemon_notional_triggers(evidence: Mapping[str, Any]) -> tuple[str, ...]:
    triggers: list[str] = []
    if str(evidence.get("daemon_status") or "").lower() in {"error", "lock_active"}:
        triggers.append("daemon_unhealthy")
    if _int_value(evidence.get("failed_iterations")) > 0:
        triggers.append("failed_daemon_iteration")
    if _int_value(evidence.get("monitor_failed_iterations")) > 0:
        triggers.append("failed_monitor")
    if _int_value(evidence.get("monitor_stale_open_orders")) > 0:
        triggers.append("stale_open_order")
    if _int_value(evidence.get("monitor_position_mismatches")) > 0:
        triggers.append("position_mismatch")
    if _int_value(evidence.get("data_parity_failed_iterations")) > 0:
        triggers.append("data_parity_failed")
    if _int_value(evidence.get("data_parity_failed_checks")) > 0:
        triggers.append("data_parity_check_failed")
    if _int_value(evidence.get("cleanup_planned_orders")) > _int_value(evidence.get("cleanup_submitted_orders")):
        triggers.append("cleanup_review_required")
    warnings = set(str(warning) for warning in _sequence(evidence.get("warnings")))
    if "last_error_present" in warnings:
        triggers.append("daemon_error_warning")
    if "data_parity_failures_present" in warnings:
        triggers.append("data_parity_warning")
    return tuple(dict.fromkeys(triggers))


def _restart_drill_records(value: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    payload = _payload(value)
    if payload:
        return tuple(_mapping(item) for item in _sequence(payload.get("drills")))
    return tuple(_mapping(item) for item in _sequence(value))


def _restart_drill_result(
    name: str,
    record: Mapping[str, Any] | None,
    *,
    duplicate_check: Mapping[str, Any],
) -> PaperDaemonRestartDrillResult:
    record = _mapping(record)
    if name == "duplicate_client_order_id_guard":
        evidence = {**dict(record), **dict(duplicate_check)}
        if duplicate_check["passed"] and bool(record.get("guard_enabled", True)):
            return PaperDaemonRestartDrillResult(name, True, "duplicate_client_order_guard_passed", evidence)
        reason = "duplicate_client_order_ids_detected" if duplicate_check["duplicates"] else "duplicate_guard_missing"
        return PaperDaemonRestartDrillResult(name, False, reason, evidence)
    if not record:
        return PaperDaemonRestartDrillResult(name, False, "restart_drill_evidence_missing", {})
    if name == "clean_stop_resume":
        checks = {
            "stopped_cleanly": bool(record.get("stopped_cleanly")),
            "resumed": bool(record.get("resumed")),
            "recovery_passed": bool(record.get("recovery_passed")),
            "duplicate_submit_blocked": not bool(record.get("duplicate_submit_detected")),
        }
    elif name == "stale_lock_replacement":
        checks = {
            "stale_lock_detected": bool(record.get("stale_lock_detected")),
            "stale_lock_replaced": bool(record.get("stale_lock_replaced")),
            "resumed": bool(record.get("resumed")),
            "recovery_passed": bool(record.get("recovery_passed")),
        }
    elif name == "kill_switch_resume":
        checks = {
            "kill_switch_written": bool(record.get("kill_switch_written")),
            "blocked_start": bool(record.get("blocked_start")),
            "kill_switch_cleared": bool(record.get("kill_switch_cleared")),
            "resumed_after_clear": bool(record.get("resumed_after_clear")),
        }
    else:
        checks = {"passed": bool(record.get("passed"))}
    passed = all(checks.values())
    reason = "passed" if passed else _first_failed_check(checks)
    return PaperDaemonRestartDrillResult(name, passed, reason, {**dict(record), "checks": checks})


def _duplicate_client_order_id_check(order_artifacts: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    rows = [row for artifact in order_artifacts for row in _client_order_rows(artifact)]
    counts: dict[str, int] = {}
    guarded: dict[str, bool] = {}
    for row in rows:
        client_order_id = str(row.get("client_order_id") or "")
        if not client_order_id:
            continue
        counts[client_order_id] = counts.get(client_order_id, 0) + 1
        guarded[client_order_id] = guarded.get(client_order_id, False) or _duplicate_guarded(row)
    duplicates = tuple(order_id for order_id, count in sorted(counts.items()) if count > 1 and not guarded.get(order_id))
    return {
        "passed": not duplicates,
        "duplicates": list(duplicates),
        "client_order_ids_seen": sorted(counts),
        "orders_scanned": len(rows),
    }


def _client_order_rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if value.get("client_order_id"):
            rows.append(value)
        for key in ("submitted_orders", "planned_orders", "open_orders", "orders", "submitted_orders_after", "orders_after", "children", "records", "iterations"):
            rows.extend(_client_order_rows(value.get(key)))
        return tuple(rows)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            rows.extend(_client_order_rows(item))
    return tuple(rows)


def _duplicate_guarded(row: Mapping[str, Any]) -> bool:
    values = {
        str(row.get("status") or "").lower(),
        str(row.get("reason") or "").lower(),
        str(row.get("action") or "").lower(),
        str(row.get("decision") or "").lower(),
    }
    return bool(
        values
        & {
            "duplicate_blocked",
            "retry_existing_open_order",
            "duplicate_guard_blocked",
            "reuse_existing_open_order",
        }
    )


def _first_failed_check(checks: Mapping[str, bool]) -> str:
    return next((name for name, passed in checks.items() if not passed), "restart_drill_failed")


def _previous_tier(current_notional: float, tiers: Sequence[float]) -> float:
    ordered = sorted(float(tier) for tier in tiers if float(tier) > 0)
    lower = [tier for tier in ordered if tier < current_notional]
    return lower[-1] if lower else ordered[0] if ordered else current_notional


def _next_tier(current_notional: float, tiers: Sequence[float]) -> float:
    ordered = sorted(float(tier) for tier in tiers if float(tier) > 0)
    higher = [tier for tier in ordered if tier > current_notional]
    return higher[0] if higher else current_notional


def _collect_artifact_paths(payload: Mapping[str, Any], iterations: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    paths: list[str] = []
    if payload.get("artifact_path"):
        paths.append(str(payload["artifact_path"]))
    for item in iterations:
        for path in _sequence(item.get("artifact_paths")):
            if path:
                paths.append(str(path))
    return tuple(dict.fromkeys(paths))


def _payload(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict"):
        payload = value.to_dict()
        return _mapping(payload)
    return {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return ()


def _load_json_mapping(path: str | Path, *, default: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = Path(path)
    if not candidate.exists():
        return default
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {**default, "last_error": "invalid_json"}
    return _mapping(payload)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _utc_now(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc_now(parsed)


def _age_seconds(started_at: datetime | None, now: datetime) -> float | None:
    if started_at is None:
        return None
    return max(0.0, (now - started_at).total_seconds())


def _path_age_days(path: Path, now: datetime) -> float:
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0.0, (now - modified_at).total_seconds() / 86_400)


def _mtime_or_min(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def _utc_now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_str(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()
