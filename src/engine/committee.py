from dataclasses import dataclass, field
from typing import Mapping, Sequence

from src.backtesting import TradeCommitteeDecision
from src.execution import GeneratedOrderIntent, TargetPositionIntent
from src.models import Order

from .account import PaperAccountState


@dataclass(frozen=True)
class CommitteeExecutionPolicy:
    allow_fractional_quantity: bool = False
    min_order_quantity: float = 1.0
    default_hedge_symbol: str = "SH"
    flatten_on_cash: bool = True


@dataclass(frozen=True)
class CommitteeExecutionPlan:
    decision: TradeCommitteeDecision
    targets: tuple[TargetPositionIntent, ...]
    orders: tuple[GeneratedOrderIntent, ...]
    reason: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_orders(self) -> bool:
        return bool(self.orders)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.to_dict(),
            "reason": self.reason,
            "has_orders": self.has_orders,
            "targets": [
                {
                    "symbol": target.symbol,
                    "target_quantity": target.target_quantity,
                }
                for target in self.targets
            ],
            "orders": [
                {
                    "symbol": intent.order.symbol,
                    "side": intent.order.side,
                    "quantity": intent.order.quantity,
                    "order_type": intent.order.order_type,
                    "source_target": intent.source_target.symbol if intent.source_target else None,
                }
                for intent in self.orders
            ],
            "warnings": list(self.warnings),
        }


def plan_committee_execution(
    decision: TradeCommitteeDecision,
    account_state: PaperAccountState,
    prices: Mapping[str, float],
    account_equity: float | None = None,
    policy: CommitteeExecutionPolicy | None = None,
) -> CommitteeExecutionPlan:
    policy = policy or CommitteeExecutionPolicy()
    equity = float(account_equity if account_equity is not None else account_state.equity(dict(prices)))
    warnings: list[str] = []

    if decision.action in {"trade_strategy", "use_benchmark"}:
        return _target_primary_symbol(decision, account_state, prices, equity, policy, warnings)
    if decision.action == "reduce_exposure":
        return _reduce_primary_symbol(decision, account_state, prices, equity, policy, warnings)
    if decision.action == "hedge":
        return _target_hedge_symbol(decision, account_state, prices, equity, policy, warnings)
    if decision.action == "cash":
        return _cash_plan(decision, account_state, policy, warnings)

    warnings.append(f"Unsupported committee action: {decision.action}.")
    return CommitteeExecutionPlan(decision, (), (), "unsupported_committee_action", tuple(warnings))


def _target_primary_symbol(
    decision: TradeCommitteeDecision,
    account_state: PaperAccountState,
    prices: Mapping[str, float],
    equity: float,
    policy: CommitteeExecutionPolicy,
    warnings: list[str],
) -> CommitteeExecutionPlan:
    target_quantity = _target_quantity(decision.symbol, decision.target_weight, equity, prices, policy, warnings)
    return _plan_quantity_change(decision, account_state, decision.symbol, target_quantity, policy, warnings)


def _reduce_primary_symbol(
    decision: TradeCommitteeDecision,
    account_state: PaperAccountState,
    prices: Mapping[str, float],
    equity: float,
    policy: CommitteeExecutionPolicy,
    warnings: list[str],
) -> CommitteeExecutionPlan:
    current_quantity = account_state.quantity(decision.symbol)
    direction = 1 if current_quantity >= 0 else -1
    target_quantity = _target_quantity(decision.symbol, decision.target_weight, equity, prices, policy, warnings) * direction
    return _plan_quantity_change(decision, account_state, decision.symbol, target_quantity, policy, warnings)


def _target_hedge_symbol(
    decision: TradeCommitteeDecision,
    account_state: PaperAccountState,
    prices: Mapping[str, float],
    equity: float,
    policy: CommitteeExecutionPolicy,
    warnings: list[str],
) -> CommitteeExecutionPlan:
    hedge_symbol = str(decision.metadata.get("hedge_symbol", policy.default_hedge_symbol)).upper()
    target_quantity = _target_quantity(hedge_symbol, decision.hedge_weight, equity, prices, policy, warnings)
    return _plan_quantity_change(decision, account_state, hedge_symbol, target_quantity, policy, warnings)


def _cash_plan(
    decision: TradeCommitteeDecision,
    account_state: PaperAccountState,
    policy: CommitteeExecutionPolicy,
    warnings: list[str],
) -> CommitteeExecutionPlan:
    if not policy.flatten_on_cash:
        return CommitteeExecutionPlan(decision, (), (), "cash_without_flatten", tuple(warnings))
    targets: list[TargetPositionIntent] = []
    orders: list[GeneratedOrderIntent] = []
    for symbol in sorted(account_state.positions):
        plan = _plan_quantity_change(decision, account_state, symbol, 0.0, policy, warnings)
        targets.extend(plan.targets)
        orders.extend(plan.orders)
    return CommitteeExecutionPlan(decision, tuple(targets), tuple(orders), "cash_flatten_plan", tuple(warnings))


def _plan_quantity_change(
    decision: TradeCommitteeDecision,
    account_state: PaperAccountState,
    symbol: str,
    target_quantity: float,
    policy: CommitteeExecutionPolicy,
    warnings: list[str],
) -> CommitteeExecutionPlan:
    target_quantity = _normalize_quantity(target_quantity, policy)
    current_quantity = account_state.quantity(symbol)
    delta = target_quantity - current_quantity
    target = TargetPositionIntent(symbol=symbol.upper(), target_quantity=target_quantity)
    if abs(delta) < policy.min_order_quantity:
        return CommitteeExecutionPlan(decision, (target,), (), "target_already_satisfied", tuple(warnings))

    order = Order(symbol=symbol.upper(), side="BUY" if delta > 0 else "SELL", quantity=abs(delta))
    return CommitteeExecutionPlan(
        decision,
        (target,),
        (GeneratedOrderIntent(order=order, source_target=target),),
        decision.reason,
        tuple(warnings),
    )


def _target_quantity(
    symbol: str,
    target_weight: float,
    equity: float,
    prices: Mapping[str, float],
    policy: CommitteeExecutionPolicy,
    warnings: list[str],
) -> float:
    price = prices.get(symbol.upper()) or prices.get(symbol)
    if price is None or price <= 0:
        warnings.append(f"Missing valid price for {symbol.upper()}.")
        return 0.0
    return _normalize_quantity((equity * target_weight) / float(price), policy)


def _normalize_quantity(quantity: float, policy: CommitteeExecutionPolicy) -> float:
    if policy.allow_fractional_quantity:
        return round(quantity, 6)
    if abs(quantity) < policy.min_order_quantity:
        return 0.0
    return float(int(quantity))
