from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from src.deployment import DeploymentProfile

from .broker_checks import ValidationProbe


@dataclass(frozen=True)
class DeploymentRehearsalRequirement:
    name: str
    required_checks: tuple[str, ...] = (
        "startup",
        "graceful_stop",
        "watchdog_timeout",
        "log_rotation",
        "artifact_persistence",
        "state_db_persistence",
        "restart_recovery",
    )

    def to_dict(self) -> dict:
        return {"name": self.name, "required_checks": list(self.required_checks)}


@dataclass(frozen=True)
class DeploymentRehearsalReport:
    probes: tuple[ValidationProbe, ...]
    requirements: tuple[DeploymentRehearsalRequirement, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "requirements": [requirement.to_dict() for requirement in self.requirements],
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class GoldenArtifactCase:
    name: str
    observed: Mapping[str, Any]
    expected: Mapping[str, Any]
    tolerances: Mapping[str, float] | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "observed": dict(self.observed),
            "expected": dict(self.expected),
            "tolerances": dict(self.tolerances or {}),
        }


@dataclass(frozen=True)
class GoldenArtifactReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "probes": [probe.to_dict() for probe in self.probes]}


@dataclass(frozen=True)
class GoldenArtifactFixture:
    name: str
    input_payload: Mapping[str, Any]
    expected_payload: Mapping[str, Any]
    approved_by: str = ""
    approved_at: datetime | None = None
    source_digest: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "input_payload": dict(self.input_payload),
            "expected_payload": dict(self.expected_payload),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "source_digest": self.source_digest,
        }


@dataclass(frozen=True)
class GoldenArtifactApprovalRequest:
    name: str
    current_fixture: GoldenArtifactFixture | None
    proposed_fixture: GoldenArtifactFixture
    mismatches: tuple[Mapping[str, Any], ...]
    approved: bool = False

    @property
    def requires_review(self) -> bool:
        return bool(self.mismatches) and not self.approved

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "requires_review": self.requires_review,
            "approved": self.approved,
            "current_fixture": self.current_fixture.to_dict() if self.current_fixture else None,
            "proposed_fixture": self.proposed_fixture.to_dict(),
            "mismatches": [dict(item) for item in self.mismatches],
        }


@dataclass(frozen=True)
class PreLiveUpgradeGate:
    name: str
    description: str

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description}


@dataclass(frozen=True)
class HardPreLiveUpgradeReport:
    probes: tuple[ValidationProbe, ...]
    gates: tuple[PreLiveUpgradeGate, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "gates": [gate.to_dict() for gate in self.gates],
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class MarketSessionEvidenceEvent:
    name: str
    timestamp: datetime
    market_open: bool
    order_generated: bool = False
    order_submitted: bool = False
    allowed_to_submit: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "market_open": self.market_open,
            "order_generated": self.order_generated,
            "order_submitted": self.order_submitted,
            "allowed_to_submit": self.allowed_to_submit,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MarketSessionEnforcementReport:
    probes: tuple[ValidationProbe, ...]
    events: tuple[MarketSessionEvidenceEvent, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "events": [event.to_dict() for event in self.events],
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class DeploymentRunRecord:
    profile_name: str
    exit_code: int
    started_at: datetime
    ended_at: datetime
    graceful_stop: bool = False
    watchdog_timeout_observed: bool = False
    logs_rotated: bool = False
    artifacts_persisted: bool = False
    state_db_persisted: bool = False
    restart_recovered: bool = False
    notes: tuple[str, ...] = ()

    @property
    def elapsed_seconds(self) -> float:
        return max((self.ended_at - self.started_at).total_seconds(), 0.0)

    def to_dict(self) -> dict:
        return {
            "profile_name": self.profile_name,
            "exit_code": self.exit_code,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "elapsed_seconds": self.elapsed_seconds,
            "graceful_stop": self.graceful_stop,
            "watchdog_timeout_observed": self.watchdog_timeout_observed,
            "logs_rotated": self.logs_rotated,
            "artifacts_persisted": self.artifacts_persisted,
            "state_db_persisted": self.state_db_persisted,
            "restart_recovered": self.restart_recovered,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class DeploymentRunEvidenceReport:
    probes: tuple[ValidationProbe, ...]
    records: tuple[DeploymentRunRecord, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "records": [record.to_dict() for record in self.records],
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class AutonomousRehearsalStep:
    name: str
    passed: bool
    artifact_path: str = ""
    reason: str = "passed"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "artifact_path": self.artifact_path,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AutonomousPaperTradingRehearsalReport:
    steps: tuple[AutonomousRehearsalStep, ...]
    release_candidate_bundle: str = ""

    @property
    def passed(self) -> bool:
        return all(step.passed for step in self.steps)

    @property
    def reason(self) -> str:
        if self.passed:
            return "autonomous_paper_rehearsal_passed"
        return next(step.reason for step in self.steps if not step.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "release_candidate_bundle": self.release_candidate_bundle,
            "steps": [step.to_dict() for step in self.steps],
        }


def default_deployment_rehearsal_requirements() -> tuple[DeploymentRehearsalRequirement, ...]:
    return (
        DeploymentRehearsalRequirement("windows-task"),
        DeploymentRehearsalRequirement("docker"),
        DeploymentRehearsalRequirement("small-server"),
    )


def evaluate_deployment_rehearsal(
    evidence_by_profile: Mapping[str, Mapping[str, Any]],
    profiles: Sequence[DeploymentProfile] = (),
    requirements: Sequence[DeploymentRehearsalRequirement] | None = None,
) -> DeploymentRehearsalReport:
    requirements = tuple(requirements or default_deployment_rehearsal_requirements())
    profile_by_name = {profile.name: profile for profile in profiles}
    probes: list[ValidationProbe] = []
    for requirement in requirements:
        evidence = dict(evidence_by_profile.get(requirement.name, {}))
        profile = profile_by_name.get(requirement.name)
        checks = {
            check_name: bool(evidence.get(check_name, False))
            for check_name in requirement.required_checks
        }
        if profile is not None:
            checks["profile_command_present"] = bool(profile.command)
            checks["paper_mode_documented"] = "paper" in profile.command.lower()
            checks["paper_trading_env_safe"] = str(profile.environment.get("PAPER_TRADING", "")).lower() == "true"
        passed = all(checks.values())
        probes.append(
            ValidationProbe(
                requirement.name,
                passed,
                "passed" if passed else "deployment_rehearsal_incomplete",
                {"checks": checks, "evidence": evidence, "profile": _profile_payload(profile)},
            )
        )
    return DeploymentRehearsalReport(tuple(probes), requirements)


def evaluate_market_session_enforcement(
    events: Sequence[MarketSessionEvidenceEvent],
) -> MarketSessionEnforcementReport:
    events = tuple(events)
    outside_submissions = [event for event in events if not event.market_open and event.order_submitted]
    unauthorized_submissions = [event for event in events if event.order_submitted and not event.allowed_to_submit]
    missing_policy_records = [event for event in events if event.order_generated and not event.reason]
    probes = (
        ValidationProbe(
            "outside_session_orders_blocked",
            not outside_submissions,
            "passed" if not outside_submissions else "outside_session_order_submission_detected",
            {"events": [event.to_dict() for event in outside_submissions]},
        ),
        ValidationProbe(
            "submitted_orders_explicitly_allowed",
            not unauthorized_submissions,
            "passed" if not unauthorized_submissions else "submission_without_calendar_permission",
            {"events": [event.to_dict() for event in unauthorized_submissions]},
        ),
        ValidationProbe(
            "generation_policy_reason_recorded",
            not missing_policy_records,
            "passed" if not missing_policy_records else "missing_market_session_policy_reason",
            {"events": [event.to_dict() for event in missing_policy_records]},
        ),
    )
    return MarketSessionEnforcementReport(probes, events)


def evaluate_deployment_run_evidence(
    records: Sequence[DeploymentRunRecord],
    required_profiles: Sequence[str] = ("windows-task", "docker", "small-server"),
) -> DeploymentRunEvidenceReport:
    records = tuple(records)
    by_profile = {record.profile_name: record for record in records}
    missing_profiles = [profile for profile in required_profiles if profile not in by_profile]
    probes: list[ValidationProbe] = [
        ValidationProbe(
            "required_profiles_exercised",
            not missing_profiles,
            "passed" if not missing_profiles else "missing_deployment_profile_runs",
            {"required_profiles": list(required_profiles), "missing_profiles": missing_profiles},
        )
    ]
    for record in records:
        checks = {
            "exit_code_success": record.exit_code == 0,
            "graceful_stop": record.graceful_stop,
            "watchdog_observed_or_not_needed": record.watchdog_timeout_observed or record.exit_code == 0,
            "logs_rotated": record.logs_rotated,
            "artifacts_persisted": record.artifacts_persisted,
            "state_db_persisted": record.state_db_persisted,
            "restart_recovered": record.restart_recovered,
        }
        passed = all(checks.values())
        probes.append(
            ValidationProbe(
                f"{record.profile_name}_deployment_run",
                passed,
                "passed" if passed else "deployment_run_evidence_incomplete",
                {"checks": checks, "record": record.to_dict()},
            )
        )
    return DeploymentRunEvidenceReport(tuple(probes), records)


def build_autonomous_paper_trading_rehearsal_report(
    evidence_bundle: Mapping[str, Any],
    schedule_report: Mapping[str, Any],
    release_decision: Mapping[str, Any],
    readiness_page_path: str = "",
    release_candidate_bundle: str = "",
) -> AutonomousPaperTradingRehearsalReport:
    steps = (
        AutonomousRehearsalStep(
            "evidence_bundle",
            bool(evidence_bundle.get("passed", False)) and bool(evidence_bundle.get("latest_evidence") or evidence_bundle.get("evidence")),
            reason="passed" if bool(evidence_bundle.get("passed", False)) and bool(evidence_bundle.get("latest_evidence") or evidence_bundle.get("evidence")) else "missing_rehearsal_evidence_bundle",
        ),
        AutonomousRehearsalStep(
            "scheduled_paper_sessions",
            bool(schedule_report.get("passed", False)),
            reason="passed" if bool(schedule_report.get("passed", False)) else "scheduled_paper_sessions_failed",
        ),
        AutonomousRehearsalStep(
            "release_decision",
            release_decision.get("decision") == "release_ready",
            reason="passed" if release_decision.get("decision") == "release_ready" else "release_decision_blocked",
        ),
        AutonomousRehearsalStep(
            "operator_readiness_page",
            bool(readiness_page_path),
            artifact_path=readiness_page_path,
            reason="passed" if readiness_page_path else "missing_operator_readiness_page",
        ),
    )
    return AutonomousPaperTradingRehearsalReport(steps, release_candidate_bundle)


def evaluate_golden_artifacts(cases: Sequence[GoldenArtifactCase]) -> GoldenArtifactReport:
    probes: list[ValidationProbe] = []
    for case in cases:
        mismatches = _compare_mapping(case.expected, case.observed, case.tolerances or {})
        probes.append(
            ValidationProbe(
                case.name,
                not mismatches,
                "passed" if not mismatches else "golden_artifact_mismatch",
                {"mismatches": mismatches, "case": case.to_dict()},
            )
        )
    return GoldenArtifactReport(tuple(probes))


def generate_golden_artifact_fixture(
    name: str,
    input_payload: Mapping[str, Any],
    observed_payload: Mapping[str, Any],
    approved_by: str = "",
    approved_at: datetime | None = None,
    source_digest: str = "",
) -> GoldenArtifactFixture:
    return GoldenArtifactFixture(
        name=name,
        input_payload=dict(input_payload),
        expected_payload=dict(observed_payload),
        approved_by=approved_by,
        approved_at=approved_at or (datetime.now(timezone.utc) if approved_by else None),
        source_digest=source_digest,
    )


def propose_golden_artifact_update(
    current_fixture: GoldenArtifactFixture | None,
    observed_payload: Mapping[str, Any],
    approved_by: str = "",
    source_digest: str = "",
    tolerances: Mapping[str, float] | None = None,
) -> GoldenArtifactApprovalRequest:
    name = current_fixture.name if current_fixture else "new_golden_artifact"
    input_payload = current_fixture.input_payload if current_fixture else {}
    expected = current_fixture.expected_payload if current_fixture else {}
    mismatches = tuple(_compare_mapping(expected, observed_payload, tolerances or {})) if current_fixture else ()
    proposed = generate_golden_artifact_fixture(
        name,
        input_payload,
        observed_payload,
        approved_by=approved_by,
        source_digest=source_digest,
    )
    return GoldenArtifactApprovalRequest(
        name=name,
        current_fixture=current_fixture,
        proposed_fixture=proposed,
        mismatches=mismatches,
        approved=bool(approved_by),
    )


def default_pre_live_upgrade_gates() -> tuple[PreLiveUpgradeGate, ...]:
    return (
        PreLiveUpgradeGate("broker_statement_ingestion", "Broker statements can be ingested and compared to local state."),
        PreLiveUpgradeGate("real_alpaca_fill_polling", "Real Alpaca paper fills are polled and reconciled outside simulated fills."),
        PreLiveUpgradeGate("market_session_calendar_enforcement", "Order routing obeys market sessions, holidays, half-days, and configured hours."),
        PreLiveUpgradeGate("paper_account_parity", "Paper account cash, equity, positions, orders, and fills match broker snapshots."),
        PreLiveUpgradeGate("borrow_margin_realism", "Borrow, margin, shortability, and buying-power constraints use broker-realistic evidence."),
        PreLiveUpgradeGate("live_execution_code_separation", "Live execution code is separated from paper execution and remains locked behind explicit gates."),
    )


def evaluate_hard_pre_live_upgrade_gates(
    evidence: Mapping[str, Mapping[str, Any]],
    gates: Sequence[PreLiveUpgradeGate] | None = None,
) -> HardPreLiveUpgradeReport:
    gates = tuple(gates or default_pre_live_upgrade_gates())
    probes = []
    for gate in gates:
        payload = dict(evidence.get(gate.name, {}))
        passed = bool(payload.get("passed", False)) and bool(payload.get("artifact") or payload.get("artifact_path"))
        probes.append(
            ValidationProbe(
                gate.name,
                passed,
                "passed" if passed else "pre_live_upgrade_gate_missing",
                {"gate": gate.to_dict(), "evidence": payload},
            )
        )
    return HardPreLiveUpgradeReport(tuple(probes), gates)


def _compare_mapping(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    tolerances: Mapping[str, float],
    prefix: str = "",
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    expected_keys = set(expected)
    observed_keys = set(observed)
    for key in sorted(expected_keys - observed_keys):
        path = f"{prefix}.{key}" if prefix else str(key)
        mismatches.append({"path": path, "reason": "missing_observed_key", "expected": expected[key]})
    for key in sorted(observed_keys - expected_keys):
        path = f"{prefix}.{key}" if prefix else str(key)
        mismatches.append({"path": path, "reason": "unexpected_observed_key", "observed": observed[key]})
    for key in sorted(expected_keys & observed_keys):
        path = f"{prefix}.{key}" if prefix else str(key)
        expected_value = expected[key]
        observed_value = observed[key]
        if isinstance(expected_value, Mapping) and isinstance(observed_value, Mapping):
            mismatches.extend(_compare_mapping(expected_value, observed_value, tolerances, path))
            continue
        tolerance = tolerances.get(path, 0.0)
        if _numbers(expected_value, observed_value) and tolerance:
            delta = abs(float(expected_value) - float(observed_value))
            if delta > tolerance:
                mismatches.append(
                    {
                        "path": path,
                        "reason": "numeric_tolerance_exceeded",
                        "expected": expected_value,
                        "observed": observed_value,
                        "delta": delta,
                        "tolerance": tolerance,
                    }
                )
        elif expected_value != observed_value:
            mismatches.append(
                {
                    "path": path,
                    "reason": "value_mismatch",
                    "expected": expected_value,
                    "observed": observed_value,
                }
            )
    return mismatches


def _numbers(left: Any, right: Any) -> bool:
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool) and not isinstance(right, bool)


def _profile_payload(profile: DeploymentProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "name": profile.name,
        "command": profile.command,
        "environment": dict(profile.environment),
        "notes": list(profile.notes),
    }
