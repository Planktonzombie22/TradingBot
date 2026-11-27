import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


OPEN_ORDER_STATUSES = {"PENDING", "ACCEPTED", "NEW", "PARTIALLY_FILLED"}
CLOSED_ORDER_STATUSES = {"FILLED", "CANCELLED", "CANCELED", "REJECTED", "EXPIRED"}
DEFAULT_STALE_OPEN_ORDER_MINUTES = 15.0
DEFAULT_EXECUTION_TEMPLATES = {
    "market_on_open": {"order_type": "MARKET", "time_in_force": "opg", "requires_regular_session": True},
    "intraday_market": {"order_type": "MARKET", "time_in_force": "day", "requires_regular_session": True},
    "limit_with_timeout": {"order_type": "LIMIT", "time_in_force": "day", "timeout_minutes": 5.0},
    "bracket": {"order_type": "MARKET", "time_in_force": "day", "requires_stop_loss": True, "requires_take_profit": True},
    "oco": {"order_type": "LIMIT", "time_in_force": "gtc", "requires_stop_loss": True, "requires_take_profit": True},
    "trailing_stop": {"order_type": "TRAILING_STOP", "time_in_force": "gtc", "requires_trail": True},
    "close_only": {"order_type": "MARKET", "time_in_force": "day", "close_only": True},
}


@dataclass(frozen=True)
class PaperOpenOrderStatus:
    symbol: str
    side: str
    quantity: float
    status: str
    order_type: str | None = None
    time_in_force: str | None = None
    created_at: str | None = None
    age_minutes: float | None = None
    expected_active: bool = False
    stale: bool = False
    source: str = "unknown"
    cancel_reference: str | None = None
    reason: str = "passed"

    @property
    def unresolved(self) -> bool:
        return self.status.upper() in OPEN_ORDER_STATUSES

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "status": self.status,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "created_at": self.created_at,
            "age_minutes": self.age_minutes,
            "expected_active": self.expected_active,
            "unresolved": self.unresolved,
            "stale": self.stale,
            "source": self.source,
            "cancel_reference_available": bool(self.cancel_reference),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperOpenOrderReport:
    orders: tuple[PaperOpenOrderStatus, ...]
    observed_at: str
    max_open_order_age_minutes: float = DEFAULT_STALE_OPEN_ORDER_MINUTES
    artifact_path: str | None = None

    @property
    def unresolved_orders(self) -> int:
        return sum(1 for order in self.orders if order.unresolved)

    @property
    def stale_orders(self) -> int:
        return sum(1 for order in self.orders if order.stale)

    @property
    def stale_symbols(self) -> tuple[str, ...]:
        return tuple(order.symbol for order in self.orders if order.stale)

    @property
    def passed(self) -> bool:
        return self.stale_orders == 0

    @property
    def reason(self) -> str:
        if self.stale_orders:
            return "stale_open_paper_orders"
        if self.unresolved_orders:
            return "open_paper_orders_within_timeout"
        return "passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "observed_at": self.observed_at,
            "max_open_order_age_minutes": self.max_open_order_age_minutes,
            "unresolved_orders": self.unresolved_orders,
            "stale_orders": self.stale_orders,
            "stale_symbols": list(self.stale_symbols),
            "orders": [order.to_dict() for order in self.orders],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PaperStaleOrderCancelAttempt:
    symbol: str
    side: str
    quantity: float
    order_status: str
    age_minutes: float | None
    cancel_requested: bool
    attempted: bool
    acknowledged: bool
    cancel_reference_available: bool
    reason: str

    @property
    def passed(self) -> bool:
        return (not self.cancel_requested and not self.attempted) or self.acknowledged

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_status": self.order_status,
            "age_minutes": self.age_minutes,
            "cancel_requested": self.cancel_requested,
            "attempted": self.attempted,
            "acknowledged": self.acknowledged,
            "cancel_reference_available": self.cancel_reference_available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperStaleOrderCancelReport:
    open_order_report: PaperOpenOrderReport
    attempts: tuple[PaperStaleOrderCancelAttempt, ...]
    cancel_requested: bool = False
    artifact_path: str | None = None

    @property
    def stale_orders(self) -> int:
        return self.open_order_report.stale_orders

    @property
    def attempted(self) -> bool:
        return any(attempt.attempted for attempt in self.attempts)

    @property
    def acknowledged(self) -> bool:
        return all(attempt.acknowledged for attempt in self.attempts) if self.attempts else True

    @property
    def passed(self) -> bool:
        if not self.stale_orders:
            return True
        return bool(self.cancel_requested and self.attempted and self.acknowledged)

    @property
    def reason(self) -> str:
        if not self.stale_orders:
            return "no_stale_open_orders"
        if not self.cancel_requested:
            return "stale_order_cancel_required"
        if not self.attempted:
            return "stale_order_cancel_not_attempted"
        if not self.acknowledged:
            return "stale_order_cancel_failed"
        return "stale_order_cancel_acknowledged"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "cancel_requested": self.cancel_requested,
            "attempted": self.attempted,
            "acknowledged": self.acknowledged,
            "stale_orders": self.stale_orders,
            "open_order_report": self.open_order_report.to_dict(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ExecutionTemplateSpec:
    name: str
    order_type: str
    time_in_force: str
    requires_regular_session: bool = False
    requires_stop_loss: bool = False
    requires_take_profit: bool = False
    requires_trail: bool = False
    close_only: bool = False
    timeout_minutes: float | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "requires_regular_session": self.requires_regular_session,
            "requires_stop_loss": self.requires_stop_loss,
            "requires_take_profit": self.requires_take_profit,
            "requires_trail": self.requires_trail,
            "close_only": self.close_only,
            "timeout_minutes": self.timeout_minutes,
        }


@dataclass(frozen=True)
class ExecutionTemplateSelection:
    symbol: str
    strategy_family: str
    template_name: str
    order_type: str
    time_in_force: str
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy_family": self.strategy_family,
            "template_name": self.template_name,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ExecutionTemplateReport:
    selections: tuple[ExecutionTemplateSelection, ...]
    templates: tuple[ExecutionTemplateSpec, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(selection.passed for selection in self.selections)

    @property
    def reason(self) -> str:
        if self.passed:
            return "execution_templates_selected"
        return next(selection.reason for selection in self.selections if not selection.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "templates": [template.to_dict() for template in self.templates],
            "selections": [selection.to_dict() for selection in self.selections],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class BracketOrderLeg:
    symbol: str
    side: str
    quantity: float
    order_type: str
    limit_price: float | None
    stop_price: float | None
    time_in_force: str
    role: str
    parent_role: str | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "time_in_force": self.time_in_force,
            "role": self.role,
            "parent_role": self.parent_role,
        }


@dataclass(frozen=True)
class BracketOrderPlan:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    legs: tuple[BracketOrderLeg, ...]
    reason: str = "passed"
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "legs": [leg.to_dict() for leg in self.legs],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ReplaceOrderDecision:
    symbol: str
    side: str
    current_limit_price: float | None
    replacement_limit_price: float | None
    age_minutes: float | None
    action: str
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason in {"replace_planned", "keep_order"}

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "current_limit_price": self.current_limit_price,
            "replacement_limit_price": self.replacement_limit_price,
            "age_minutes": self.age_minutes,
            "action": self.action,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReplaceOrderReport:
    decisions: tuple[ReplaceOrderDecision, ...]
    timeout_minutes: float = 5.0
    price_improvement_bps: float = 2.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def replacements_planned(self) -> int:
        return sum(1 for decision in self.decisions if decision.action == "cancel_replace")

    @property
    def reason(self) -> str:
        if self.passed:
            return "replace_order_policy_evaluated"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "timeout_minutes": self.timeout_minutes,
            "price_improvement_bps": self.price_improvement_bps,
            "replacements_planned": self.replacements_planned,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PartialFillReconciliation:
    symbol: str
    side: str
    requested_quantity: float
    filled_quantity: float
    remaining_quantity: float
    average_fill_price: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason in {"filled", "partial_fill_tracked", "unfilled_tracked"}

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PartialFillReconciliationReport:
    reconciliations: tuple[PartialFillReconciliation, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(reconciliation.passed for reconciliation in self.reconciliations)

    @property
    def partial_fills(self) -> int:
        return sum(1 for reconciliation in self.reconciliations if reconciliation.reason == "partial_fill_tracked")

    @property
    def reason(self) -> str:
        if self.passed:
            return "partial_fill_reconciliation_passed"
        return next(reconciliation.reason for reconciliation in self.reconciliations if not reconciliation.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "partial_fills": self.partial_fills,
            "reconciliations": [reconciliation.to_dict() for reconciliation in self.reconciliations],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ClientOrderIdReplayCheck:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    prior_status: str | None
    action: str
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason in {"new_order_allowed", "duplicate_blocked", "retry_existing_open_order"}

    def to_dict(self) -> dict:
        return {
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "prior_status": self.prior_status,
            "action": self.action,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ClientOrderIdReplayReport:
    checks: tuple[ClientOrderIdReplayCheck, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def blocked_duplicates(self) -> int:
        return sum(1 for check in self.checks if check.action == "block_duplicate_submit")

    @property
    def reason(self) -> str:
        if self.passed:
            return "client_order_id_replay_checked"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "blocked_duplicates": self.blocked_duplicates,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PreSubmitOrderPreviewLine:
    symbol: str
    side: str
    quantity: float
    order_type: str
    time_in_force: str | None
    estimated_price: float | None
    estimated_notional: float | None
    price_source: str
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "estimated_price": self.estimated_price,
            "estimated_notional": self.estimated_notional,
            "price_source": self.price_source,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PreSubmitOrderPreviewReport:
    lines: tuple[PreSubmitOrderPreviewLine, ...]
    risk_gates_passed: bool = True
    approval_policy_passed: bool = True
    artifact_path: str | None = None

    @property
    def total_estimated_notional(self) -> float:
        return sum(line.estimated_notional or 0.0 for line in self.lines)

    @property
    def passed(self) -> bool:
        return self.risk_gates_passed and self.approval_policy_passed and all(line.passed for line in self.lines)

    @property
    def reason(self) -> str:
        if not self.risk_gates_passed:
            return "risk_gates_blocked_preview"
        if not self.approval_policy_passed:
            return "approval_policy_blocked_preview"
        if self.passed:
            return "pre_submit_preview_passed"
        return next(line.reason for line in self.lines if not line.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "risk_gates_passed": self.risk_gates_passed,
            "approval_policy_passed": self.approval_policy_passed,
            "total_estimated_notional": self.total_estimated_notional,
            "lines": [line.to_dict() for line in self.lines],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class OrderCountGateReport:
    orders: int
    max_session_orders: int | None
    max_orders_per_symbol: int | None
    per_symbol_counts: Mapping[str, int]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        if self.max_session_orders is not None and self.orders > self.max_session_orders:
            return False
        if self.max_orders_per_symbol is not None:
            return all(count <= self.max_orders_per_symbol for count in self.per_symbol_counts.values())
        return True

    @property
    def reason(self) -> str:
        if self.max_session_orders is not None and self.orders > self.max_session_orders:
            return "session_order_count_above_limit"
        if self.max_orders_per_symbol is not None:
            if any(count > self.max_orders_per_symbol for count in self.per_symbol_counts.values()):
                return "symbol_order_count_above_limit"
        return "order_count_gates_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "orders": self.orders,
            "max_session_orders": self.max_session_orders,
            "max_orders_per_symbol": self.max_orders_per_symbol,
            "per_symbol_counts": dict(self.per_symbol_counts),
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class TurnoverGateReport:
    daily_turnover: float
    equity: float
    daily_turnover_pct: float | None
    strategy_turnover: Mapping[str, float]
    max_daily_turnover_pct: float | None = None
    max_strategy_turnover: float | None = None
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        if self.max_daily_turnover_pct is not None and self.daily_turnover_pct is not None:
            if self.daily_turnover_pct > self.max_daily_turnover_pct:
                return False
        if self.max_strategy_turnover is not None:
            if any(value > self.max_strategy_turnover for value in self.strategy_turnover.values()):
                return False
        return True

    @property
    def reason(self) -> str:
        if self.max_daily_turnover_pct is not None and self.daily_turnover_pct is not None:
            if self.daily_turnover_pct > self.max_daily_turnover_pct:
                return "daily_turnover_above_limit"
        if self.max_strategy_turnover is not None:
            if any(value > self.max_strategy_turnover for value in self.strategy_turnover.values()):
                return "strategy_turnover_above_limit"
        return "turnover_gates_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "daily_turnover": self.daily_turnover,
            "equity": self.equity,
            "daily_turnover_pct": self.daily_turnover_pct,
            "strategy_turnover": dict(self.strategy_turnover),
            "max_daily_turnover_pct": self.max_daily_turnover_pct,
            "max_strategy_turnover": self.max_strategy_turnover,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class RealizedSlippageStatus:
    symbol: str
    strategy_name: str
    side: str
    expected_price: float | None
    fill_price: float | None
    slippage_bps: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason in {"passed", "missing_reference_price"}

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "side": self.side,
            "expected_price": self.expected_price,
            "fill_price": self.fill_price,
            "slippage_bps": self.slippage_bps,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RealizedSlippageHaltReport:
    statuses: tuple[RealizedSlippageStatus, ...]
    max_slippage_bps: float = 35.0
    halt_after_breaches: int = 2
    artifact_path: str | None = None

    @property
    def breaches(self) -> int:
        return sum(1 for status in self.statuses if status.reason == "realized_slippage_above_limit")

    @property
    def halted(self) -> bool:
        return self.breaches >= self.halt_after_breaches

    @property
    def passed(self) -> bool:
        return not self.halted

    @property
    def reason(self) -> str:
        return "realized_slippage_halt_triggered" if self.halted else "realized_slippage_within_limits"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "halted": self.halted,
            "breaches": self.breaches,
            "max_slippage_bps": self.max_slippage_bps,
            "halt_after_breaches": self.halt_after_breaches,
            "statuses": [status.to_dict() for status in self.statuses],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class RejectedOrderCooldown:
    symbol: str
    strategy_name: str
    rejects: int
    cooldown_required: bool
    cooldown_until: str | None
    reason: str

    @property
    def passed(self) -> bool:
        return not self.cooldown_required

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "rejects": self.rejects,
            "cooldown_required": self.cooldown_required,
            "cooldown_until": self.cooldown_until,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RejectedOrderCooldownReport:
    cooldowns: tuple[RejectedOrderCooldown, ...]
    max_rejects: int = 2
    cooldown_minutes: float = 60.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(cooldown.passed for cooldown in self.cooldowns)

    @property
    def reason(self) -> str:
        if self.passed:
            return "reject_cooldowns_clear"
        return "reject_cooldown_required"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_rejects": self.max_rejects,
            "cooldown_minutes": self.cooldown_minutes,
            "cooldowns": [cooldown.to_dict() for cooldown in self.cooldowns],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class LiquidityParticipationStatus:
    symbol: str
    quantity: float
    estimated_notional: float | None
    average_volume: float | None
    participation_pct: float | None
    spread_bps: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "estimated_notional": self.estimated_notional,
            "average_volume": self.average_volume,
            "participation_pct": self.participation_pct,
            "spread_bps": self.spread_bps,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LiquidityParticipationReport:
    statuses: tuple[LiquidityParticipationStatus, ...]
    max_participation_pct: float = 1.0
    min_average_volume: float = 100_000.0
    max_spread_bps: float = 25.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(status.passed for status in self.statuses)

    @property
    def reason(self) -> str:
        if self.passed:
            return "liquidity_participation_passed"
        return next(status.reason for status in self.statuses if not status.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_participation_pct": self.max_participation_pct,
            "min_average_volume": self.min_average_volume,
            "max_spread_bps": self.max_spread_bps,
            "statuses": [status.to_dict() for status in self.statuses],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class BrokerRoundingDecision:
    symbol: str
    asset_class: str
    original_quantity: float
    rounded_quantity: float
    estimated_notional: float | None
    minimum_notional: float
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason in {"passed", "quantity_rounded"}

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "original_quantity": self.original_quantity,
            "rounded_quantity": self.rounded_quantity,
            "estimated_notional": self.estimated_notional,
            "minimum_notional": self.minimum_notional,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BrokerRoundingReport:
    decisions: tuple[BrokerRoundingDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "broker_rounding_passed"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StopExitVisibilityStatus:
    symbol: str
    position_quantity: float
    stop_visible: bool
    exit_visible: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "position_quantity": self.position_quantity,
            "stop_visible": self.stop_visible,
            "exit_visible": self.exit_visible,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StopExitVisibilityReport:
    statuses: tuple[StopExitVisibilityStatus, ...]
    require_stop: bool = True
    require_exit: bool = True
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(status.passed for status in self.statuses)

    @property
    def reason(self) -> str:
        if self.passed:
            return "stop_exit_visibility_passed"
        return next(status.reason for status in self.statuses if not status.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "require_stop": self.require_stop,
            "require_exit": self.require_exit,
            "statuses": [status.to_dict() for status in self.statuses],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class QuoteDepthStatus:
    symbol: str
    bid_depth_notional: float
    ask_depth_notional: float
    spread_bps: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "bid_depth_notional": self.bid_depth_notional,
            "ask_depth_notional": self.ask_depth_notional,
            "spread_bps": self.spread_bps,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QuoteDepthReport:
    statuses: tuple[QuoteDepthStatus, ...]
    min_depth_notional: float = 10_000.0
    max_spread_bps: float = 25.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(status.passed for status in self.statuses)

    @property
    def reason(self) -> str:
        if self.passed:
            return "quote_depth_passed"
        return next(status.reason for status in self.statuses if not status.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "min_depth_notional": self.min_depth_notional,
            "max_spread_bps": self.max_spread_bps,
            "statuses": [status.to_dict() for status in self.statuses],
            "artifact_path": self.artifact_path,
        }


def build_paper_open_order_report(
    portfolio_report: Mapping[str, Any],
    open_order_snapshot: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    max_open_order_age_minutes: float = DEFAULT_STALE_OPEN_ORDER_MINUTES,
) -> PaperOpenOrderReport:
    observed_at = now or datetime.now(timezone.utc)
    expected_keys = _expected_submitted_order_keys(portfolio_report)
    payloads = _open_order_payloads(portfolio_report, open_order_snapshot)
    orders = tuple(
        _open_order_status(
            payload,
            expected_keys,
            observed_at,
            max_open_order_age_minutes,
        )
        for payload in payloads
    )
    return PaperOpenOrderReport(
        orders=orders,
        observed_at=observed_at.isoformat(),
        max_open_order_age_minutes=max_open_order_age_minutes,
    )


def write_paper_open_order_report(report: PaperOpenOrderReport, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def build_paper_stale_order_cancel_report(
    open_order_report: PaperOpenOrderReport,
    cancel_requested: bool = False,
) -> PaperStaleOrderCancelReport:
    attempts = tuple(
        _cancel_attempt_from_status(order, cancel_requested, acknowledged=False, attempted=False, reason="cancel_preview_only")
        for order in open_order_report.orders
        if order.stale
    )
    return PaperStaleOrderCancelReport(
        open_order_report=open_order_report,
        attempts=attempts,
        cancel_requested=cancel_requested,
    )


def run_paper_stale_order_cancel(
    open_order_report: PaperOpenOrderReport,
    broker: Any | None = None,
    cancel_requested: bool = False,
) -> PaperStaleOrderCancelReport:
    if not cancel_requested or broker is None:
        return build_paper_stale_order_cancel_report(open_order_report, cancel_requested=cancel_requested)
    attempts = tuple(_execute_cancel(order, broker) for order in open_order_report.orders if order.stale)
    return PaperStaleOrderCancelReport(
        open_order_report=open_order_report,
        attempts=attempts,
        cancel_requested=cancel_requested,
    )


def write_paper_stale_order_cancel_report(report: PaperStaleOrderCancelReport, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def paper_open_order_snapshot_from_broker(broker: Any) -> dict:
    return {
        "open_orders": [_order_payload(order) for order in broker.open_orders()],
    }


def build_execution_template_report(
    order_intents: Sequence[Mapping[str, Any]],
    strategy_family_templates: Mapping[str, str] | None = None,
    templates: Mapping[str, Mapping[str, Any]] | None = None,
) -> ExecutionTemplateReport:
    template_specs = _execution_template_specs(templates or DEFAULT_EXECUTION_TEMPLATES)
    template_by_name = {template.name: template for template in template_specs}
    family_templates = {
        "trend": "limit_with_timeout",
        "mean_reversion": "limit_with_timeout",
        "breakout": "bracket",
        "close": "close_only",
        "risk_exit": "close_only",
        **dict(strategy_family_templates or {}),
    }
    selections = tuple(_template_selection(intent, family_templates, template_by_name) for intent in order_intents)
    return ExecutionTemplateReport(selections=selections, templates=template_specs)


def build_bracket_order_plan(
    order: Mapping[str, Any],
    entry_price: float | None = None,
    stop_loss_pct: float = 0.02,
    take_profit_pct: float = 0.04,
    time_in_force: str = "gtc",
) -> BracketOrderPlan:
    symbol = str(order.get("symbol") or "").upper()
    side = str(order.get("side") or "").upper()
    quantity = float(order.get("quantity") or order.get("qty") or 0.0)
    entry = float(entry_price or order.get("limit_price") or order.get("estimated_price") or order.get("price") or 0.0)
    if quantity <= 0 or entry <= 0 or side not in {"BUY", "SELL"}:
        return BracketOrderPlan(symbol, side, quantity, entry, 0.0, 0.0, (), "invalid_bracket_order_input")
    exit_side = "SELL" if side == "BUY" else "BUY"
    if side == "BUY":
        stop_price = entry * (1.0 - stop_loss_pct)
        take_profit = entry * (1.0 + take_profit_pct)
    else:
        stop_price = entry * (1.0 + stop_loss_pct)
        take_profit = entry * (1.0 - take_profit_pct)
    legs = (
        BracketOrderLeg(symbol, side, quantity, "MARKET", None, None, "day", "entry"),
        BracketOrderLeg(symbol, exit_side, quantity, "STOP", None, round(stop_price, 4), time_in_force, "stop_loss", "entry"),
        BracketOrderLeg(symbol, exit_side, quantity, "LIMIT", round(take_profit, 4), None, time_in_force, "take_profit", "entry"),
    )
    return BracketOrderPlan(symbol, side, quantity, entry, round(stop_price, 4), round(take_profit, 4), legs)


def build_replace_order_report(
    open_orders: Sequence[Mapping[str, Any]],
    quotes: Mapping[str, Mapping[str, Any]],
    now: datetime | None = None,
    timeout_minutes: float = 5.0,
    price_improvement_bps: float = 2.0,
) -> ReplaceOrderReport:
    observed_at = now or datetime.now(timezone.utc)
    decisions = tuple(
        _replace_order_decision(order, quotes.get(str(order.get("symbol") or "").upper(), {}), observed_at, timeout_minutes, price_improvement_bps)
        for order in open_orders
    )
    return ReplaceOrderReport(decisions=decisions, timeout_minutes=timeout_minutes, price_improvement_bps=price_improvement_bps)


def build_partial_fill_reconciliation_report(
    submitted_orders: Sequence[Mapping[str, Any]],
    execution_reports: Sequence[Mapping[str, Any]],
) -> PartialFillReconciliationReport:
    reports_by_key = {_order_match_key(report): report for report in execution_reports}
    reconciliations = tuple(_partial_fill_reconciliation(order, reports_by_key.get(_order_match_key(order))) for order in submitted_orders)
    return PartialFillReconciliationReport(reconciliations=reconciliations)


def build_client_order_id_replay_report(
    intended_orders: Sequence[Mapping[str, Any]],
    prior_submissions: Sequence[Mapping[str, Any]],
) -> ClientOrderIdReplayReport:
    prior_by_id = {
        str(order.get("client_order_id")): order
        for order in prior_submissions
        if order.get("client_order_id")
    }
    checks = tuple(_client_order_id_check(order, prior_by_id.get(str(order.get("client_order_id") or ""))) for order in intended_orders)
    return ClientOrderIdReplayReport(checks=checks)


def build_pre_submit_order_preview(
    orders: Sequence[Mapping[str, Any]],
    prices: Mapping[str, Any],
    risk_gates_passed: bool = True,
    approval_policy_passed: bool = True,
) -> PreSubmitOrderPreviewReport:
    lines = tuple(_pre_submit_line(order, prices.get(str(order.get("symbol") or "").upper())) for order in orders)
    return PreSubmitOrderPreviewReport(lines, risk_gates_passed=risk_gates_passed, approval_policy_passed=approval_policy_passed)


def build_order_count_gate_report(
    orders: Sequence[Mapping[str, Any]],
    max_session_orders: int | None = None,
    max_orders_per_symbol: int | None = None,
) -> OrderCountGateReport:
    counts: dict[str, int] = {}
    for order in orders:
        symbol = str(order.get("symbol") or "").upper()
        counts[symbol] = counts.get(symbol, 0) + 1
    return OrderCountGateReport(len(orders), max_session_orders, max_orders_per_symbol, counts)


def build_turnover_gate_report(
    fills: Sequence[Mapping[str, Any]],
    account_snapshot: Mapping[str, Any],
    max_daily_turnover_pct: float | None = None,
    max_strategy_turnover: float | None = None,
) -> TurnoverGateReport:
    equity = _optional_float(account_snapshot.get("equity") or account_snapshot.get("portfolio_value")) or 0.0
    daily_turnover = sum(_order_notional(fill) for fill in fills)
    strategy_turnover: dict[str, float] = {}
    for fill in fills:
        strategy = str(fill.get("strategy_name") or fill.get("strategy") or "unknown")
        strategy_turnover[strategy] = strategy_turnover.get(strategy, 0.0) + _order_notional(fill)
    daily_turnover_pct = (daily_turnover / equity) if equity else None
    return TurnoverGateReport(
        daily_turnover=daily_turnover,
        equity=equity,
        daily_turnover_pct=daily_turnover_pct,
        strategy_turnover=strategy_turnover,
        max_daily_turnover_pct=max_daily_turnover_pct,
        max_strategy_turnover=max_strategy_turnover,
    )


def build_realized_slippage_halt_report(
    fills: Sequence[Mapping[str, Any]],
    max_slippage_bps: float = 35.0,
    halt_after_breaches: int = 2,
) -> RealizedSlippageHaltReport:
    statuses = tuple(_realized_slippage_status(fill, max_slippage_bps) for fill in fills)
    return RealizedSlippageHaltReport(statuses, max_slippage_bps=max_slippage_bps, halt_after_breaches=halt_after_breaches)


def build_rejected_order_cooldown_report(
    rejected_orders: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
    max_rejects: int = 2,
    cooldown_minutes: float = 60.0,
) -> RejectedOrderCooldownReport:
    observed_at = now or datetime.now(timezone.utc)
    grouped: dict[tuple[str, str], int] = {}
    for order in rejected_orders:
        if str(order.get("status") or "").upper() != "REJECTED":
            continue
        key = (str(order.get("symbol") or "").upper(), str(order.get("strategy_name") or order.get("strategy") or "unknown"))
        grouped[key] = grouped.get(key, 0) + 1
    cooldowns = tuple(
        _rejected_order_cooldown(symbol, strategy, rejects, observed_at, max_rejects, cooldown_minutes)
        for (symbol, strategy), rejects in sorted(grouped.items())
    )
    return RejectedOrderCooldownReport(cooldowns, max_rejects=max_rejects, cooldown_minutes=cooldown_minutes)


def build_liquidity_participation_report(
    orders: Sequence[Mapping[str, Any]],
    liquidity_by_symbol: Mapping[str, Mapping[str, Any]],
    max_participation_pct: float = 1.0,
    min_average_volume: float = 100_000.0,
    max_spread_bps: float = 25.0,
) -> LiquidityParticipationReport:
    statuses = tuple(
        _liquidity_participation_status(
            order,
            liquidity_by_symbol.get(str(order.get("symbol") or "").upper(), {}),
            max_participation_pct,
            min_average_volume,
            max_spread_bps,
        )
        for order in orders
    )
    return LiquidityParticipationReport(
        statuses,
        max_participation_pct=max_participation_pct,
        min_average_volume=min_average_volume,
        max_spread_bps=max_spread_bps,
    )


def build_broker_rounding_report(
    orders: Sequence[Mapping[str, Any]],
    rules_by_asset_class: Mapping[str, Mapping[str, Any]] | None = None,
) -> BrokerRoundingReport:
    rules = {
        "equity": {"fractional": True, "quantity_precision": 6, "minimum_notional": 1.0},
        "etf": {"fractional": True, "quantity_precision": 6, "minimum_notional": 1.0},
        "stock": {"fractional": True, "quantity_precision": 6, "minimum_notional": 1.0},
        "whole_share": {"fractional": False, "quantity_precision": 0, "minimum_notional": 1.0},
        "crypto": {"fractional": True, "quantity_precision": 8, "minimum_notional": 1.0},
        **dict(rules_by_asset_class or {}),
    }
    return BrokerRoundingReport(tuple(_broker_rounding_decision(order, rules) for order in orders))


def build_stop_exit_visibility_report(
    positions: Sequence[Mapping[str, Any]],
    open_orders: Sequence[Mapping[str, Any]],
    require_stop: bool = True,
    require_exit: bool = True,
) -> StopExitVisibilityReport:
    orders_by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    for order in open_orders:
        orders_by_symbol.setdefault(str(order.get("symbol") or "").upper(), []).append(order)
    statuses = tuple(_stop_exit_visibility_status(position, orders_by_symbol, require_stop, require_exit) for position in positions)
    return StopExitVisibilityReport(statuses, require_stop=require_stop, require_exit=require_exit)


def build_quote_depth_report(
    depth_by_symbol: Mapping[str, Mapping[str, Any]],
    min_depth_notional: float = 10_000.0,
    max_spread_bps: float = 25.0,
) -> QuoteDepthReport:
    statuses = tuple(
        _quote_depth_status(symbol, depth, min_depth_notional, max_spread_bps)
        for symbol, depth in sorted(depth_by_symbol.items())
    )
    return QuoteDepthReport(statuses, min_depth_notional=min_depth_notional, max_spread_bps=max_spread_bps)


def write_execution_template_report(report: ExecutionTemplateReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_bracket_order_plan(report: BracketOrderPlan, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_replace_order_report(report: ReplaceOrderReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_partial_fill_reconciliation_report(report: PartialFillReconciliationReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_client_order_id_replay_report(report: ClientOrderIdReplayReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_pre_submit_order_preview_report(report: PreSubmitOrderPreviewReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_order_count_gate_report(report: OrderCountGateReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_turnover_gate_report(report: TurnoverGateReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_realized_slippage_halt_report(report: RealizedSlippageHaltReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_rejected_order_cooldown_report(report: RejectedOrderCooldownReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_liquidity_participation_report(report: LiquidityParticipationReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_broker_rounding_report(report: BrokerRoundingReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_stop_exit_visibility_report(report: StopExitVisibilityReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_quote_depth_report(report: QuoteDepthReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def _open_order_status(
    payload: Mapping[str, Any],
    expected_keys: set[str],
    observed_at: datetime,
    max_open_order_age_minutes: float,
) -> PaperOpenOrderStatus:
    status = str(payload.get("status") or "PENDING").upper()
    created_at = _created_at(payload)
    age_minutes = _age_minutes(created_at, observed_at)
    unresolved = status in OPEN_ORDER_STATUSES
    stale = bool(unresolved and age_minutes is not None and age_minutes > max_open_order_age_minutes)
    expected_active = bool(_order_keys(payload) & expected_keys)
    reason = "stale_open_order" if stale else "open_order_within_timeout" if unresolved else "closed_order"
    return PaperOpenOrderStatus(
        symbol=str(payload.get("symbol") or "").upper(),
        side=str(payload.get("side") or "").upper(),
        quantity=float(payload.get("quantity") or payload.get("qty") or 0.0),
        status=status,
        order_type=payload.get("order_type") or payload.get("type"),
        time_in_force=payload.get("time_in_force"),
        created_at=created_at.isoformat() if created_at else None,
        age_minutes=age_minutes,
        expected_active=expected_active,
        stale=stale,
        source=str(payload.get("source") or "broker_open_orders"),
        cancel_reference=payload.get("cancel_reference") or payload.get("id") or payload.get("client_order_id") or payload.get("broker_order_id"),
        reason=reason,
    )


def _template_selection(
    intent: Mapping[str, Any],
    family_templates: Mapping[str, str],
    templates: Mapping[str, ExecutionTemplateSpec],
) -> ExecutionTemplateSelection:
    symbol = str(intent.get("symbol") or "").upper()
    family = str(intent.get("strategy_family") or intent.get("family") or "trend").lower()
    requested_template = str(intent.get("execution_template") or family_templates.get(family) or "limit_with_timeout")
    template = templates.get(requested_template)
    if template is None:
        return ExecutionTemplateSelection(symbol, family, requested_template, "UNKNOWN", "unknown", "unknown_execution_template")
    reason = "passed"
    if template.requires_stop_loss and not intent.get("stop_loss_price") and not intent.get("stop_loss_pct"):
        reason = "missing_stop_loss_for_template"
    elif template.requires_take_profit and not intent.get("take_profit_price") and not intent.get("take_profit_pct"):
        reason = "missing_take_profit_for_template"
    elif template.requires_trail and not intent.get("trail_percent"):
        reason = "missing_trailing_stop_for_template"
    return ExecutionTemplateSelection(symbol, family, template.name, template.order_type, template.time_in_force, reason)


def _execution_template_specs(templates: Mapping[str, Mapping[str, Any]]) -> tuple[ExecutionTemplateSpec, ...]:
    return tuple(
        ExecutionTemplateSpec(
            name=name,
            order_type=str(payload.get("order_type") or "MARKET"),
            time_in_force=str(payload.get("time_in_force") or "day"),
            requires_regular_session=bool(payload.get("requires_regular_session", False)),
            requires_stop_loss=bool(payload.get("requires_stop_loss", False)),
            requires_take_profit=bool(payload.get("requires_take_profit", False)),
            requires_trail=bool(payload.get("requires_trail", False)),
            close_only=bool(payload.get("close_only", False)),
            timeout_minutes=_optional_float(payload.get("timeout_minutes")),
        )
        for name, payload in templates.items()
    )


def _replace_order_decision(
    order: Mapping[str, Any],
    quote: Mapping[str, Any],
    observed_at: datetime,
    timeout_minutes: float,
    price_improvement_bps: float,
) -> ReplaceOrderDecision:
    symbol = str(order.get("symbol") or "").upper()
    side = str(order.get("side") or "").upper()
    current_limit = _optional_float(order.get("limit_price"))
    age = _age_minutes(_created_at(order), observed_at)
    if age is None:
        return ReplaceOrderDecision(symbol, side, current_limit, None, age, "keep", "missing_order_age")
    if age <= timeout_minutes:
        return ReplaceOrderDecision(symbol, side, current_limit, None, age, "keep", "keep_order")
    bid = _optional_float(quote.get("bid") or quote.get("bid_price"))
    ask = _optional_float(quote.get("ask") or quote.get("ask_price"))
    if side == "BUY" and ask:
        replacement = ask * (1.0 + price_improvement_bps / 10_000.0)
    elif side == "SELL" and bid:
        replacement = bid * (1.0 - price_improvement_bps / 10_000.0)
    else:
        return ReplaceOrderDecision(symbol, side, current_limit, None, age, "keep", "missing_quote_for_replacement")
    return ReplaceOrderDecision(symbol, side, current_limit, round(replacement, 4), age, "cancel_replace", "replace_planned")


def _partial_fill_reconciliation(
    order: Mapping[str, Any],
    report: Mapping[str, Any] | None,
) -> PartialFillReconciliation:
    symbol = str(order.get("symbol") or "").upper()
    side = str(order.get("side") or "").upper()
    requested = float(order.get("quantity") or order.get("qty") or 0.0)
    filled = _optional_float((report or {}).get("filled_quantity") or (report or {}).get("filled_qty") or order.get("filled_quantity")) or 0.0
    average_fill_price = _optional_float((report or {}).get("average_fill_price") or (report or {}).get("avg_fill_price"))
    remaining = max(0.0, requested - filled)
    if filled <= 0:
        reason = "unfilled_tracked"
    elif filled < requested:
        reason = "partial_fill_tracked"
    elif filled == requested:
        reason = "filled"
    else:
        reason = "overfilled_order"
    return PartialFillReconciliation(symbol, side, requested, filled, remaining, average_fill_price, reason)


def _client_order_id_check(order: Mapping[str, Any], prior: Mapping[str, Any] | None) -> ClientOrderIdReplayCheck:
    client_order_id = str(order.get("client_order_id") or "")
    symbol = str(order.get("symbol") or "").upper()
    side = str(order.get("side") or "").upper()
    quantity = float(order.get("quantity") or order.get("qty") or 0.0)
    if not client_order_id:
        return ClientOrderIdReplayCheck(client_order_id, symbol, side, quantity, None, "block_duplicate_submit", "missing_client_order_id")
    if prior is None:
        return ClientOrderIdReplayCheck(client_order_id, symbol, side, quantity, None, "submit_new", "new_order_allowed")
    prior_status = str(prior.get("status") or "").upper()
    if prior_status in OPEN_ORDER_STATUSES:
        return ClientOrderIdReplayCheck(client_order_id, symbol, side, quantity, prior_status, "reuse_existing_open_order", "retry_existing_open_order")
    return ClientOrderIdReplayCheck(client_order_id, symbol, side, quantity, prior_status, "block_duplicate_submit", "duplicate_blocked")


def _pre_submit_line(order: Mapping[str, Any], price_payload: Any) -> PreSubmitOrderPreviewLine:
    symbol = str(order.get("symbol") or "").upper()
    side = str(order.get("side") or "").upper()
    quantity = float(order.get("quantity") or order.get("qty") or 0.0)
    order_type = str(order.get("order_type") or order.get("type") or "MARKET").upper()
    time_in_force = order.get("time_in_force")
    price, source = _preview_price(order, price_payload)
    reason = "passed"
    if quantity <= 0:
        reason = "invalid_order_quantity"
    elif price is None:
        reason = "missing_price_for_preview"
    return PreSubmitOrderPreviewLine(
        symbol,
        side,
        quantity,
        order_type,
        time_in_force,
        price,
        abs(quantity * price) if price is not None else None,
        source,
        reason,
    )


def _preview_price(order: Mapping[str, Any], price_payload: Any) -> tuple[float | None, str]:
    explicit = _optional_float(order.get("limit_price") or order.get("estimated_price") or order.get("price"))
    if explicit is not None:
        return explicit, "order"
    if isinstance(price_payload, Mapping):
        for key in ("mid_price", "latest_trade_price", "price", "close"):
            price = _optional_float(price_payload.get(key))
            if price is not None:
                return price, key
        bid = _optional_float(price_payload.get("bid") or price_payload.get("bid_price"))
        ask = _optional_float(price_payload.get("ask") or price_payload.get("ask_price"))
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0, "quote_mid"
    price = _optional_float(price_payload)
    return (price, "price_map") if price is not None else (None, "missing")


def _order_match_key(order: Mapping[str, Any]) -> str:
    return str(order.get("client_order_id") or order.get("order_id") or order.get("id") or "|".join(
        [
            str(order.get("symbol") or "").upper(),
            str(order.get("side") or "").upper(),
            str(order.get("quantity") or order.get("qty") or 0.0),
        ]
    ))


def _order_notional(order: Mapping[str, Any]) -> float:
    notional = _optional_float(order.get("notional") or order.get("estimated_notional"))
    if notional is not None:
        return abs(notional)
    quantity = _optional_float(order.get("quantity") or order.get("qty") or order.get("filled_quantity")) or 0.0
    price = _optional_float(order.get("average_fill_price") or order.get("fill_price") or order.get("price")) or 0.0
    return abs(quantity * price)


def _realized_slippage_status(fill: Mapping[str, Any], max_slippage_bps: float) -> RealizedSlippageStatus:
    symbol = str(fill.get("symbol") or "").upper()
    strategy = str(fill.get("strategy_name") or fill.get("strategy") or "unknown")
    side = str(fill.get("side") or "").upper()
    expected_price = _optional_float(fill.get("expected_price") or fill.get("reference_price"))
    fill_price = _optional_float(fill.get("average_fill_price") or fill.get("fill_price"))
    slippage = _signed_slippage_bps(side, fill_price, expected_price)
    reason = "passed"
    if slippage is None:
        reason = "missing_reference_price"
    elif slippage > max_slippage_bps:
        reason = "realized_slippage_above_limit"
    return RealizedSlippageStatus(symbol, strategy, side, expected_price, fill_price, slippage, reason)


def _signed_slippage_bps(side: str, fill_price: float | None, expected_price: float | None) -> float | None:
    if fill_price is None or not expected_price:
        return None
    signed = fill_price - expected_price if side == "BUY" else expected_price - fill_price
    return max(0.0, (signed / expected_price) * 10_000.0)


def _rejected_order_cooldown(
    symbol: str,
    strategy: str,
    rejects: int,
    observed_at: datetime,
    max_rejects: int,
    cooldown_minutes: float,
) -> RejectedOrderCooldown:
    required = rejects >= max_rejects
    until = observed_at.timestamp() + cooldown_minutes * 60.0
    cooldown_until = datetime.fromtimestamp(until, tz=timezone.utc).isoformat() if required else None
    return RejectedOrderCooldown(
        symbol=symbol,
        strategy_name=strategy,
        rejects=rejects,
        cooldown_required=required,
        cooldown_until=cooldown_until,
        reason="reject_cooldown_required" if required else "reject_count_within_limit",
    )


def _liquidity_participation_status(
    order: Mapping[str, Any],
    liquidity: Mapping[str, Any],
    max_participation_pct: float,
    min_average_volume: float,
    max_spread_bps: float,
) -> LiquidityParticipationStatus:
    symbol = str(order.get("symbol") or "").upper()
    quantity = _optional_float(order.get("quantity") or order.get("qty")) or 0.0
    price, _ = _preview_price(order, liquidity)
    estimated_notional = abs(quantity * price) if price is not None else None
    average_volume = _optional_float(liquidity.get("average_volume") or liquidity.get("avg_volume") or liquidity.get("volume"))
    participation_pct = (abs(quantity) / average_volume * 100.0) if average_volume else None
    spread_bps = _spread_bps(liquidity)
    reason = "passed"
    if average_volume is None:
        reason = "missing_average_volume"
    elif average_volume < min_average_volume:
        reason = "average_volume_below_minimum"
    elif participation_pct is not None and participation_pct > max_participation_pct:
        reason = "participation_above_limit"
    elif spread_bps is None:
        reason = "missing_spread"
    elif spread_bps > max_spread_bps:
        reason = "spread_above_limit"
    return LiquidityParticipationStatus(symbol, quantity, estimated_notional, average_volume, participation_pct, spread_bps, reason)


def _spread_bps(payload: Mapping[str, Any]) -> float | None:
    explicit = _optional_float(payload.get("spread_bps"))
    if explicit is not None:
        return explicit
    bid = _optional_float(payload.get("bid") or payload.get("bid_price"))
    ask = _optional_float(payload.get("ask") or payload.get("ask_price"))
    if bid is None or ask is None:
        return None
    mid = (bid + ask) / 2.0
    if not mid:
        return None
    return (ask - bid) / mid * 10_000.0


def _broker_rounding_decision(order: Mapping[str, Any], rules: Mapping[str, Mapping[str, Any]]) -> BrokerRoundingDecision:
    symbol = str(order.get("symbol") or "").upper()
    asset_class = str(order.get("asset_class") or "equity").lower()
    rule = rules.get(asset_class, rules["equity"])
    quantity = _optional_float(order.get("quantity") or order.get("qty")) or 0.0
    precision = int(rule.get("quantity_precision", 6))
    fractional = bool(rule.get("fractional", True))
    price = _optional_float(order.get("estimated_price") or order.get("price") or order.get("limit_price"))
    minimum_notional = float(rule.get("minimum_notional", 1.0))
    rounded = round(quantity, precision) if fractional else float(int(quantity))
    notional = abs(rounded * price) if price is not None else None
    reason = "passed"
    if rounded <= 0:
        reason = "rounded_quantity_zero"
    elif notional is not None and notional < minimum_notional:
        reason = "notional_below_minimum"
    elif rounded != quantity:
        reason = "quantity_rounded"
    return BrokerRoundingDecision(symbol, asset_class, quantity, rounded, notional, minimum_notional, reason)


def _stop_exit_visibility_status(
    position: Mapping[str, Any],
    orders_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    require_stop: bool,
    require_exit: bool,
) -> StopExitVisibilityStatus:
    symbol = str(position.get("symbol") or "").upper()
    quantity = _optional_float(position.get("quantity") or position.get("qty")) or 0.0
    orders = orders_by_symbol.get(symbol, ())
    stop_visible = any(str(order.get("order_type") or order.get("type") or "").upper() in {"STOP", "STOP_LIMIT", "TRAILING_STOP"} for order in orders)
    exit_visible = any(str(order.get("role") or order.get("reason") or "").lower() in {"exit", "take_profit", "stop_loss", "controlled_flatten", "eod_closeout"} for order in orders)
    if not exit_visible:
        exit_visible = any(str(order.get("side") or "").upper() == ("SELL" if quantity > 0 else "BUY") for order in orders)
    reason = "passed"
    if require_stop and not stop_visible:
        reason = "missing_visible_stop_order"
    elif require_exit and not exit_visible:
        reason = "missing_visible_exit_order"
    return StopExitVisibilityStatus(symbol, quantity, stop_visible, exit_visible, reason)


def _quote_depth_status(
    symbol: str,
    depth: Mapping[str, Any],
    min_depth_notional: float,
    max_spread_bps: float,
) -> QuoteDepthStatus:
    bid_depth = _depth_notional(depth.get("bids") or depth.get("bid_levels") or ())
    ask_depth = _depth_notional(depth.get("asks") or depth.get("ask_levels") or ())
    spread_bps = _spread_bps(depth)
    reason = "passed"
    if bid_depth < min_depth_notional or ask_depth < min_depth_notional:
        reason = "depth_notional_below_minimum"
    elif spread_bps is None:
        reason = "missing_depth_spread"
    elif spread_bps > max_spread_bps:
        reason = "depth_spread_above_limit"
    return QuoteDepthStatus(str(symbol).upper(), bid_depth, ask_depth, spread_bps, reason)


def _depth_notional(levels: Any) -> float:
    if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
        return 0.0
    total = 0.0
    for level in levels:
        if isinstance(level, Mapping):
            price = _optional_float(level.get("price") or level.get("p"))
            size = _optional_float(level.get("size") or level.get("quantity") or level.get("q"))
        elif isinstance(level, Sequence) and len(level) >= 2:
            price = _optional_float(level[0])
            size = _optional_float(level[1])
        else:
            continue
        if price is not None and size is not None:
            total += abs(price * size)
    return total


def _write_report(payload: dict, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _open_order_payloads(
    portfolio_report: Mapping[str, Any],
    open_order_snapshot: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], ...]:
    payloads: list[Mapping[str, Any]] = []
    if open_order_snapshot:
        for key in ("open_orders", "open_orders_seen", "open_orders_after", "orders"):
            payloads.extend(_orders_from(open_order_snapshot.get(key), source="broker_open_orders"))
    submission = portfolio_report.get("submission") or {}
    payloads.extend(_orders_from(submission.get("submitted_orders"), source="portfolio_submission"))

    deduped: dict[tuple[str, str, float, str, str | None], Mapping[str, Any]] = {}
    for payload in payloads:
        status = str(payload.get("status") or "").upper()
        if status in CLOSED_ORDER_STATUSES:
            continue
        symbol = str(payload.get("symbol") or "").upper()
        side = str(payload.get("side") or "").upper()
        quantity = float(payload.get("quantity") or payload.get("qty") or 0.0)
        key = (symbol, side, quantity, status, payload.get("client_order_id") or payload.get("id"))
        deduped[key] = payload
    return tuple(deduped.values())


def _orders_from(value: Any, source: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    orders = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        payload = dict(item)
        payload.setdefault("source", source)
        orders.append(payload)
    return orders


def _expected_submitted_order_keys(portfolio_report: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for order in (portfolio_report.get("submission") or {}).get("submitted_orders") or ():
        if isinstance(order, Mapping):
            keys.update(_order_keys(order))
    return keys


def _order_keys(order: Mapping[str, Any]) -> set[str]:
    keys = {
        str(order.get("id") or ""),
        str(order.get("client_order_id") or ""),
        "|".join(
            [
                str(order.get("symbol") or "").upper(),
                str(order.get("side") or "").upper(),
                str(order.get("quantity") or order.get("qty") or 0.0),
            ]
        ),
    }
    return {key for key in keys if key}


def _created_at(payload: Mapping[str, Any]) -> datetime | None:
    value = payload.get("created_at") or payload.get("submitted_at")
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_minutes(created_at: datetime | None, observed_at: datetime) -> float | None:
    if created_at is None:
        return None
    return (observed_at - created_at).total_seconds() / 60.0


def _order_payload(order: Any) -> dict:
    return {
        "id": getattr(order, "id", None),
        "client_order_id": getattr(order, "client_order_id", None),
        "symbol": getattr(order, "symbol", ""),
        "side": getattr(order, "side", ""),
        "quantity": getattr(order, "quantity", 0.0),
        "order_type": getattr(order, "order_type", None),
        "limit_price": getattr(order, "limit_price", None),
        "stop_price": getattr(order, "stop_price", None),
        "time_in_force": getattr(order, "time_in_force", None),
        "status": getattr(order, "status", "PENDING"),
        "created_at": getattr(order, "created_at", None).isoformat() if getattr(order, "created_at", None) else None,
        "source": "broker_open_orders",
    }


def _execute_cancel(order: PaperOpenOrderStatus, broker: Any) -> PaperStaleOrderCancelAttempt:
    if not order.cancel_reference:
        return _cancel_attempt_from_status(
            order,
            cancel_requested=True,
            attempted=False,
            acknowledged=False,
            reason="missing_cancel_reference",
        )
    cancelled = broker.cancel_order(order.cancel_reference)
    acknowledged = bool(cancelled and str(getattr(cancelled, "status", "")).upper() in {"CANCELLED", "CANCELED"})
    return _cancel_attempt_from_status(
        order,
        cancel_requested=True,
        attempted=True,
        acknowledged=acknowledged,
        reason="cancel_acknowledged" if acknowledged else "cancel_not_acknowledged",
    )


def _cancel_attempt_from_status(
    order: PaperOpenOrderStatus,
    cancel_requested: bool,
    attempted: bool,
    acknowledged: bool,
    reason: str,
) -> PaperStaleOrderCancelAttempt:
    return PaperStaleOrderCancelAttempt(
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        order_status=order.status,
        age_minutes=order.age_minutes,
        cancel_requested=cancel_requested,
        attempted=attempted,
        acknowledged=acknowledged,
        cancel_reference_available=bool(order.cancel_reference),
        reason=reason,
    )
