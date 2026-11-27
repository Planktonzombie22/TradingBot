import json
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.app import TradingApplication
from src.backtesting import PaperSessionManifest
from src.config import StrategyConfig
from src.execution import BrokerReconciler, ExecutionReport
from src.models import Order
from src.portfolio import CapitalLedgerPolicy, CapitalRequest, allocate_capital_requests

from .paper_session import (
    AutonomousPaperSessionOptions,
    AutonomousPaperSessionResult,
    PaperSessionRiskBudget,
    PaperSessionSubmissionGuardReport,
    evaluate_paper_session_submission_guard,
    run_autonomous_paper_session,
)


@dataclass(frozen=True)
class PortfolioPaperSessionOptions:
    symbols: Sequence[str] = ()
    manifests: Sequence[PaperSessionManifest] = ()
    max_symbols: int = 10
    artifact_root: str = "runs/portfolio-paper-session"
    session_template: AutonomousPaperSessionOptions | None = None
    requested_weight: float = 0.10
    strategy_edge: float = 0.01
    benchmark_edge: float = 0.0
    submit_orders: bool = False
    comparison_provider: str | None = None
    recover_state: bool = False
    state_db_path: str | None = None
    risk_budget: PaperSessionRiskBudget | None = None
    max_portfolio_notional: float | None = None
    capital_policy: CapitalLedgerPolicy = field(default_factory=CapitalLedgerPolicy)
    submission_guard_evaluator: Callable[
        [TradingApplication, AutonomousPaperSessionOptions, Sequence[Order]],
        PaperSessionSubmissionGuardReport,
    ] = evaluate_paper_session_submission_guard


@dataclass(frozen=True)
class PortfolioCandidateResult:
    symbol: str
    strategy: str
    params: Mapping[str, Any]
    ready: bool
    orders_planned: int
    requested_weight: float
    warnings: tuple[str, ...]
    report_path: str | None
    session: AutonomousPaperSessionResult

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "params": dict(self.params),
            "ready": self.ready,
            "orders_planned": self.orders_planned,
            "requested_weight": self.requested_weight,
            "warnings": list(self.warnings),
            "report_path": self.report_path,
            "session": self.session.to_dict(),
        }


@dataclass(frozen=True)
class PortfolioNotionalBudgetReport:
    estimated_notional: float
    max_notional: float | None = None
    unknown_orders: int = 0

    @property
    def passed(self) -> bool:
        if self.unknown_orders:
            return self.max_notional is None
        return self.max_notional is None or self.estimated_notional <= self.max_notional

    @property
    def reason(self) -> str:
        if self.unknown_orders and self.max_notional is not None:
            return "portfolio_notional_unknown"
        if not self.passed:
            return "portfolio_notional_exceeds_budget"
        return "portfolio_notional_budget_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "estimated_notional": self.estimated_notional,
            "max_notional": self.max_notional,
            "unknown_orders": self.unknown_orders,
        }


@dataclass(frozen=True)
class PortfolioSubmissionReport:
    submit_requested: bool = False
    attempted: bool = False
    submitted_orders: tuple[Mapping[str, Any], ...] = ()
    execution_reports: tuple[Mapping[str, Any], ...] = ()
    reconciliation: Mapping[str, Any] | None = None
    submission_guard: PaperSessionSubmissionGuardReport | None = None
    notional_budget: PortfolioNotionalBudgetReport | None = None
    fill_poll_attempts: int = 0
    polled_execution_reports: int = 0
    reason: str = "submit_not_requested"

    @property
    def submitted(self) -> bool:
        return bool(self.submitted_orders)

    @property
    def orders_submitted(self) -> int:
        return len(self.submitted_orders)

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
            "orders_submitted": self.orders_submitted,
            "reason": self.reason,
            "reconciliation_clean": self.reconciliation_clean,
            "submission_guard": self.submission_guard.to_dict() if self.submission_guard else None,
            "notional_budget": self.notional_budget.to_dict() if self.notional_budget else None,
            "fill_poll_attempts": self.fill_poll_attempts,
            "polled_execution_reports": self.polled_execution_reports,
            "submitted_orders": [dict(order) for order in self.submitted_orders],
            "execution_reports": [dict(report) for report in self.execution_reports],
            "reconciliation": dict(self.reconciliation) if self.reconciliation else None,
        }


@dataclass(frozen=True)
class PortfolioPaperSessionReport:
    symbols: tuple[str, ...]
    candidates: tuple[PortfolioCandidateResult, ...]
    capital_report: Any
    consolidated_orders: tuple[Mapping[str, Any], ...]
    submission: PortfolioSubmissionReport = field(default_factory=PortfolioSubmissionReport)
    artifact_path: str | None = None

    @property
    def ready_for_submission(self) -> bool:
        return bool(self.consolidated_orders) and all(not candidate.warnings for candidate in self.candidates if candidate.ready)

    @property
    def accepted_symbols(self) -> tuple[str, ...]:
        return tuple(
            allocation.request.symbol
            for allocation in self.capital_report.allocations
            if allocation.accepted
        )

    def to_dict(self) -> dict:
        return {
            "symbols": list(self.symbols),
            "ready_for_submission": self.ready_for_submission,
            "accepted_symbols": list(self.accepted_symbols),
            "candidate_count": len(self.candidates),
            "consolidated_order_count": len(self.consolidated_orders),
            "submission": self.submission.to_dict(),
            "capital_report": self.capital_report.to_dict(),
            "consolidated_orders": [dict(order) for order in self.consolidated_orders],
            "artifact_path": self.artifact_path,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def run_portfolio_paper_session(
    app: TradingApplication,
    options: PortfolioPaperSessionOptions | None = None,
) -> PortfolioPaperSessionReport:
    options = options or PortfolioPaperSessionOptions()
    symbols = tuple(_portfolio_symbols(app, options))
    candidates = tuple(_candidate_session(app, symbol, options) for symbol in symbols)
    capital_report = allocate_capital_requests(_capital_requests(candidates, options), options.capital_policy)
    consolidated_orders = tuple(
        _scale_orders_to_portfolio_notional(
            _consolidated_orders(candidates, capital_report, options),
            _portfolio_notional_limit(options),
        )
    )
    submission = _submit_consolidated_orders(app, consolidated_orders, options)
    report = PortfolioPaperSessionReport(
        symbols=symbols,
        candidates=candidates,
        capital_report=capital_report,
        consolidated_orders=consolidated_orders,
        submission=submission,
    )
    artifact_path = _write_portfolio_report(report, options)
    return PortfolioPaperSessionReport(
        symbols=report.symbols,
        candidates=report.candidates,
        capital_report=report.capital_report,
        consolidated_orders=report.consolidated_orders,
        submission=report.submission,
        artifact_path=artifact_path,
    )


def _portfolio_symbols(app: TradingApplication, options: PortfolioPaperSessionOptions) -> list[str]:
    raw = [manifest.symbol for manifest in options.manifests] if options.manifests else list(options.symbols)
    if not raw:
        raw = app.load_universe()
    if not raw:
        raw = [app.config.data.symbol]
    symbols = []
    seen = set()
    for item in raw:
        symbol = str(item).strip().upper()
        if not symbol or symbol in seen:
            continue
        symbols.append(symbol)
        seen.add(symbol)
        if len(symbols) >= options.max_symbols:
            break
    return symbols


def _candidate_session(
    app: TradingApplication,
    symbol: str,
    options: PortfolioPaperSessionOptions,
) -> PortfolioCandidateResult:
    manifest = _manifest_for_symbol(symbol, options.manifests)
    strategy = manifest.strategy_name if manifest else app.config.strategy.name
    params = dict(manifest.params) if manifest else dict(app.config.strategy.params)
    symbol_app = TradingApplication(
        replace(
            app.config,
            data=replace(app.config.data, symbol=symbol),
            strategy=StrategyConfig(name=strategy, params=params),
        )
    )
    session = run_autonomous_paper_session(
        symbol_app,
        _candidate_session_options(symbol, options),
    )
    return PortfolioCandidateResult(
        symbol=symbol,
        strategy=strategy,
        params=params,
        ready=session.ready_for_submission,
        orders_planned=session.orders_planned,
        requested_weight=options.requested_weight,
        warnings=session.warnings,
        report_path=session.report_path,
        session=session,
    )


def _candidate_session_options(
    symbol: str,
    options: PortfolioPaperSessionOptions,
) -> AutonomousPaperSessionOptions:
    artifact_root = str(Path(options.artifact_root) / "symbols" / symbol)
    if options.session_template is not None:
        return replace(
            options.session_template,
            submit_orders=False,
            sync_broker_state=options.session_template.submit_orders or options.session_template.sync_broker_state,
            artifact_root=artifact_root,
            max_position_weight=min(options.session_template.max_position_weight, options.requested_weight),
        )
    return AutonomousPaperSessionOptions(
        submit_orders=False,
        artifact_root=artifact_root,
        strategy_edge=options.strategy_edge,
        benchmark_edge=options.benchmark_edge,
        max_position_weight=options.requested_weight,
        comparison_provider=options.comparison_provider,
        recover_state=options.recover_state,
        state_db_path=options.state_db_path,
        risk_budget=options.risk_budget,
    )


def _capital_requests(
    candidates: Sequence[PortfolioCandidateResult],
    options: PortfolioPaperSessionOptions,
) -> list[CapitalRequest]:
    requests = []
    for index, candidate in enumerate(candidates):
        action = "trade_strategy" if candidate.ready and candidate.orders_planned else "cash"
        requests.append(
            CapitalRequest(
                strategy_name=candidate.strategy,
                symbol=candidate.symbol,
                action=action,
                requested_weight=options.requested_weight,
                family="portfolio_paper_session",
                edge_score=options.strategy_edge,
                priority=len(candidates) - index,
                metadata={
                    "params": dict(candidate.params),
                    "report_path": candidate.report_path,
                    "warnings": list(candidate.warnings),
                },
            )
        )
    return requests


def _consolidated_orders(
    candidates: Sequence[PortfolioCandidateResult],
    capital_report,
    options: PortfolioPaperSessionOptions,
) -> list[dict]:
    candidates_by_symbol = {candidate.symbol: candidate for candidate in candidates}
    orders = []
    for allocation in capital_report.allocations:
        if not allocation.accepted:
            continue
        candidate = candidates_by_symbol.get(allocation.request.symbol)
        if candidate is None:
            continue
        scale = allocation.allocated_weight / options.requested_weight if options.requested_weight else 0.0
        for order in candidate.session.planned_orders:
            payload = dict(order)
            payload["quantity"] = round(float(payload["quantity"]) * scale, 8)
            payload["allocated_weight"] = allocation.allocated_weight
            payload["strategy_name"] = candidate.strategy
            payload["source_report_path"] = candidate.report_path
            payload["portfolio_action"] = allocation.request.action
            latest_price = candidate.session.latest_prices.get(candidate.symbol)
            payload["latest_price"] = latest_price
            payload["estimated_notional"] = abs(float(payload["quantity"])) * latest_price if latest_price is not None else None
            orders.append(payload)
    return orders


def _scale_orders_to_portfolio_notional(
    orders: Sequence[Mapping[str, Any]],
    max_notional: float | None,
) -> list[dict]:
    scaled_orders = [dict(order) for order in orders]
    if max_notional is None:
        return scaled_orders
    known_notional = [order.get("estimated_notional") for order in scaled_orders]
    if any(value is None for value in known_notional):
        return scaled_orders
    total_notional = sum(abs(float(value)) for value in known_notional)
    if total_notional <= 0 or total_notional <= max_notional:
        return scaled_orders
    scale = max_notional / total_notional
    for order in scaled_orders:
        original_quantity = float(order["quantity"])
        original_notional = float(order["estimated_notional"])
        order["original_quantity"] = original_quantity
        order["original_estimated_notional"] = original_notional
        order["portfolio_notional_scale"] = scale
        order["quantity"] = round(original_quantity * scale, 8)
        order["estimated_notional"] = abs(float(order["quantity"])) * float(order["latest_price"])
    return scaled_orders


def _submit_consolidated_orders(
    app: TradingApplication,
    consolidated_orders: Sequence[Mapping[str, Any]],
    options: PortfolioPaperSessionOptions,
) -> PortfolioSubmissionReport:
    notional_budget = _portfolio_notional_budget(consolidated_orders, _portfolio_notional_limit(options))
    submit_requested = _portfolio_submit_requested(options)
    if not submit_requested:
        return PortfolioSubmissionReport(submit_requested=False, notional_budget=notional_budget)
    if not consolidated_orders:
        return PortfolioSubmissionReport(submit_requested=True, notional_budget=notional_budget, reason="no_consolidated_orders")
    if not notional_budget.passed:
        return PortfolioSubmissionReport(
            submit_requested=True,
            notional_budget=notional_budget,
            reason=notional_budget.reason,
        )

    local_orders = tuple(_order_from_payload(order) for order in consolidated_orders)
    guard_options = _portfolio_guard_options(options)
    submission_guard = options.submission_guard_evaluator(app, guard_options, local_orders)
    if not submission_guard.passed:
        return PortfolioSubmissionReport(
            submit_requested=True,
            submission_guard=submission_guard,
            notional_budget=notional_budget,
            reason=submission_guard.reason,
        )

    broker = app.create_broker()
    submitted = tuple(broker.submit_order(order) for order in local_orders)
    execution_reports = tuple(broker.execution_reports())
    fill_poll_attempts, polled_execution_reports, execution_reports = _poll_portfolio_execution_reports(
        broker,
        submitted,
        execution_reports,
        options,
    )
    if polled_execution_reports:
        submitted = _latest_broker_orders(broker, submitted)
    reconciliation = BrokerReconciler().reconcile_orders(submitted, execution_reports)
    return PortfolioSubmissionReport(
        submit_requested=True,
        attempted=True,
        submitted_orders=tuple(_order_payload(order) for order in submitted),
        execution_reports=tuple(_execution_report_payload(report) for report in execution_reports),
        reconciliation=_reconciliation_payload(reconciliation),
        submission_guard=submission_guard,
        notional_budget=notional_budget,
        fill_poll_attempts=fill_poll_attempts,
        polled_execution_reports=polled_execution_reports,
        reason="submitted_consolidated_orders" if submitted else "broker_returned_no_orders",
    )


def _portfolio_submit_requested(options: PortfolioPaperSessionOptions) -> bool:
    return bool(options.session_template.submit_orders) if options.session_template is not None else bool(options.submit_orders)


def _poll_portfolio_execution_reports(
    broker,
    submitted_orders: Sequence[Order],
    fallback_reports: Sequence[ExecutionReport],
    options: PortfolioPaperSessionOptions,
) -> tuple[int, int, tuple[ExecutionReport, ...]]:
    poll = getattr(broker, "poll_execution_reports", None)
    template = options.session_template
    attempts = max(int(template.fill_poll_attempts), 0) if template is not None else 0
    if poll is None or attempts <= 0 or not submitted_orders:
        return 0, 0, tuple(fallback_reports)
    reports: tuple[ExecutionReport, ...] = tuple(fallback_reports)
    for attempt in range(1, attempts + 1):
        polled = tuple(poll(submitted_orders))
        if polled:
            reports = polled
            return attempt, len(polled), reports
        interval = float(template.fill_poll_interval_seconds) if template is not None else 0.0
        if interval > 0 and attempt < attempts:
            time.sleep(interval)
    return attempts, 0, reports


def _latest_broker_orders(broker: Any, orders: Sequence[Order]) -> tuple[Order, ...]:
    broker_orders = getattr(broker, "orders", None)
    if not isinstance(broker_orders, Mapping):
        return tuple(orders)
    return tuple(broker_orders.get(order.id, order) for order in orders)


def _portfolio_guard_options(options: PortfolioPaperSessionOptions) -> AutonomousPaperSessionOptions:
    if options.session_template is not None:
        return replace(options.session_template, submit_orders=True)
    return AutonomousPaperSessionOptions(submit_orders=True)


def _portfolio_notional_limit(options: PortfolioPaperSessionOptions) -> float | None:
    if options.max_portfolio_notional is not None:
        return options.max_portfolio_notional
    if options.session_template and options.session_template.risk_budget:
        return options.session_template.risk_budget.max_session_notional
    return None


def _portfolio_notional_budget(
    consolidated_orders: Sequence[Mapping[str, Any]],
    max_notional: float | None,
) -> PortfolioNotionalBudgetReport:
    known_values = []
    unknown_orders = 0
    for order in consolidated_orders:
        value = order.get("estimated_notional")
        if value is None:
            unknown_orders += 1
            continue
        known_values.append(abs(float(value)))
    return PortfolioNotionalBudgetReport(
        estimated_notional=sum(known_values),
        max_notional=max_notional,
        unknown_orders=unknown_orders,
    )


def _order_from_payload(payload: Mapping[str, Any]) -> Order:
    created_at = payload.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif not isinstance(created_at, datetime):
        created_at = datetime.now().astimezone()
    return Order(
        symbol=str(payload["symbol"]),
        side=payload.get("side", "BUY"),
        quantity=float(payload["quantity"]),
        order_type=payload.get("order_type", "MARKET"),
        limit_price=payload.get("limit_price"),
        stop_price=payload.get("stop_price"),
        take_profit_price=payload.get("take_profit_price"),
        trail_percent=payload.get("trail_percent"),
        time_in_force=str(payload.get("time_in_force", "day")),
        parent_order_id=payload.get("parent_order_id"),
        order_group_id=payload.get("order_group_id"),
        status=payload.get("status", "PENDING"),
        created_at=created_at,
        id=str(payload.get("id")),
        client_order_id=payload.get("client_order_id"),
    )


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


_REDACTED_BROKER_KEYS = {
    "account_id",
    "account_number",
    "asset_id",
    "id",
    "user_id",
}


def _redact_broker_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in _REDACTED_BROKER_KEYS:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_broker_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_broker_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_broker_payload(item) for item in value)
    return value


def load_paper_session_manifests(path: str | Path) -> tuple[PaperSessionManifest, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_manifests = _manifest_payloads(payload)
    return tuple(_paper_manifest_from_payload(item) for item in raw_manifests)


def _manifest_for_symbol(
    symbol: str,
    manifests: Sequence[PaperSessionManifest],
) -> PaperSessionManifest | None:
    normalized = symbol.upper()
    for manifest in manifests:
        if manifest.symbol.upper() == normalized:
            return manifest
    return None


def _manifest_payloads(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        raise ValueError("Paper manifest input must be a JSON object or list.")
    if isinstance(payload.get("enabled_manifests"), list):
        return [item for item in payload["enabled_manifests"] if isinstance(item, Mapping)]
    if isinstance(payload.get("paper_manifest"), Mapping):
        return [payload["paper_manifest"]]
    if isinstance(payload.get("candidates"), list):
        manifests = []
        for candidate in payload["candidates"]:
            if isinstance(candidate, Mapping) and isinstance(candidate.get("paper_manifest"), Mapping):
                manifests.append(candidate["paper_manifest"])
        return manifests
    return [payload]


def _paper_manifest_from_payload(payload: Mapping[str, Any]) -> PaperSessionManifest:
    strategy = payload.get("strategy_name") or payload.get("strategy")
    symbol = payload.get("symbol")
    if not strategy or not symbol:
        raise ValueError("Paper manifest entries require strategy_name and symbol.")
    params = payload.get("params") or {}
    if not isinstance(params, Mapping):
        raise ValueError("Paper manifest params must be a JSON object.")
    safeguards = payload.get("safeguards") or (
        "paper_trading_only",
        "runtime_risk_gates_required",
        "broker_reconciliation_required",
        "operator_kill_switch_required",
    )
    return PaperSessionManifest(
        strategy_name=str(strategy),
        symbol=str(symbol).upper(),
        params=dict(params),
        broker_mode=str(payload.get("broker_mode", "alpaca_paper")),
        data_source=str(payload.get("data_source", "alpaca")),
        execution_profile=str(payload.get("execution_profile", "paper_default")),
        manifest_status=str(payload.get("manifest_status", "ready_for_paper_session")),
        safeguards=tuple(safeguards),
    )


def _write_portfolio_report(
    report: PortfolioPaperSessionReport,
    options: PortfolioPaperSessionOptions,
) -> str:
    path = Path(options.artifact_root) / "portfolio-session-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(path)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(path)
