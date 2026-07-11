from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CapitalLedgerPolicy:
    cash_reserve: float = 0.10
    max_symbol_weight: float = 0.25
    max_strategy_weight: float = 0.25
    max_family_weight: float = 0.40
    hedge_budget: float = 0.10
    min_edge_score: float = 0.0


@dataclass(frozen=True)
class CapitalRequest:
    strategy_name: str
    symbol: str
    action: str
    requested_weight: float
    family: str = "default"
    edge_score: float = 0.0
    priority: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "action": self.action,
            "requested_weight": self.requested_weight,
            "family": self.family,
            "edge_score": self.edge_score,
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CapitalAllocation:
    request: CapitalRequest
    allocated_weight: float
    reason: str

    @property
    def accepted(self) -> bool:
        return self.allocated_weight > 0

    def to_dict(self) -> dict:
        return {
            "request": self.request.to_dict(),
            "allocated_weight": self.allocated_weight,
            "accepted": self.accepted,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CapitalLedgerReport:
    policy: CapitalLedgerPolicy
    allocations: tuple[CapitalAllocation, ...]

    @property
    def invested_weight(self) -> float:
        return round(sum(allocation.allocated_weight for allocation in self.allocations if allocation.request.action != "hedge"), 10)

    @property
    def hedge_weight(self) -> float:
        return round(sum(allocation.allocated_weight for allocation in self.allocations if allocation.request.action == "hedge"), 10)

    @property
    def cash_weight(self) -> float:
        return round(max(0.0, 1.0 - self.invested_weight - self.hedge_weight), 10)

    @property
    def weights_by_symbol(self) -> dict[str, float]:
        weights: dict[str, float] = {}
        for allocation in self.allocations:
            if allocation.accepted:
                weights[allocation.request.symbol] = weights.get(allocation.request.symbol, 0.0) + allocation.allocated_weight
        return weights

    @property
    def weights_by_family(self) -> dict[str, float]:
        weights: dict[str, float] = {}
        for allocation in self.allocations:
            if allocation.accepted:
                weights[allocation.request.family] = weights.get(allocation.request.family, 0.0) + allocation.allocated_weight
        return weights

    def to_dict(self) -> dict:
        return {
            "policy": {
                "cash_reserve": self.policy.cash_reserve,
                "max_symbol_weight": self.policy.max_symbol_weight,
                "max_strategy_weight": self.policy.max_strategy_weight,
                "max_family_weight": self.policy.max_family_weight,
                "hedge_budget": self.policy.hedge_budget,
                "min_edge_score": self.policy.min_edge_score,
            },
            "invested_weight": self.invested_weight,
            "hedge_weight": self.hedge_weight,
            "cash_weight": self.cash_weight,
            "weights_by_symbol": self.weights_by_symbol,
            "weights_by_family": self.weights_by_family,
            "allocations": [allocation.to_dict() for allocation in self.allocations],
        }


def allocate_capital_requests(
    requests: Sequence[CapitalRequest],
    policy: CapitalLedgerPolicy | None = None,
) -> CapitalLedgerReport:
    policy = policy or CapitalLedgerPolicy()
    allocations: list[CapitalAllocation] = []
    primary_remaining = max(0.0, 1.0 - policy.cash_reserve)
    hedge_remaining = max(0.0, policy.hedge_budget)
    symbol_weights: dict[str, float] = {}
    strategy_weights: dict[str, float] = {}
    family_weights: dict[str, float] = {}

    for request in sorted(requests, key=lambda item: (item.priority, item.edge_score), reverse=True):
        if request.action not in {"trade_strategy", "use_benchmark", "hedge"}:
            allocations.append(CapitalAllocation(request, 0.0, "non_allocating_committee_action"))
            continue
        if request.action != "hedge" and request.edge_score < policy.min_edge_score:
            allocations.append(CapitalAllocation(request, 0.0, "edge_below_capital_threshold"))
            continue

        budget_remaining = hedge_remaining if request.action == "hedge" else primary_remaining
        symbol_remaining = max(0.0, policy.max_symbol_weight - symbol_weights.get(request.symbol, 0.0))
        strategy_remaining = max(0.0, policy.max_strategy_weight - strategy_weights.get(request.strategy_name, 0.0))
        family_remaining = max(0.0, policy.max_family_weight - family_weights.get(request.family, 0.0))
        allocation = min(
            max(request.requested_weight, 0.0),
            budget_remaining,
            symbol_remaining,
            strategy_remaining,
            family_remaining,
        )

        if allocation <= 0:
            allocations.append(CapitalAllocation(request, 0.0, "capital_cap_exhausted"))
            continue

        symbol_weights[request.symbol] = symbol_weights.get(request.symbol, 0.0) + allocation
        strategy_weights[request.strategy_name] = strategy_weights.get(request.strategy_name, 0.0) + allocation
        family_weights[request.family] = family_weights.get(request.family, 0.0) + allocation
        if request.action == "hedge":
            hedge_remaining -= allocation
        else:
            primary_remaining -= allocation
        reason = "allocated_requested_weight" if allocation == request.requested_weight else "allocated_capped_weight"
        allocations.append(CapitalAllocation(request, round(allocation, 10), reason))

    return CapitalLedgerReport(policy, tuple(allocations))


def capital_request_from_decision(
    decision: Any,
    family: str = "default",
    priority: int = 0,
) -> CapitalRequest:
    strategy_name = decision.strategy_name or decision.action
    requested_weight = decision.hedge_weight if decision.action == "hedge" else decision.target_weight
    edge_score = float(decision.metadata.get("strategy_edge", decision.metadata.get("benchmark_edge", 0.0)))
    return CapitalRequest(
        strategy_name=strategy_name,
        symbol=decision.symbol,
        action=decision.action,
        requested_weight=requested_weight,
        family=family,
        edge_score=edge_score,
        priority=priority,
        metadata=decision.metadata,
    )
