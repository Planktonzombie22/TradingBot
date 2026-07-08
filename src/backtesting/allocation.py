from dataclasses import dataclass
from typing import Sequence

from .scorecards import ScorecardReport, SymbolResearchScorecard


@dataclass(frozen=True)
class EnsembleAllocationPolicy:
    min_strategy_excess_return: float = 0.0
    min_benchmark_return: float = 0.0
    min_robustness_score: float = 0.0
    max_symbol_weight: float = 0.20
    cash_reserve: float = 0.10
    allow_benchmark_fallback: bool = True


@dataclass(frozen=True)
class EnsembleAllocationDecision:
    symbol: str
    action: str
    strategy: str | None
    weight: float
    reason: str
    score: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "strategy": self.strategy,
            "weight": self.weight,
            "reason": self.reason,
            "score": self.score,
        }


@dataclass(frozen=True)
class EnsembleAllocationPlan:
    policy: EnsembleAllocationPolicy
    decisions: tuple[EnsembleAllocationDecision, ...]

    @property
    def invested_weight(self) -> float:
        return sum(decision.weight for decision in self.decisions if decision.action != "cash")

    @property
    def cash_weight(self) -> float:
        return max(0.0, 1.0 - self.invested_weight)

    def to_dict(self) -> dict:
        return {
            "policy": {
                "min_strategy_excess_return": self.policy.min_strategy_excess_return,
                "min_benchmark_return": self.policy.min_benchmark_return,
                "min_robustness_score": self.policy.min_robustness_score,
                "max_symbol_weight": self.policy.max_symbol_weight,
                "cash_reserve": self.policy.cash_reserve,
                "allow_benchmark_fallback": self.policy.allow_benchmark_fallback,
            },
            "invested_weight": self.invested_weight,
            "cash_weight": self.cash_weight,
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


def build_ensemble_allocation(
    scorecards: ScorecardReport | Sequence[SymbolResearchScorecard],
    policy: EnsembleAllocationPolicy | None = None,
) -> EnsembleAllocationPlan:
    """Choose strategy, benchmark, or cash per symbol from validated scorecards."""

    policy = policy or EnsembleAllocationPolicy()
    cards = tuple(scorecards.scorecards if isinstance(scorecards, ScorecardReport) else scorecards)
    raw_decisions = tuple(_decision_for_scorecard(card, policy) for card in cards)
    weighted = _assign_weights(raw_decisions, policy)
    return EnsembleAllocationPlan(policy=policy, decisions=weighted)


def _decision_for_scorecard(
    scorecard: SymbolResearchScorecard,
    policy: EnsembleAllocationPolicy,
) -> EnsembleAllocationDecision:
    selected_entry = next((entry for entry in scorecard.strategy_entries if entry.strategy == scorecard.selected_strategy), None)
    strategy_is_active = scorecard.selected_strategy in scorecard.active_strategies or not scorecard.active_strategies
    strategy_is_valid = (
        scorecard.selected_action == "trade_strategy"
        and strategy_is_active
        and selected_entry is not None
        and selected_entry.best_excess_return >= policy.min_strategy_excess_return
        and selected_entry.robustness_score >= policy.min_robustness_score
    )
    if strategy_is_valid:
        return EnsembleAllocationDecision(
            symbol=scorecard.symbol,
            action="strategy",
            strategy=scorecard.selected_strategy,
            weight=0.0,
            reason="validated_strategy_edge",
            score=selected_entry.robustness_score,
        )

    if policy.allow_benchmark_fallback and scorecard.benchmark_return >= policy.min_benchmark_return:
        return EnsembleAllocationDecision(
            symbol=scorecard.symbol,
            action="benchmark",
            strategy=scorecard.benchmark_strategy,
            weight=0.0,
            reason="benchmark_preferred",
            score=scorecard.benchmark_return,
        )

    return EnsembleAllocationDecision(
        symbol=scorecard.symbol,
        action="cash",
        strategy=None,
        weight=0.0,
        reason="no_valid_edge",
        score=0.0,
    )


def _assign_weights(
    decisions: Sequence[EnsembleAllocationDecision],
    policy: EnsembleAllocationPolicy,
) -> tuple[EnsembleAllocationDecision, ...]:
    candidates = [decision for decision in decisions if decision.action != "cash"]
    if not candidates:
        return tuple(decisions)

    available_weight = max(0.0, 1.0 - policy.cash_reserve)
    equal_weight = min(policy.max_symbol_weight, available_weight / len(candidates))
    remaining = available_weight
    weighted = []
    for decision in decisions:
        if decision.action == "cash" or remaining <= 0:
            weighted.append(decision)
            continue
        weight = min(equal_weight, remaining)
        weighted.append(
            EnsembleAllocationDecision(
                symbol=decision.symbol,
                action=decision.action,
                strategy=decision.strategy,
                weight=weight,
                reason=decision.reason,
                score=decision.score,
            )
        )
        remaining -= weight
    return tuple(weighted)
