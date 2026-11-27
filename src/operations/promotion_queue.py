from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.backtesting import MarketRegimeProfile, PaperTradingScorecard, PromotionPipelineReport


@dataclass(frozen=True)
class PromotionQueuePolicy:
    require_operator_approval: bool = True
    require_paper_scorecard: bool = True
    require_regime_fit: bool = True
    min_strategy_edge: float = 0.0
    minimum_estimated_capacity: float | None = None


@dataclass(frozen=True)
class PromotionQueueCandidate:
    promotion_report: PromotionPipelineReport
    strategy_edge: float = 0.0
    paper_scorecard: PaperTradingScorecard | None = None
    regime: MarketRegimeProfile | None = None
    regime_fit: bool = True
    operator_approved: bool = False
    family: str = "default"
    requested_weight: float = 0.10
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def strategy_name(self) -> str:
        return self.promotion_report.evidence.strategy_name

    @property
    def symbol(self) -> str:
        return self.promotion_report.evidence.symbol.upper()

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "strategy_edge": self.strategy_edge,
            "family": self.family,
            "requested_weight": self.requested_weight,
            "operator_approved": self.operator_approved,
            "regime_fit": self.regime_fit,
            "promotion_report": self.promotion_report.to_dict(),
            "paper_scorecard": self.paper_scorecard.to_dict() if self.paper_scorecard else None,
            "regime": self.regime.to_dict() if self.regime else None,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PromotionQueueGate:
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
class PromotionQueueDecision:
    candidate: PromotionQueueCandidate
    gates: tuple[PromotionQueueGate, ...]

    @property
    def enabled(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def status(self) -> str:
        return "enabled_for_paper" if self.enabled else "blocked"

    @property
    def reason(self) -> str:
        if self.enabled:
            return "all_promotion_queue_gates_passed"
        return next(gate.reason for gate in self.gates if not gate.passed)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "enabled": self.enabled,
            "reason": self.reason,
            "candidate": self.candidate.to_dict(),
            "paper_manifest": self.candidate.promotion_report.manifest.to_dict() if self.candidate.promotion_report.manifest else None,
            "gates": [gate.to_dict() for gate in self.gates],
        }


@dataclass(frozen=True)
class PromotionQueueReport:
    policy: PromotionQueuePolicy
    decisions: tuple[PromotionQueueDecision, ...]

    @property
    def enabled_decisions(self) -> tuple[PromotionQueueDecision, ...]:
        return tuple(decision for decision in self.decisions if decision.enabled)

    @property
    def blocked_decisions(self) -> tuple[PromotionQueueDecision, ...]:
        return tuple(decision for decision in self.decisions if not decision.enabled)

    @property
    def enabled_manifests(self) -> tuple:
        return tuple(
            decision.candidate.promotion_report.manifest
            for decision in self.enabled_decisions
            if decision.candidate.promotion_report.manifest is not None
        )

    def to_dict(self) -> dict:
        return {
            "enabled_count": len(self.enabled_decisions),
            "blocked_count": len(self.blocked_decisions),
            "policy": {
                "require_operator_approval": self.policy.require_operator_approval,
                "require_paper_scorecard": self.policy.require_paper_scorecard,
                "require_regime_fit": self.policy.require_regime_fit,
                "min_strategy_edge": self.policy.min_strategy_edge,
                "minimum_estimated_capacity": self.policy.minimum_estimated_capacity,
            },
            "enabled_manifests": [manifest.to_dict() for manifest in self.enabled_manifests],
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


def evaluate_promotion_queue(
    candidates: Sequence[PromotionQueueCandidate],
    policy: PromotionQueuePolicy | None = None,
) -> PromotionQueueReport:
    policy = policy or PromotionQueuePolicy()
    decisions = tuple(_decision(candidate, policy) for candidate in candidates)
    return PromotionQueueReport(policy=policy, decisions=decisions)


def _decision(candidate: PromotionQueueCandidate, policy: PromotionQueuePolicy) -> PromotionQueueDecision:
    gates = (
        _research_gate(candidate),
        _edge_gate(candidate, policy),
        _capacity_gate(candidate, policy),
        _paper_scorecard_gate(candidate, policy),
        _regime_gate(candidate, policy),
        _operator_gate(candidate, policy),
    )
    return PromotionQueueDecision(candidate, gates)


def _research_gate(candidate: PromotionQueueCandidate) -> PromotionQueueGate:
    report = candidate.promotion_report
    if report.passed and report.manifest is not None:
        return PromotionQueueGate("research_promotion", True, "promotion_manifest_ready")
    return PromotionQueueGate(
        "research_promotion",
        False,
        report.reason,
        {"manifest_available": report.manifest is not None},
    )


def _edge_gate(candidate: PromotionQueueCandidate, policy: PromotionQueuePolicy) -> PromotionQueueGate:
    if candidate.strategy_edge >= policy.min_strategy_edge:
        return PromotionQueueGate("strategy_edge", True, "strategy_edge_passed", {"strategy_edge": candidate.strategy_edge})
    return PromotionQueueGate(
        "strategy_edge",
        False,
        "strategy_edge_below_threshold",
        {"strategy_edge": candidate.strategy_edge, "threshold": policy.min_strategy_edge},
    )


def _capacity_gate(candidate: PromotionQueueCandidate, policy: PromotionQueuePolicy) -> PromotionQueueGate:
    if policy.minimum_estimated_capacity is None:
        return PromotionQueueGate("capacity", True, "not_required")
    capacity = candidate.promotion_report.evidence.capacity_report
    estimated = capacity.estimated_capacity if capacity else None
    if estimated is not None and estimated >= policy.minimum_estimated_capacity:
        return PromotionQueueGate("capacity", True, "capacity_passed", {"estimated_capacity": estimated})
    return PromotionQueueGate(
        "capacity",
        False,
        "capacity_below_queue_threshold",
        {"estimated_capacity": estimated, "threshold": policy.minimum_estimated_capacity},
    )


def _paper_scorecard_gate(candidate: PromotionQueueCandidate, policy: PromotionQueuePolicy) -> PromotionQueueGate:
    if not policy.require_paper_scorecard:
        return PromotionQueueGate("paper_scorecard", True, "not_required")
    if candidate.paper_scorecard is None:
        return PromotionQueueGate("paper_scorecard", False, "missing_paper_scorecard")
    if candidate.paper_scorecard.passed:
        return PromotionQueueGate("paper_scorecard", True, "paper_scorecard_passed")
    return PromotionQueueGate("paper_scorecard", False, candidate.paper_scorecard.reason)


def _regime_gate(candidate: PromotionQueueCandidate, policy: PromotionQueuePolicy) -> PromotionQueueGate:
    if not policy.require_regime_fit:
        return PromotionQueueGate("regime_fit", True, "not_required")
    if candidate.regime_fit:
        return PromotionQueueGate(
            "regime_fit",
            True,
            "regime_fit_passed",
            {"regime": candidate.regime.to_dict() if candidate.regime else None},
        )
    return PromotionQueueGate(
        "regime_fit",
        False,
        "regime_fit_failed",
        {"regime": candidate.regime.to_dict() if candidate.regime else None},
    )


def _operator_gate(candidate: PromotionQueueCandidate, policy: PromotionQueuePolicy) -> PromotionQueueGate:
    if not policy.require_operator_approval:
        return PromotionQueueGate("operator_approval", True, "not_required")
    if candidate.operator_approved:
        return PromotionQueueGate("operator_approval", True, "operator_approved")
    return PromotionQueueGate("operator_approval", False, "missing_operator_approval")
