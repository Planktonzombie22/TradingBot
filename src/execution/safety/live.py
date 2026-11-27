import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.models import Order


LIVE_TRADING_BASE_URL = "https://api.alpaca.markets"
REQUIRED_LIVE_UNLOCK_CHECKS = (
    "config_flag",
    "env_flag",
    "live_account_url",
    "risk_profile",
    "approval_artifact",
    "command_flag",
    "live_adapter_implemented",
)
EMERGENCY_PROCEDURES = ("cancel_all", "flatten_all", "disable_scheduler", "rotate_keys", "validate_account_state")
COMPLIANCE_TOPICS = ("pdt", "margin", "short_sales", "wash_sales", "broker_restrictions", "tax_export")


@dataclass(frozen=True)
class LiveSafetyCheck:
    name: str
    passed: bool
    reason: str
    metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "reason": self.reason, "metadata": dict(self.metadata or {})}


@dataclass(frozen=True)
class LiveOrderBoundaryReport:
    paper_adapter: str
    live_adapter: str
    live_submit_default_enabled: bool = False
    shared_submit_path: bool = False

    @property
    def passed(self) -> bool:
        return bool(self.paper_adapter) and bool(self.live_adapter) and not self.live_submit_default_enabled and not self.shared_submit_path

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "paper_adapter": self.paper_adapter,
            "live_adapter": self.live_adapter,
            "live_submit_default_enabled": self.live_submit_default_enabled,
            "shared_submit_path": self.shared_submit_path,
            "reason": "separate_live_boundary" if self.passed else "live_boundary_not_separate",
        }


@dataclass(frozen=True)
class LiveUnlockReport:
    checks: tuple[LiveSafetyCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks) and {check.name for check in self.checks} >= set(REQUIRED_LIVE_UNLOCK_CHECKS)

    @property
    def blockers(self) -> tuple[LiveSafetyCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "live_unlocked": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [check.to_dict() for check in self.blockers],
        }


@dataclass(frozen=True)
class AccountAllowlistReport:
    account_fingerprint: str
    allowed_fingerprints: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.account_fingerprint in self.allowed_fingerprints

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "account_fingerprint": self.account_fingerprint,
            "allowed": self.account_fingerprint in self.allowed_fingerprints,
            "allowed_fingerprints": list(self.allowed_fingerprints),
        }


@dataclass(frozen=True)
class LiveOrderCapReport:
    checks: tuple[LiveSafetyCheck, ...]
    max_order_notional: float
    max_daily_notional: float
    max_daily_loss: float
    max_open_positions: int
    max_gross_exposure: float

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "limits": {
                "max_order_notional": self.max_order_notional,
                "max_daily_notional": self.max_daily_notional,
                "max_daily_loss": self.max_daily_loss,
                "max_open_positions": self.max_open_positions,
                "max_gross_exposure": self.max_gross_exposure,
            },
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [check.to_dict() for check in self.checks if not check.passed],
        }


@dataclass(frozen=True)
class LiveKillSwitchDrillReport:
    dry_run_passed: bool
    paper_passed: bool
    live_unlock_requested: bool = False

    @property
    def passed(self) -> bool:
        return self.dry_run_passed and self.paper_passed

    @property
    def live_unlock_allowed(self) -> bool:
        return self.live_unlock_requested and self.passed

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "dry_run_passed": self.dry_run_passed,
            "paper_passed": self.paper_passed,
            "live_unlock_requested": self.live_unlock_requested,
            "live_unlock_allowed": self.live_unlock_allowed,
        }


@dataclass(frozen=True)
class NoLiveSubmitReport:
    commands: tuple[Mapping[str, Any], ...]

    @property
    def violations(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.commands if row.get("execution_mode") != "live" and bool(row.get("touches_live_endpoint") or row.get("submits_live_order")))

    @property
    def passed(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "commands": [dict(row) for row in self.commands],
            "violations": [dict(row) for row in self.violations],
        }


@dataclass(frozen=True)
class SecretScanReport:
    scanned_items: tuple[Mapping[str, Any], ...]

    @property
    def findings(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.scanned_items if bool(row.get("findings")))

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        return {"passed": self.passed, "scanned_items": [dict(row) for row in self.scanned_items], "findings": [dict(row) for row in self.findings]}


@dataclass(frozen=True)
class RedactionRegressionReport:
    checks: tuple[LiveSafetyCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "checks": [check.to_dict() for check in self.checks], "blockers": [check.to_dict() for check in self.checks if not check.passed]}


@dataclass(frozen=True)
class AuditLogIntegrityReport:
    entries: tuple[Mapping[str, Any], ...]

    @property
    def passed(self) -> bool:
        expected_previous = ""
        for entry in self.entries:
            payload = dict(entry)
            digest = str(payload.pop("digest", ""))
            previous_digest = str(payload.get("previous_digest", ""))
            if previous_digest != expected_previous or digest != _digest(payload):
                return False
            expected_previous = digest
        return bool(self.entries)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "entries": [dict(row) for row in self.entries], "entries_checked": len(self.entries)}


@dataclass(frozen=True)
class ReadOnlyReportingModeReport:
    mode: str
    broker_submit_requested: bool = False
    write_artifacts_requested: bool = True

    @property
    def passed(self) -> bool:
        return self.mode == "read-only" and not self.broker_submit_requested and self.write_artifacts_requested

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "mode": self.mode,
            "broker_submit_requested": self.broker_submit_requested,
            "write_artifacts_requested": self.write_artifacts_requested,
        }


@dataclass(frozen=True)
class ManualApprovalWorkflowReport:
    approvals: tuple[Mapping[str, Any], ...]
    required_actions: tuple[str, ...]

    @property
    def missing_actions(self) -> tuple[str, ...]:
        approved = {str(row.get("action")) for row in self.approvals if bool(row.get("approved")) and row.get("operator") and row.get("timestamp")}
        return tuple(action for action in self.required_actions if action not in approved)

    @property
    def passed(self) -> bool:
        return not self.missing_actions

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "required_actions": list(self.required_actions),
            "approvals": [dict(row) for row in self.approvals],
            "missing_actions": list(self.missing_actions),
        }


@dataclass(frozen=True)
class EmergencyProcedureReport:
    procedures: tuple[Mapping[str, Any], ...]

    @property
    def missing_procedures(self) -> tuple[str, ...]:
        present = {str(row.get("name")) for row in self.procedures if row.get("documented") and row.get("tested_in_paper")}
        return tuple(name for name in EMERGENCY_PROCEDURES if name not in present)

    @property
    def passed(self) -> bool:
        return not self.missing_procedures

    def to_dict(self) -> dict:
        return {"passed": self.passed, "procedures": [dict(row) for row in self.procedures], "missing_procedures": list(self.missing_procedures)}


@dataclass(frozen=True)
class ComplianceAwarenessReport:
    topics: tuple[Mapping[str, Any], ...]

    @property
    def missing_topics(self) -> tuple[str, ...]:
        present = {str(row.get("topic")) for row in self.topics if row.get("documented")}
        return tuple(topic for topic in COMPLIANCE_TOPICS if topic not in present)

    @property
    def passed(self) -> bool:
        return not self.missing_topics

    def to_dict(self) -> dict:
        return {"passed": self.passed, "topics": [dict(row) for row in self.topics], "missing_topics": list(self.missing_topics)}


@dataclass(frozen=True)
class LiveStillLockedReport:
    live_unlock: LiveUnlockReport
    no_live_submit: NoLiveSubmitReport
    live_adapter_available: bool = False

    @property
    def passed(self) -> bool:
        return not self.live_unlock.passed and self.no_live_submit.passed and not self.live_adapter_available

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "live_locked": self.passed,
            "live_adapter_available": self.live_adapter_available,
            "live_unlock": self.live_unlock.to_dict(),
            "no_live_submit": self.no_live_submit.to_dict(),
        }


def build_live_order_boundary_report(
    paper_adapter: str = "AlpacaPaperBroker",
    live_adapter: str = "LockedAlpacaLiveBroker",
    live_submit_default_enabled: bool = False,
    shared_submit_path: bool = False,
) -> LiveOrderBoundaryReport:
    return LiveOrderBoundaryReport(paper_adapter, live_adapter, live_submit_default_enabled, shared_submit_path)


def build_live_unlock_report(config: Mapping[str, Any]) -> LiveUnlockReport:
    base_url = str(config.get("base_url", ""))
    checks = (
        LiveSafetyCheck("config_flag", bool(config.get("config_flag")), "passed" if config.get("config_flag") else "config_flag_missing"),
        LiveSafetyCheck("env_flag", bool(config.get("env_flag")), "passed" if config.get("env_flag") else "env_flag_missing"),
        LiveSafetyCheck("live_account_url", base_url.rstrip("/") == LIVE_TRADING_BASE_URL, "passed" if base_url.rstrip("/") == LIVE_TRADING_BASE_URL else "live_account_url_missing"),
        LiveSafetyCheck("risk_profile", bool(config.get("risk_profile")), "passed" if config.get("risk_profile") else "risk_profile_missing"),
        LiveSafetyCheck("approval_artifact", bool(config.get("approval_artifact")), "passed" if config.get("approval_artifact") else "approval_artifact_missing"),
        LiveSafetyCheck("command_flag", bool(config.get("command_flag")), "passed" if config.get("command_flag") else "command_flag_missing"),
        LiveSafetyCheck("live_adapter_implemented", bool(config.get("live_adapter_implemented")), "passed" if config.get("live_adapter_implemented") else "live_adapter_not_implemented"),
    )
    return LiveUnlockReport(checks)


def build_account_allowlist_report(account_id: str, allowed_account_ids: Sequence[str]) -> AccountAllowlistReport:
    return AccountAllowlistReport(_fingerprint(account_id), tuple(_fingerprint(value) for value in allowed_account_ids))


def build_live_order_cap_report(
    orders: Sequence[Order | Mapping[str, Any]],
    prices: Mapping[str, float],
    max_order_notional: float,
    max_daily_notional: float,
    max_daily_loss: float,
    max_open_positions: int,
    max_gross_exposure: float,
    current_open_positions: int = 0,
    current_gross_exposure: float = 0.0,
    current_daily_loss: float = 0.0,
) -> LiveOrderCapReport:
    normalized = [_order_fields(order) for order in orders]
    order_notionals = [_quantity(row) * float(prices.get(str(row["symbol"]), 0.0)) for row in normalized]
    daily_notional = sum(order_notionals)
    checks = [
        LiveSafetyCheck("max_order_notional", all(value <= max_order_notional for value in order_notionals), "passed" if all(value <= max_order_notional for value in order_notionals) else "max_order_notional_exceeded"),
        LiveSafetyCheck("max_daily_notional", daily_notional <= max_daily_notional, "passed" if daily_notional <= max_daily_notional else "max_daily_notional_exceeded"),
        LiveSafetyCheck("max_daily_loss", abs(current_daily_loss) <= max_daily_loss, "passed" if abs(current_daily_loss) <= max_daily_loss else "max_daily_loss_exceeded"),
        LiveSafetyCheck("max_open_positions", current_open_positions + len({row["symbol"] for row in normalized}) <= max_open_positions, "passed" if current_open_positions + len({row["symbol"] for row in normalized}) <= max_open_positions else "max_open_positions_exceeded"),
        LiveSafetyCheck("max_gross_exposure", current_gross_exposure + daily_notional <= max_gross_exposure, "passed" if current_gross_exposure + daily_notional <= max_gross_exposure else "max_gross_exposure_exceeded"),
    ]
    return LiveOrderCapReport(tuple(checks), max_order_notional, max_daily_notional, max_daily_loss, max_open_positions, max_gross_exposure)


def build_live_kill_switch_drill_report(dry_run_passed: bool, paper_passed: bool, live_unlock_requested: bool = False) -> LiveKillSwitchDrillReport:
    return LiveKillSwitchDrillReport(dry_run_passed, paper_passed, live_unlock_requested)


def build_no_live_submit_report(commands: Sequence[Mapping[str, Any]]) -> NoLiveSubmitReport:
    return NoLiveSubmitReport(tuple(dict(row) for row in commands))


def build_secret_scan_report(items: Mapping[str, str] | Sequence[Mapping[str, Any]]) -> SecretScanReport:
    if isinstance(items, Mapping):
        rows = tuple({"path": path, "findings": _secret_findings(content)} for path, content in items.items())
    else:
        rows = tuple({**dict(row), "findings": _secret_findings(str(row.get("content", "")))} for row in items)
    return SecretScanReport(rows)


def build_redaction_regression_report(payloads: Sequence[Mapping[str, Any]], sensitive_values: Sequence[str]) -> RedactionRegressionReport:
    rendered = json.dumps([dict(row) for row in payloads], default=str)
    checks = tuple(
        LiveSafetyCheck(f"redacted_{idx}", value not in rendered, "passed" if value not in rendered else "sensitive_value_visible")
        for idx, value in enumerate(sensitive_values)
        if value
    )
    return RedactionRegressionReport(checks)


def build_audit_log_integrity_report(entries: Sequence[Mapping[str, Any]]) -> AuditLogIntegrityReport:
    expected_previous = ""
    normalized = []
    for entry in entries:
        payload = dict(entry)
        payload.setdefault("previous_digest", expected_previous)
        payload["digest"] = _digest({key: value for key, value in payload.items() if key != "digest"})
        expected_previous = payload["digest"]
        normalized.append(payload)
    return AuditLogIntegrityReport(tuple(normalized))


def build_read_only_reporting_mode_report(mode: str, broker_submit_requested: bool = False, write_artifacts_requested: bool = True) -> ReadOnlyReportingModeReport:
    return ReadOnlyReportingModeReport(mode, broker_submit_requested, write_artifacts_requested)


def build_manual_approval_workflow_report(approvals: Sequence[Mapping[str, Any]], required_actions: Sequence[str]) -> ManualApprovalWorkflowReport:
    return ManualApprovalWorkflowReport(tuple(dict(row) for row in approvals), tuple(required_actions))


def build_emergency_procedure_report(procedures: Sequence[Mapping[str, Any]]) -> EmergencyProcedureReport:
    return EmergencyProcedureReport(tuple(dict(row) for row in procedures))


def build_compliance_awareness_report(topics: Sequence[Mapping[str, Any]]) -> ComplianceAwarenessReport:
    return ComplianceAwarenessReport(tuple(dict(row) for row in topics))


def build_live_still_locked_report(live_unlock: LiveUnlockReport, no_live_submit: NoLiveSubmitReport, live_adapter_available: bool = False) -> LiveStillLockedReport:
    return LiveStillLockedReport(live_unlock, no_live_submit, live_adapter_available)


def write_live_safety_report(report: Any, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return destination


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _secret_findings(content: str) -> list[str]:
    findings = []
    patterns = {
        "alpaca_key": r"(?i)APCA|ALPACA_API_KEY|PK[A-Z0-9]{12,}",
        "secret_key": r"(?i)SECRET_KEY\s*=|SK[A-Z0-9]{12,}",
        "bearer_token": r"(?i)bearer\s+[a-z0-9._-]{16,}",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, content):
            findings.append(name)
    return findings


def _order_fields(order: Order | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(order, Order):
        return {"symbol": order.symbol, "quantity": order.quantity}
    return dict(order)


def _quantity(order: Mapping[str, Any]) -> float:
    try:
        return float(order.get("quantity", order.get("qty", 0.0)))
    except (TypeError, ValueError):
        return 0.0
