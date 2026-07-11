from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.data import DataDriftReport

from ..research.regime import MarketRegimeProfile
from .paper_scorecard import PaperTradingScorecard
from .promotion import PromotionPipelineReport


TradeCommitteeAction = str


@dataclass(frozen=True)
class TradeCommitteePolicy:
    require_promotion: bool = True
    require_paper_scorecard: bool = True
    require_data_health: bool = True
    allow_benchmark_fallback: bool = True
    allow_hedging: bool = True
    reduce_on_regime_degradation: bool = True
    min_strategy_edge: float = 0.0
    min_benchmark_edge: float = 0.0
    min_regime_quality: float = 0.55
    max_position_weight: float = 0.25
    benchmark_weight: float = 0.20
    hedge_weight: float = 0.10
    exposure_reduction_multiplier: float = 0.50


@dataclass(frozen=True)
class TradeCommitteeContext:
    symbol: str
    promotion_report: PromotionPipelineReport | None = None
    paper_scorecard: PaperTradingScorecard | None = None
    data_drift_reports: Sequence[DataDriftReport] = field(default_factory=tuple)
    regime: MarketRegimeProfile | None = None
    strategy_edge: float = 0.0
    benchmark_edge: float = 0.0
    current_exposure: float = 0.0
    risk_halt: bool = False
    risk_reason: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeCommitteeGate:
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
class TradeCommitteeDecision:
    symbol: str
    action: TradeCommitteeAction
    target_weight: float
    reason: str
    gates: tuple[TradeCommitteeGate, ...]
    strategy_name: str | None = None
    hedge_weight: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.action in {"trade_strategy", "use_benchmark", "hedge", "reduce_exposure"}

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "approved": self.approved,
            "target_weight": self.target_weight,
            "strategy_name": self.strategy_name,
            "hedge_weight": self.hedge_weight,
            "reason": self.reason,
            "gates": [gate.to_dict() for gate in self.gates],
            "metadata": dict(self.metadata),
        }


def decide_trade_action(
    context: TradeCommitteeContext,
    policy: TradeCommitteePolicy | None = None,
) -> TradeCommitteeDecision:
    policy = policy or TradeCommitteePolicy()
    gates = (
        _risk_gate(context),
        _data_gate(context, policy),
        _promotion_gate(context, policy),
        _paper_gate(context, policy),
        _regime_gate(context, policy),
        _edge_gate(context, policy),
    )

    if context.risk_halt:
        return _decision(context, "cash", 0.0, "risk_halt_active", gates, policy)

    data_gate = _gate(gates, "data_health")
    if not data_gate.passed:
        return _decision(context, "cash", 0.0, data_gate.reason, gates, policy)

    promotion_gate = _gate(gates, "promotion")
    if not promotion_gate.passed:
        return _fallback_without_strategy(context, policy, gates, promotion_gate.reason)

    paper_gate = _gate(gates, "paper_behavior")
    if not paper_gate.passed:
        if policy.allow_hedging and context.current_exposure > 0:
            return _decision(context, "hedge", context.current_exposure, paper_gate.reason, gates, policy, hedge_weight=policy.hedge_weight)
        return _decision(context, "cash", 0.0, paper_gate.reason, gates, policy)

    regime_gate = _gate(gates, "regime_quality")
    if not regime_gate.passed:
        if policy.reduce_on_regime_degradation and context.current_exposure > 0:
            reduced_weight = max(context.current_exposure * policy.exposure_reduction_multiplier, 0.0)
            return _decision(context, "reduce_exposure", reduced_weight, regime_gate.reason, gates, policy)
        return _decision(context, "cash", 0.0, regime_gate.reason, gates, policy)

    edge_gate = _gate(gates, "edge")
    if context.strategy_edge > policy.min_strategy_edge and edge_gate.passed:
        return _decision(
            context,
            "trade_strategy",
            policy.max_position_weight,
            "committee_approved_strategy",
            gates,
            policy,
            strategy_name=_strategy_name(context),
        )

    if policy.allow_benchmark_fallback and context.benchmark_edge > policy.min_benchmark_edge:
        return _decision(context, "use_benchmark", policy.benchmark_weight, "benchmark_edge_preferred", gates, policy, strategy_name="benchmark")

    return _decision(context, "cash", 0.0, "no_validated_edge", gates, policy)


def _risk_gate(context: TradeCommitteeContext) -> TradeCommitteeGate:
    if context.risk_halt:
        return TradeCommitteeGate("risk_halt", False, context.risk_reason or "risk_halt_active")
    return TradeCommitteeGate("risk_halt", True, "no_risk_halt")


def _data_gate(context: TradeCommitteeContext, policy: TradeCommitteePolicy) -> TradeCommitteeGate:
    if not policy.require_data_health:
        return TradeCommitteeGate("data_health", True, "not_required")
    failed = [report for report in context.data_drift_reports if not report.passed]
    if failed:
        return TradeCommitteeGate(
            "data_health",
            False,
            "data_drift_failed",
            {
                "failed_reports": len(failed),
                "providers": [f"{report.primary_provider}/{report.comparison_provider}" for report in failed],
            },
        )
    return TradeCommitteeGate("data_health", True, "data_health_passed", {"reports": len(context.data_drift_reports)})


def _promotion_gate(context: TradeCommitteeContext, policy: TradeCommitteePolicy) -> TradeCommitteeGate:
    if not policy.require_promotion:
        return TradeCommitteeGate("promotion", True, "not_required")
    if context.promotion_report is None:
        return TradeCommitteeGate("promotion", False, "missing_promotion_report")
    if context.promotion_report.passed:
        return TradeCommitteeGate("promotion", True, "promotion_ready")
    return TradeCommitteeGate("promotion", False, context.promotion_report.reason)


def _paper_gate(context: TradeCommitteeContext, policy: TradeCommitteePolicy) -> TradeCommitteeGate:
    if not policy.require_paper_scorecard:
        return TradeCommitteeGate("paper_behavior", True, "not_required")
    if context.paper_scorecard is None:
        return TradeCommitteeGate("paper_behavior", False, "missing_paper_scorecard")
    if context.paper_scorecard.passed:
        return TradeCommitteeGate("paper_behavior", True, "paper_behavior_in_line")
    return TradeCommitteeGate("paper_behavior", False, context.paper_scorecard.reason)


def _regime_gate(context: TradeCommitteeContext, policy: TradeCommitteePolicy) -> TradeCommitteeGate:
    quality = _regime_quality(context.regime)
    if quality >= policy.min_regime_quality:
        return TradeCommitteeGate("regime_quality", True, "regime_quality_passed", {"quality": quality})
    return TradeCommitteeGate(
        "regime_quality",
        False,
        "regime_quality_below_threshold",
        {"quality": quality, "threshold": policy.min_regime_quality},
    )


def _edge_gate(context: TradeCommitteeContext, policy: TradeCommitteePolicy) -> TradeCommitteeGate:
    if context.strategy_edge > policy.min_strategy_edge:
        return TradeCommitteeGate(
            "edge",
            True,
            "strategy_edge_passed",
            {"strategy_edge": context.strategy_edge, "benchmark_edge": context.benchmark_edge},
        )
    if policy.allow_benchmark_fallback and context.benchmark_edge > policy.min_benchmark_edge:
        return TradeCommitteeGate(
            "edge",
            True,
            "benchmark_edge_available",
            {"strategy_edge": context.strategy_edge, "benchmark_edge": context.benchmark_edge},
        )
    return TradeCommitteeGate(
        "edge",
        False,
        "no_validated_edge",
        {"strategy_edge": context.strategy_edge, "benchmark_edge": context.benchmark_edge},
    )


def _regime_quality(regime: MarketRegimeProfile | None) -> float:
    if regime is None:
        return 0.60

    score = 1.0
    if regime.trend_state == "unknown":
        score -= 0.35
    elif regime.trend_state == "mixed":
        score -= 0.15
    elif regime.trend_state == "range_bound":
        score -= 0.05

    if regime.volatility_state == "unknown":
        score -= 0.15
    elif regime.volatility_state == "expansion":
        score -= 0.10

    if regime.liquidity_state == "unknown":
        score -= 0.15
    elif regime.liquidity_state == "thin":
        score -= 0.35

    if regime.macro_sensitivity == "high":
        score -= 0.05

    return round(min(max(score, 0.0), 1.0), 4)


def _fallback_without_strategy(
    context: TradeCommitteeContext,
    policy: TradeCommitteePolicy,
    gates: tuple[TradeCommitteeGate, ...],
    reason: str,
) -> TradeCommitteeDecision:
    if policy.allow_benchmark_fallback and context.benchmark_edge > policy.min_benchmark_edge:
        return _decision(context, "use_benchmark", policy.benchmark_weight, "strategy_not_promoted_benchmark_fallback", gates, policy, strategy_name="benchmark")
    return _decision(context, "cash", 0.0, reason, gates, policy)


def _decision(
    context: TradeCommitteeContext,
    action: TradeCommitteeAction,
    target_weight: float,
    reason: str,
    gates: tuple[TradeCommitteeGate, ...],
    policy: TradeCommitteePolicy,
    strategy_name: str | None = None,
    hedge_weight: float = 0.0,
) -> TradeCommitteeDecision:
    return TradeCommitteeDecision(
        symbol=context.symbol.upper(),
        action=action,
        target_weight=min(max(target_weight, 0.0), policy.max_position_weight),
        strategy_name=strategy_name,
        hedge_weight=max(hedge_weight, 0.0),
        reason=reason,
        gates=gates,
        metadata={
            "strategy_edge": context.strategy_edge,
            "benchmark_edge": context.benchmark_edge,
            "current_exposure": context.current_exposure,
            "regime_quality": _regime_quality(context.regime),
            "notes": list(context.notes),
        },
    )


def _strategy_name(context: TradeCommitteeContext) -> str | None:
    if context.promotion_report and context.promotion_report.manifest:
        return context.promotion_report.manifest.strategy_name
    if context.promotion_report:
        return context.promotion_report.evidence.strategy_name
    if context.paper_scorecard:
        return context.paper_scorecard.expectation.strategy_name
    return None


def _gate(gates: Sequence[TradeCommitteeGate], name: str) -> TradeCommitteeGate:
    return next(gate for gate in gates if gate.name == name)
