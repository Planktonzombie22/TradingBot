import json
from dataclasses import dataclass
from pathlib import Path

from .paper_lifecycle import PaperPositionLifecycle, PaperPositionLifecycleReport


@dataclass(frozen=True)
class PaperExitPreviewOrder:
    symbol: str
    side: str
    quantity: float
    order_type: str = "MARKET"
    strategy_name: str = "unknown"
    owner_type: str = "unknown"
    estimated_notional: float | None = None
    expected_realized_pnl: float | None = None
    position_status: str = "active"
    reason: str = "operator_requested_active_flatten_preview"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "strategy_name": self.strategy_name,
            "owner_type": self.owner_type,
            "estimated_notional": self.estimated_notional,
            "expected_realized_pnl": self.expected_realized_pnl,
            "position_status": self.position_status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperExitPreviewReport:
    orders: tuple[PaperExitPreviewOrder, ...]
    include_active_positions: bool = False
    cleanup_debt_symbols: tuple[str, ...] = ()
    artifact_path: str | None = None

    @property
    def requires_operator_action(self) -> bool:
        return bool(self.cleanup_debt_symbols)

    @property
    def reason(self) -> str:
        if self.orders:
            return "exit_preview_created"
        return "no_exit_orders_needed"

    @property
    def passed(self) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "requires_operator_action": self.requires_operator_action,
            "include_active_positions": self.include_active_positions,
            "cleanup_debt_symbols": list(self.cleanup_debt_symbols),
            "orders": [order.to_dict() for order in self.orders],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PaperControlledFlattenPlan:
    orders: tuple[PaperExitPreviewOrder, ...]
    requested_symbols: tuple[str, ...] = ()
    blocked_symbols: tuple[str, ...] = ()
    exit_reason: str = "operator_requested_controlled_flatten"
    monitor_confirmation_required: bool = True
    submit_requested: bool = False
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return not self.blocked_symbols

    @property
    def reason(self) -> str:
        if self.blocked_symbols:
            return "requested_symbols_not_active_pilot_positions"
        if self.orders:
            return "controlled_flatten_plan_created"
        return "no_active_pilot_positions_selected"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "exit_reason": self.exit_reason,
            "submit_requested": self.submit_requested,
            "monitor_confirmation_required": self.monitor_confirmation_required,
            "requested_symbols": list(self.requested_symbols),
            "blocked_symbols": list(self.blocked_symbols),
            "orders": [order.to_dict() for order in self.orders],
            "artifact_path": self.artifact_path,
        }


def build_paper_exit_preview(
    lifecycle_report: PaperPositionLifecycleReport,
    include_active_positions: bool = False,
) -> PaperExitPreviewReport:
    orders = tuple(
        _exit_order(position)
        for position in lifecycle_report.positions
        if _should_preview_exit(position, include_active_positions)
    )
    return PaperExitPreviewReport(
        orders=orders,
        include_active_positions=include_active_positions,
        cleanup_debt_symbols=lifecycle_report.exposure_registry.cleanup_debt_symbols,
    )


def build_paper_controlled_flatten_plan(
    lifecycle_report: PaperPositionLifecycleReport,
    symbols: tuple[str, ...] = (),
    exit_reason: str = "operator_requested_controlled_flatten",
    submit_requested: bool = False,
) -> PaperControlledFlattenPlan:
    requested = tuple(symbol.upper() for symbol in symbols if symbol)
    active_positions = tuple(position for position in lifecycle_report.positions if _is_active_pilot_position(position))
    selected = tuple(
        position
        for position in active_positions
        if not requested or position.symbol.upper() in set(requested)
    )
    selected_symbols = {position.symbol.upper() for position in selected}
    blocked = tuple(symbol for symbol in requested if symbol not in selected_symbols)
    return PaperControlledFlattenPlan(
        orders=tuple(_exit_order(position, reason_override=exit_reason) for position in selected if abs(position.observed_quantity) > 1e-12),
        requested_symbols=requested,
        blocked_symbols=blocked,
        exit_reason=exit_reason,
        submit_requested=submit_requested,
    )


def write_paper_exit_preview_report(report: PaperExitPreviewReport, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def write_paper_controlled_flatten_plan(report: PaperControlledFlattenPlan, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def _should_preview_exit(position: PaperPositionLifecycle, include_active_positions: bool) -> bool:
    if abs(position.observed_quantity) <= 1e-12:
        return False
    return position.forced_exit_needed or include_active_positions


def _exit_order(position: PaperPositionLifecycle, reason_override: str | None = None) -> PaperExitPreviewOrder:
    side = "SELL" if position.observed_quantity > 0 else "BUY"
    forced_reason = f"{position.status}_position_cleanup_debt"
    reason = reason_override or (forced_reason if position.forced_exit_needed else "operator_requested_active_flatten_preview")
    return PaperExitPreviewOrder(
        symbol=position.symbol,
        side=side,
        quantity=abs(position.observed_quantity),
        strategy_name=position.strategy_name,
        owner_type=position.owner_type,
        estimated_notional=_estimated_notional(position),
        expected_realized_pnl=position.unrealized_pnl,
        position_status=position.status,
        reason=reason,
    )


def _estimated_notional(position: PaperPositionLifecycle) -> float | None:
    if position.market_value is not None:
        return abs(position.market_value)
    if position.average_fill_price is not None:
        return abs(position.observed_quantity) * position.average_fill_price
    return None


def _is_active_pilot_position(position: PaperPositionLifecycle) -> bool:
    return position.status in {"fresh", "active"} and position.owner_type == "promoted_strategy" and abs(position.observed_quantity) > 1e-12
