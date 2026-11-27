import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


REQUIRED_VALIDATION_PROFILES = ("fast", "paper-dry-run", "paper-submit", "release", "live-gate")
REQUIRED_REVIEW_FIELDS = ("strategy", "rationale", "max_live_notional", "stop_conditions", "rollback_procedure")


@dataclass(frozen=True)
class PreLiveGate:
    name: str
    passed: bool
    reason: str
    evidence: Mapping[str, Any] | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "reason": self.reason, "evidence": dict(self.evidence or {})}


@dataclass(frozen=True)
class FinalPreLiveEvidenceReport:
    gates: tuple[PreLiveGate, ...]

    @property
    def blockers(self) -> tuple[PreLiveGate, ...]:
        return tuple(gate for gate in self.gates if not gate.passed)

    @property
    def passed(self) -> bool:
        return bool(self.gates) and not self.blockers

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "gates": [gate.to_dict() for gate in self.gates],
            "blockers": [gate.to_dict() for gate in self.blockers],
        }


@dataclass(frozen=True)
class ValidationProfileGateReport:
    profiles: tuple[Mapping[str, Any], ...]

    @property
    def missing_profiles(self) -> tuple[str, ...]:
        passed = {str(row.get("profile")) for row in self.profiles if row.get("status") == "passed" and not row.get("stale")}
        return tuple(profile for profile in REQUIRED_VALIDATION_PROFILES if profile not in passed)

    @property
    def passed(self) -> bool:
        return not self.missing_profiles

    def to_dict(self) -> dict:
        return {"passed": self.passed, "profiles": [dict(row) for row in self.profiles], "missing_profiles": list(self.missing_profiles)}


@dataclass(frozen=True)
class ReleaseCandidateEvidenceBundleReport:
    code_version: str
    config_hash: str
    artifact_digests: Mapping[str, str]
    readiness_html_path: str

    @property
    def passed(self) -> bool:
        return bool(self.code_version and self.config_hash and self.artifact_digests and self.readiness_html_path)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "code_version": self.code_version,
            "config_hash": self.config_hash,
            "artifact_digests": dict(self.artifact_digests),
            "readiness_html_path": self.readiness_html_path,
        }


@dataclass(frozen=True)
class PaperTradingDayEvidenceReport:
    clean_days: int
    required_days: int = 30

    @property
    def passed(self) -> bool:
        return self.clean_days >= self.required_days

    def to_dict(self) -> dict:
        return {"passed": self.passed, "clean_days": self.clean_days, "required_days": self.required_days, "remaining_days": max(0, self.required_days - self.clean_days)}


@dataclass(frozen=True)
class PromotedPortfolioSubmitExitReport:
    clean_submit_exit_cycles: int
    symbols: tuple[str, ...]
    required_cycles: int = 10

    @property
    def passed(self) -> bool:
        return self.clean_submit_exit_cycles >= self.required_cycles and bool(self.symbols)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "clean_submit_exit_cycles": self.clean_submit_exit_cycles,
            "required_cycles": self.required_cycles,
            "symbols": list(self.symbols),
        }


@dataclass(frozen=True)
class DrillCountReport:
    name: str
    clean_count: int
    required_count: int = 5

    @property
    def passed(self) -> bool:
        return self.clean_count >= self.required_count

    def to_dict(self) -> dict:
        return {"passed": self.passed, "name": self.name, "clean_count": self.clean_count, "required_count": self.required_count}


@dataclass(frozen=True)
class LiveCandidateStrategyEvidenceReport:
    strategies: tuple[Mapping[str, Any], ...]

    @property
    def blockers(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.strategies if not _strategy_evidence_passed(row))

    @property
    def passed(self) -> bool:
        return bool(self.strategies) and not self.blockers

    def to_dict(self) -> dict:
        return {"passed": self.passed, "strategies": [dict(row) for row in self.strategies], "blockers": [dict(row) for row in self.blockers]}


@dataclass(frozen=True)
class DeploymentEnvironmentEvidenceReport:
    scheduled_monitor_jobs: int
    scheduled_report_jobs: int
    missed_artifacts: int

    @property
    def passed(self) -> bool:
        return self.scheduled_monitor_jobs > 0 and self.scheduled_report_jobs > 0 and self.missed_artifacts == 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "scheduled_monitor_jobs": self.scheduled_monitor_jobs,
            "scheduled_report_jobs": self.scheduled_report_jobs,
            "missed_artifacts": self.missed_artifacts,
        }


@dataclass(frozen=True)
class SecretLeakageEvidenceReport:
    findings: tuple[Mapping[str, Any], ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        return {"passed": self.passed, "findings": [dict(row) for row in self.findings]}


@dataclass(frozen=True)
class LivePreviewBlockProofReport:
    intended_order: Mapping[str, Any]
    preview_created: bool
    live_submit_blocked: bool
    final_approval_present: bool = False

    @property
    def passed(self) -> bool:
        return bool(self.intended_order) and self.preview_created and self.live_submit_blocked and not self.final_approval_present

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "intended_order": dict(self.intended_order),
            "preview_created": self.preview_created,
            "live_submit_blocked": self.live_submit_blocked,
            "final_approval_present": self.final_approval_present,
        }


@dataclass(frozen=True)
class OperatorEmergencyCapabilityReport:
    stop_scheduler: bool
    cancel_orders: bool
    flatten_positions: bool
    rotate_keys: bool

    @property
    def passed(self) -> bool:
        return self.stop_scheduler and self.cancel_orders and self.flatten_positions and self.rotate_keys

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "stop_scheduler": self.stop_scheduler,
            "cancel_orders": self.cancel_orders,
            "flatten_positions": self.flatten_positions,
            "rotate_keys": self.rotate_keys,
        }


@dataclass(frozen=True)
class WrittenPreLiveReviewReport:
    review: Mapping[str, Any]
    approved: bool = False
    stored: bool = False

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(field for field in REQUIRED_REVIEW_FIELDS if not self.review.get(field))

    @property
    def passed(self) -> bool:
        return not self.missing_fields and self.approved and self.stored

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "review": dict(self.review),
            "approved": self.approved,
            "stored": self.stored,
            "missing_fields": list(self.missing_fields),
        }


@dataclass(frozen=True)
class FirstLiveMicroOrderAuthorizationReport:
    pre_live_gates_passed: bool
    tiny_capital: bool
    immediate_reconciliation: bool
    immediate_monitor: bool
    automatic_lockout: bool

    @property
    def authorized(self) -> bool:
        return self.pre_live_gates_passed and self.tiny_capital and self.immediate_reconciliation and self.immediate_monitor and self.automatic_lockout

    def to_dict(self) -> dict:
        return {
            "authorized": self.authorized,
            "passed": self.authorized,
            "pre_live_gates_passed": self.pre_live_gates_passed,
            "tiny_capital": self.tiny_capital,
            "immediate_reconciliation": self.immediate_reconciliation,
            "immediate_monitor": self.immediate_monitor,
            "automatic_lockout": self.automatic_lockout,
        }


def build_validation_profile_gate_report(profiles: Sequence[Mapping[str, Any]]) -> ValidationProfileGateReport:
    return ValidationProfileGateReport(tuple(dict(row) for row in profiles))


def build_release_candidate_evidence_bundle_report(code_version: str, config_hash: str, artifact_digests: Mapping[str, str], readiness_html_path: str) -> ReleaseCandidateEvidenceBundleReport:
    return ReleaseCandidateEvidenceBundleReport(code_version, config_hash, dict(artifact_digests), readiness_html_path)


def build_paper_trading_day_evidence_report(clean_days: int, required_days: int = 30) -> PaperTradingDayEvidenceReport:
    return PaperTradingDayEvidenceReport(clean_days, required_days)


def build_promoted_portfolio_submit_exit_report(clean_submit_exit_cycles: int, symbols: Sequence[str], required_cycles: int = 10) -> PromotedPortfolioSubmitExitReport:
    return PromotedPortfolioSubmitExitReport(clean_submit_exit_cycles, tuple(str(symbol).upper() for symbol in symbols), required_cycles)


def build_drill_count_report(name: str, clean_count: int, required_count: int = 5) -> DrillCountReport:
    return DrillCountReport(name, clean_count, required_count)


def build_live_candidate_strategy_evidence_report(strategies: Sequence[Mapping[str, Any]]) -> LiveCandidateStrategyEvidenceReport:
    return LiveCandidateStrategyEvidenceReport(tuple(dict(row) for row in strategies))


def build_deployment_environment_evidence_report(scheduled_monitor_jobs: int, scheduled_report_jobs: int, missed_artifacts: int) -> DeploymentEnvironmentEvidenceReport:
    return DeploymentEnvironmentEvidenceReport(scheduled_monitor_jobs, scheduled_report_jobs, missed_artifacts)


def build_secret_leakage_evidence_report(findings: Sequence[Mapping[str, Any]]) -> SecretLeakageEvidenceReport:
    return SecretLeakageEvidenceReport(tuple(dict(row) for row in findings))


def build_live_preview_block_proof_report(intended_order: Mapping[str, Any], preview_created: bool, live_submit_blocked: bool, final_approval_present: bool = False) -> LivePreviewBlockProofReport:
    return LivePreviewBlockProofReport(dict(intended_order), preview_created, live_submit_blocked, final_approval_present)


def build_operator_emergency_capability_report(stop_scheduler: bool, cancel_orders: bool, flatten_positions: bool, rotate_keys: bool) -> OperatorEmergencyCapabilityReport:
    return OperatorEmergencyCapabilityReport(stop_scheduler, cancel_orders, flatten_positions, rotate_keys)


def build_written_pre_live_review_report(review: Mapping[str, Any], approved: bool = False, stored: bool = False) -> WrittenPreLiveReviewReport:
    return WrittenPreLiveReviewReport(dict(review), approved, stored)


def build_first_live_micro_order_authorization_report(pre_live_gates_passed: bool, tiny_capital: bool, immediate_reconciliation: bool, immediate_monitor: bool, automatic_lockout: bool) -> FirstLiveMicroOrderAuthorizationReport:
    return FirstLiveMicroOrderAuthorizationReport(pre_live_gates_passed, tiny_capital, immediate_reconciliation, immediate_monitor, automatic_lockout)


def build_final_pre_live_evidence_report(gates: Sequence[PreLiveGate | Mapping[str, Any]]) -> FinalPreLiveEvidenceReport:
    normalized = tuple(gate if isinstance(gate, PreLiveGate) else PreLiveGate(str(gate.get("name", "")), bool(gate.get("passed")), str(gate.get("reason", "")), dict(gate.get("evidence", {}))) for gate in gates)
    return FinalPreLiveEvidenceReport(normalized)


def pre_live_gate(name: str, report: Any, reason: str | None = None) -> PreLiveGate:
    payload = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    passed = bool(payload.get("passed") or payload.get("authorized"))
    return PreLiveGate(name, passed, reason or ("passed" if passed else "pre_live_gate_blocked"), payload)


def write_pre_live_evidence_report(report: Any, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return destination


def artifact_digest(path: str | Path) -> str:
    source = Path(path)
    return hashlib.sha256(source.read_bytes()).hexdigest()


def _strategy_evidence_passed(row: Mapping[str, Any]) -> bool:
    required = (
        "paper_scorecard_stable",
        "slippage_stable",
        "drift_stable",
        "pnl_stable",
        "rejects_clean",
        "missed_fills_clean",
        "benchmark_comparison_passed",
        "walk_forward_current",
        "holdout_current",
        "cost_stress_current",
        "market_cluster_current",
    )
    return all(bool(row.get(key)) for key in required)
