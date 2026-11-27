import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.app import TradingApplication
from src.execution import BrokerPositionSnapshot, BrokerReconciler, ExecutionReport
from src.models import Order

from .paper_session import (
    AutonomousPaperSessionOptions,
    PaperSessionSubmissionGuardReport,
    evaluate_paper_session_submission_guard,
)
from .portfolio_session import _redact_broker_payload


@dataclass(frozen=True)
class PaperCleanupOptions:
    submit_orders: bool = False
    artifact_path: str = "reports/paper-cleanup-report.json"
    symbols: Sequence[str] = ()
    approval_options: AutonomousPaperSessionOptions = field(default_factory=AutonomousPaperSessionOptions)
    fill_poll_attempts: int = 1
    fill_poll_interval_seconds: float = 0.0
    submission_guard_evaluator: Callable[
        [TradingApplication, AutonomousPaperSessionOptions, Sequence[Order]],
        PaperSessionSubmissionGuardReport,
    ] = evaluate_paper_session_submission_guard


@dataclass(frozen=True)
class PaperCleanupReport:
    submit_requested: bool
    attempted: bool
    positions_seen: tuple[Mapping[str, Any], ...]
    planned_orders: tuple[Mapping[str, Any], ...]
    submitted_orders: tuple[Mapping[str, Any], ...] = ()
    execution_reports: tuple[Mapping[str, Any], ...] = ()
    submission_guard: PaperSessionSubmissionGuardReport | None = None
    reconciliation: Mapping[str, Any] | None = None
    fill_poll_attempts: int = 0
    polled_execution_reports: int = 0
    reason: str = "preview_only"
    artifact_path: str | None = None

    @property
    def submitted(self) -> bool:
        return bool(self.submitted_orders)

    @property
    def reconciliation_clean(self) -> bool | None:
        if self.reconciliation is None:
            return None
        return bool(self.reconciliation.get("is_clean"))

    def to_dict(self) -> dict:
        return {
            "submit_requested": self.submit_requested,
            "attempted": self.attempted,
            "submitted": self.submitted,
            "positions_seen": [dict(position) for position in self.positions_seen],
            "planned_orders": [dict(order) for order in self.planned_orders],
            "submitted_orders": [dict(order) for order in self.submitted_orders],
            "execution_reports": [dict(report) for report in self.execution_reports],
            "submission_guard": self.submission_guard.to_dict() if self.submission_guard else None,
            "reconciliation": dict(self.reconciliation) if self.reconciliation else None,
            "reconciliation_clean": self.reconciliation_clean,
            "fill_poll_attempts": self.fill_poll_attempts,
            "polled_execution_reports": self.polled_execution_reports,
            "reason": self.reason,
            "artifact_path": self.artifact_path,
        }


def run_paper_cleanup(
    app: TradingApplication,
    options: PaperCleanupOptions | None = None,
    broker_factory: Callable[[], Any] | None = None,
) -> PaperCleanupReport:
    options = options or PaperCleanupOptions()
    broker = (broker_factory or app.create_broker)()
    positions = tuple(_filtered_positions(broker.positions(), options.symbols))
    planned_orders = tuple(_flatten_order(position) for position in positions if abs(position.quantity) > 0)
    submission_guard = None
    submitted_orders: tuple[Order, ...] = ()
    execution_reports: tuple[ExecutionReport, ...] = ()
    reconciliation = None
    fill_poll_attempts = 0
    polled_execution_reports = 0
    reason = "preview_only"
    attempted = False

    if options.submit_orders:
        guard_options = _cleanup_guard_options(options)
        submission_guard = options.submission_guard_evaluator(app, guard_options, planned_orders)
        if not planned_orders:
            reason = "no_positions_to_flatten"
        elif not submission_guard.passed:
            reason = submission_guard.reason
        else:
            attempted = True
            submitted_orders = tuple(broker.submit_order(order) for order in planned_orders)
            execution_reports = tuple(broker.execution_reports())
            fill_poll_attempts, polled_execution_reports, execution_reports = _poll_cleanup_reports(
                broker,
                submitted_orders,
                execution_reports,
                options,
            )
            if polled_execution_reports:
                submitted_orders = _latest_broker_orders(broker, submitted_orders)
            reconciliation = _reconciliation_payload(BrokerReconciler().reconcile_orders(submitted_orders, execution_reports))
            reason = "flatten_orders_submitted" if submitted_orders else "broker_returned_no_orders"

    report = PaperCleanupReport(
        submit_requested=options.submit_orders,
        attempted=attempted,
        positions_seen=tuple(_position_payload(position) for position in positions),
        planned_orders=tuple(_order_payload(order) for order in planned_orders),
        submitted_orders=tuple(_order_payload(order) for order in submitted_orders),
        execution_reports=tuple(_execution_report_payload(report) for report in execution_reports),
        submission_guard=submission_guard,
        reconciliation=reconciliation,
        fill_poll_attempts=fill_poll_attempts,
        polled_execution_reports=polled_execution_reports,
        reason=reason,
    )
    artifact_path = _write_cleanup_report(report, options)
    return PaperCleanupReport(
        submit_requested=report.submit_requested,
        attempted=report.attempted,
        positions_seen=report.positions_seen,
        planned_orders=report.planned_orders,
        submitted_orders=report.submitted_orders,
        execution_reports=report.execution_reports,
        submission_guard=report.submission_guard,
        reconciliation=report.reconciliation,
        fill_poll_attempts=report.fill_poll_attempts,
        polled_execution_reports=report.polled_execution_reports,
        reason=report.reason,
        artifact_path=artifact_path,
    )


def _filtered_positions(
    positions: Sequence[BrokerPositionSnapshot],
    symbols: Sequence[str],
) -> list[BrokerPositionSnapshot]:
    allowlist = {symbol.upper() for symbol in symbols if symbol}
    return [
        position
        for position in positions
        if position.symbol and (not allowlist or position.symbol.upper() in allowlist)
    ]


def _flatten_order(position: BrokerPositionSnapshot) -> Order:
    side = "SELL" if position.quantity > 0 else "BUY"
    return Order(position.symbol.upper(), side, abs(position.quantity), order_type="MARKET")


def _cleanup_guard_options(options: PaperCleanupOptions) -> AutonomousPaperSessionOptions:
    return AutonomousPaperSessionOptions(
        submit_orders=True,
        submission_approval_policy=options.approval_options.submission_approval_policy,
        prior_broker_proof_reports=options.approval_options.prior_broker_proof_reports,
    )


def _poll_cleanup_reports(
    broker,
    submitted_orders: Sequence[Order],
    fallback_reports: Sequence[ExecutionReport],
    options: PaperCleanupOptions,
) -> tuple[int, int, tuple[ExecutionReport, ...]]:
    poll = getattr(broker, "poll_execution_reports", None)
    attempts = max(int(options.fill_poll_attempts), 0)
    if poll is None or attempts <= 0 or not submitted_orders:
        return 0, 0, tuple(fallback_reports)
    reports: tuple[ExecutionReport, ...] = tuple(fallback_reports)
    for attempt in range(1, attempts + 1):
        polled = tuple(poll(submitted_orders))
        if polled:
            return attempt, len(polled), polled
        if options.fill_poll_interval_seconds > 0 and attempt < attempts:
            time.sleep(options.fill_poll_interval_seconds)
    return attempts, 0, reports


def _latest_broker_orders(broker: Any, orders: Sequence[Order]) -> tuple[Order, ...]:
    broker_orders = getattr(broker, "orders", None)
    if not isinstance(broker_orders, Mapping):
        return tuple(orders)
    return tuple(broker_orders.get(order.id, order) for order in orders)


def _position_payload(position: BrokerPositionSnapshot) -> dict:
    return {
        "symbol": position.symbol,
        "quantity": position.quantity,
        "average_entry_price": position.average_entry_price,
        "market_value": position.market_value,
        "raw": _redact_broker_payload(position.raw),
    }


def _order_payload(order: Order) -> dict:
    return {
        "id": order.id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "order_type": order.order_type,
        "limit_price": order.limit_price,
        "stop_price": order.stop_price,
        "take_profit_price": order.take_profit_price,
        "trail_percent": order.trail_percent,
        "time_in_force": order.time_in_force,
        "parent_order_id": order.parent_order_id,
        "order_group_id": order.order_group_id,
        "status": order.status,
        "created_at": order.created_at.isoformat(),
    }


def _execution_report_payload(report: ExecutionReport) -> dict:
    return {
        "order_id": report.order_id,
        "status": report.status,
        "broker_order_id": report.broker_order_id,
        "fill_id": report.fill_id,
        "filled_quantity": report.filled_quantity,
        "average_fill_price": report.average_fill_price,
        "submitted_at": report.submitted_at.isoformat(),
        "raw": _redact_broker_payload(report.raw),
    }


def _reconciliation_payload(reconciliation) -> dict:
    return {
        "is_clean": reconciliation.is_clean,
        "unresolved": len(reconciliation.unresolved),
        "orders": [
            {
                "order_id": item.order_id,
                "status": item.status.value,
                "local_status": item.local_status,
                "broker_status": item.broker_status,
                "broker_order_id": item.broker_order_id,
                "message": item.message,
            }
            for item in reconciliation.orders
        ],
    }


def _write_cleanup_report(report: PaperCleanupReport, options: PaperCleanupOptions) -> str:
    path = Path(options.artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(path)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(path)
