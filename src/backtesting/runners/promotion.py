from dataclasses import dataclass, field
from typing import Any, Mapping

from ..core.validation import BacktestValidationReport
from ..execution.capacity import CapacityAnalysisReport
from .governance import WalkForwardGovernanceReport


@dataclass(frozen=True)
class PromotionPipelinePolicy:
    require_source_rules: bool = True
    require_data_validation: bool = True
    require_replication_or_benchmark: bool = True
    require_governance: bool = True
    require_capacity: bool = True
    require_risk_gates: bool = True
    minimum_estimated_capacity: float | None = None


@dataclass(frozen=True)
class ResearchCandidateEvidence:
    strategy_name: str
    symbol: str
    params: Mapping[str, Any] = field(default_factory=dict)
    source_rules_captured: bool = False
    data_validation_passed: bool = False
    benchmark_passed: bool = False
    replication_passed: bool = False
    risk_gates_passed: bool = False
    data_range: tuple[str, str] | None = None
    validation_report: BacktestValidationReport | None = None
    governance_report: WalkForwardGovernanceReport | None = None
    capacity_report: CapacityAnalysisReport | None = None
    benchmark_summary: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "params": dict(self.params),
            "source_rules_captured": self.source_rules_captured,
            "data_validation_passed": self.data_validation_passed,
            "benchmark_passed": self.benchmark_passed,
            "replication_passed": self.replication_passed,
            "risk_gates_passed": self.risk_gates_passed,
            "data_range": list(self.data_range) if self.data_range else None,
            "validation_report": self.validation_report.to_dict() if self.validation_report else None,
            "governance": self.governance_report.to_dict() if self.governance_report else None,
            "capacity": self.capacity_report.to_dict() if self.capacity_report else None,
            "benchmark_summary": dict(self.benchmark_summary),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class PromotionGateResult:
    name: str
    passed: bool
    reason: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class PaperSessionManifest:
    strategy_name: str
    symbol: str
    params: Mapping[str, Any]
    broker_mode: str = "alpaca_paper"
    data_source: str = "alpaca"
    execution_profile: str = "paper_default"
    manifest_status: str = "ready_for_paper_session"
    safeguards: tuple[str, ...] = (
        "paper_trading_only",
        "runtime_risk_gates_required",
        "broker_reconciliation_required",
        "operator_kill_switch_required",
    )

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "params": dict(self.params),
            "broker_mode": self.broker_mode,
            "data_source": self.data_source,
            "execution_profile": self.execution_profile,
            "manifest_status": self.manifest_status,
            "safeguards": list(self.safeguards),
        }


@dataclass(frozen=True)
class PromotionPipelineReport:
    evidence: ResearchCandidateEvidence
    policy: PromotionPipelinePolicy
    gates: tuple[PromotionGateResult, ...]
    manifest: PaperSessionManifest | None

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def reason(self) -> str:
        if self.passed:
            return "promotion_ready"
        failed = next(gate for gate in self.gates if not gate.passed)
        return failed.reason

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "evidence": self.evidence.to_dict(),
            "policy": {
                "require_source_rules": self.policy.require_source_rules,
                "require_data_validation": self.policy.require_data_validation,
                "require_replication_or_benchmark": self.policy.require_replication_or_benchmark,
                "require_governance": self.policy.require_governance,
                "require_capacity": self.policy.require_capacity,
                "require_risk_gates": self.policy.require_risk_gates,
                "minimum_estimated_capacity": self.policy.minimum_estimated_capacity,
            },
            "gates": [gate.to_dict() for gate in self.gates],
            "manifest": self.manifest.to_dict() if self.manifest else None,
        }


def evaluate_promotion_candidate(
    evidence: ResearchCandidateEvidence,
    policy: PromotionPipelinePolicy | None = None,
) -> PromotionPipelineReport:
    policy = policy or PromotionPipelinePolicy()
    gates = (
        _source_rules_gate(evidence, policy),
        _data_validation_gate(evidence, policy),
        _replication_or_benchmark_gate(evidence, policy),
        _governance_gate(evidence, policy),
        _capacity_gate(evidence, policy),
        _risk_gate(evidence, policy),
    )
    manifest = _paper_manifest(evidence) if all(gate.passed for gate in gates) else None
    return PromotionPipelineReport(evidence=evidence, policy=policy, gates=gates, manifest=manifest)


def _source_rules_gate(evidence: ResearchCandidateEvidence, policy: PromotionPipelinePolicy) -> PromotionGateResult:
    if not policy.require_source_rules:
        return PromotionGateResult("source_rules", True, "not_required")
    if evidence.source_rules_captured:
        return PromotionGateResult("source_rules", True, "source_rules_captured")
    return PromotionGateResult("source_rules", False, "missing_source_rules")


def _data_validation_gate(evidence: ResearchCandidateEvidence, policy: PromotionPipelinePolicy) -> PromotionGateResult:
    if not policy.require_data_validation:
        return PromotionGateResult("data_validation", True, "not_required")
    report_passed = evidence.validation_report.passed if evidence.validation_report else evidence.data_validation_passed
    if evidence.data_validation_passed and report_passed:
        return PromotionGateResult("data_validation", True, "data_validation_passed")
    return PromotionGateResult("data_validation", False, "data_validation_failed")


def _replication_or_benchmark_gate(
    evidence: ResearchCandidateEvidence,
    policy: PromotionPipelinePolicy,
) -> PromotionGateResult:
    if not policy.require_replication_or_benchmark:
        return PromotionGateResult("replication_or_benchmark", True, "not_required")
    if evidence.replication_passed:
        return PromotionGateResult("replication_or_benchmark", True, "replication_passed")
    if evidence.benchmark_passed:
        return PromotionGateResult("replication_or_benchmark", True, "benchmark_passed")
    return PromotionGateResult("replication_or_benchmark", False, "missing_replication_or_benchmark_edge")


def _governance_gate(evidence: ResearchCandidateEvidence, policy: PromotionPipelinePolicy) -> PromotionGateResult:
    if not policy.require_governance:
        return PromotionGateResult("walk_forward_governance", True, "not_required")
    if evidence.governance_report and evidence.governance_report.passed:
        return PromotionGateResult(
            "walk_forward_governance",
            True,
            "governance_passed",
            {"holdout_score": evidence.governance_report.holdout_score},
        )
    reason = evidence.governance_report.reason if evidence.governance_report else "missing_governance_report"
    return PromotionGateResult("walk_forward_governance", False, reason)


def _capacity_gate(evidence: ResearchCandidateEvidence, policy: PromotionPipelinePolicy) -> PromotionGateResult:
    if not policy.require_capacity:
        return PromotionGateResult("capacity", True, "not_required")
    if not evidence.capacity_report:
        return PromotionGateResult("capacity", False, "missing_capacity_report")
    estimated_capacity = evidence.capacity_report.estimated_capacity
    if estimated_capacity is None:
        return PromotionGateResult("capacity", False, "no_capacity_level_passed")
    if policy.minimum_estimated_capacity is not None and estimated_capacity < policy.minimum_estimated_capacity:
        return PromotionGateResult(
            "capacity",
            False,
            "capacity_below_minimum",
            {"estimated_capacity": estimated_capacity, "minimum_estimated_capacity": policy.minimum_estimated_capacity},
        )
    return PromotionGateResult("capacity", True, "capacity_passed", {"estimated_capacity": estimated_capacity})


def _risk_gate(evidence: ResearchCandidateEvidence, policy: PromotionPipelinePolicy) -> PromotionGateResult:
    if not policy.require_risk_gates:
        return PromotionGateResult("risk_gates", True, "not_required")
    if evidence.risk_gates_passed:
        return PromotionGateResult("risk_gates", True, "risk_gates_passed")
    return PromotionGateResult("risk_gates", False, "risk_gates_failed")


def _paper_manifest(evidence: ResearchCandidateEvidence) -> PaperSessionManifest:
    params = evidence.params
    if evidence.governance_report:
        params = evidence.governance_report.parameter_stability.champion_params or evidence.params
    return PaperSessionManifest(
        strategy_name=evidence.strategy_name,
        symbol=evidence.symbol,
        params=dict(params),
    )
