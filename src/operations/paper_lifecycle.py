import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


FRESH_MAX_HOURS = 24.0
ACTIVE_MAX_HOURS = 72.0


@dataclass(frozen=True)
class PaperPositionLifecycle:
    symbol: str
    strategy_name: str
    expected_quantity: float
    observed_quantity: float
    target_notional: float | None = None
    market_value: float | None = None
    requested_quantity: float | None = None
    filled_quantity: float | None = None
    average_fill_price: float | None = None
    reference_price: float | None = None
    slippage_per_share: float | None = None
    slippage_bps: float | None = None
    unrealized_pnl: float | None = None
    notional_drift: float | None = None
    broker_status: str | None = None
    order_type: str | None = None
    time_in_force: str | None = None
    fill_timestamp: str | None = None
    entry_rationale: str = "promoted_portfolio_paper_submit"
    expected_holding_window: str = "micro_pilot_max_3_days"
    risk_budget: Mapping[str, Any] | None = None
    stop_policy: str = "monitor_only_until_strategy_exit_controls_exist"
    exit_policy: str = "manual_or_strategy_exit_required"
    source_report_path: str | None = None
    opened_at: str | None = None
    age_hours: float | None = None
    status: str = "active"
    owner_type: str = "promoted_strategy"

    @property
    def matched(self) -> bool:
        return abs(self.observed_quantity - self.expected_quantity) <= 1e-6

    @property
    def forced_exit_needed(self) -> bool:
        return self.status in {"stale", "expired", "orphan"}

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "expected_quantity": self.expected_quantity,
            "observed_quantity": self.observed_quantity,
            "matched": self.matched,
            "target_notional": self.target_notional,
            "market_value": self.market_value,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "average_fill_price": self.average_fill_price,
            "reference_price": self.reference_price,
            "slippage_per_share": self.slippage_per_share,
            "slippage_bps": self.slippage_bps,
            "unrealized_pnl": self.unrealized_pnl,
            "notional_drift": self.notional_drift,
            "broker_status": self.broker_status,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "fill_timestamp": self.fill_timestamp,
            "entry_rationale": self.entry_rationale,
            "expected_holding_window": self.expected_holding_window,
            "risk_budget": dict(self.risk_budget or {}),
            "stop_policy": self.stop_policy,
            "exit_policy": self.exit_policy,
            "source_report_path": self.source_report_path,
            "opened_at": self.opened_at,
            "age_hours": self.age_hours,
            "status": self.status,
            "owner_type": self.owner_type,
            "forced_exit_needed": self.forced_exit_needed,
        }


@dataclass(frozen=True)
class PaperPositionScorecard:
    symbol: str
    quantity_matched: bool
    fill_price_present: bool
    market_value_present: bool
    notional_drift: float | None = None
    slippage_bps: float | None = None
    unrealized_pnl: float | None = None
    reason: str = "passed"

    @property
    def passed(self) -> bool:
        return self.quantity_matched and self.fill_price_present and self.market_value_present and self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "passed": self.passed,
            "reason": "passed" if self.passed else self.reason,
            "quantity_matched": self.quantity_matched,
            "fill_price_present": self.fill_price_present,
            "market_value_present": self.market_value_present,
            "notional_drift": self.notional_drift,
            "slippage_bps": self.slippage_bps,
            "unrealized_pnl": self.unrealized_pnl,
        }


@dataclass(frozen=True)
class PaperExposureRegistry:
    active_expected_symbols: tuple[str, ...] = ()
    orphan_symbols: tuple[str, ...] = ()
    missing_expected_symbols: tuple[str, ...] = ()
    stale_symbols: tuple[str, ...] = ()
    expired_symbols: tuple[str, ...] = ()

    @property
    def cleanup_debt_symbols(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.orphan_symbols + self.stale_symbols + self.expired_symbols))

    def to_dict(self) -> dict:
        return {
            "active_expected_symbols": list(self.active_expected_symbols),
            "orphan_symbols": list(self.orphan_symbols),
            "missing_expected_symbols": list(self.missing_expected_symbols),
            "stale_symbols": list(self.stale_symbols),
            "expired_symbols": list(self.expired_symbols),
            "cleanup_debt_symbols": list(self.cleanup_debt_symbols),
        }


@dataclass(frozen=True)
class PaperPositionLifecycleReport:
    positions: tuple[PaperPositionLifecycle, ...]
    scorecards: tuple[PaperPositionScorecard, ...]
    exposure_registry: PaperExposureRegistry
    observed_at: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return (
            not self.exposure_registry.orphan_symbols
            and not self.exposure_registry.missing_expected_symbols
            and all(scorecard.passed for scorecard in self.scorecards)
        )

    @property
    def active_positions(self) -> tuple[PaperPositionLifecycle, ...]:
        return tuple(position for position in self.positions if position.status in {"fresh", "active"})

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "observed_at": self.observed_at,
            "positions": [position.to_dict() for position in self.positions],
            "scorecards": [scorecard.to_dict() for scorecard in self.scorecards],
            "active_positions": len(self.active_positions),
            "exposure_registry": self.exposure_registry.to_dict(),
            "artifact_path": self.artifact_path,
        }


def build_paper_position_lifecycle_report(
    portfolio_report: Mapping[str, Any],
    position_snapshot: Mapping[str, Any],
    cleanup_evidence: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> PaperPositionLifecycleReport:
    observed_at = now or datetime.now(timezone.utc)
    expected = _apply_cleanup_closures_to_intents(
        _expected_position_intents(portfolio_report),
        _cleanup_closed_positions(cleanup_evidence or {}),
    )
    observed = _observed_position_payloads(position_snapshot)
    symbols = tuple(sorted(set(expected) | set(observed)))
    positions = tuple(
        _position_lifecycle(
            symbol,
            expected.get(symbol),
            observed.get(symbol),
            portfolio_report,
            observed_at,
        )
        for symbol in symbols
    )
    registry = _exposure_registry(positions)
    return PaperPositionLifecycleReport(
        positions=positions,
        scorecards=tuple(_position_scorecard(position) for position in positions),
        exposure_registry=registry,
        observed_at=observed_at.isoformat(),
    )


def write_paper_position_lifecycle_report(report: PaperPositionLifecycleReport, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def append_paper_position_journal(report: PaperPositionLifecycleReport, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        for position in report.positions:
            handle.write(json.dumps({"observed_at": report.observed_at, "position": position.to_dict()}) + "\n")
    return str(output)


def _expected_position_intents(portfolio_report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    consolidated = portfolio_report.get("consolidated_orders") or ()
    executions = _execution_reports_by_order_id(portfolio_report)
    submission = portfolio_report.get("submission") if isinstance(portfolio_report.get("submission"), Mapping) else {}
    submitted_orders = submission.get("submitted_orders") or portfolio_report.get("submitted_orders") or ()
    submitted = {
        str(order.get("symbol", "")).upper(): _submitted_order_with_execution(order, executions)
        for order in submitted_orders
        if isinstance(order, Mapping) and str(order.get("status", "")).upper() in {"FILLED", "PARTIALLY_FILLED"}
    }
    if not consolidated:
        return {
            symbol: _intent_from_submitted_order(order)
            for symbol, order in submitted.items()
        }
    intents: dict[str, Mapping[str, Any]] = {}
    for order in consolidated:
        if not isinstance(order, Mapping):
            continue
        symbol = str(order.get("symbol", "")).upper()
        fill = submitted.get(symbol)
        if not symbol or fill is None:
            continue
        side = str(fill.get("side") or order.get("side") or "").upper()
        quantity = float(fill.get("filled_quantity") or fill.get("quantity") or order.get("quantity") or 0.0)
        signed_quantity = quantity if side == "BUY" else -quantity
        payload = dict(order)
        payload["expected_quantity"] = signed_quantity
        payload["requested_quantity"] = _optional_float(order.get("original_quantity") or order.get("quantity"))
        payload["filled_quantity"] = quantity
        payload["average_fill_price"] = fill.get("average_fill_price")
        payload["broker_status"] = fill.get("execution_status") or fill.get("status")
        payload["order_type"] = fill.get("order_type") or order.get("order_type")
        payload["time_in_force"] = fill.get("time_in_force") or order.get("time_in_force")
        payload["fill_timestamp"] = fill.get("fill_timestamp") or fill.get("submitted_at")
        payload["opened_at"] = fill.get("created_at") or order.get("created_at")
        intents[symbol] = payload
    return intents


def _cleanup_closed_positions(cleanup_evidence: Mapping[str, Any]) -> dict[str, float]:
    if not cleanup_evidence or not cleanup_evidence.get("submitted"):
        return {}
    closures: dict[str, float] = {}
    for order in cleanup_evidence.get("submitted_orders") or ():
        if not isinstance(order, Mapping):
            continue
        if str(order.get("status", "")).upper() not in {"FILLED", "PARTIALLY_FILLED"}:
            continue
        symbol = str(order.get("symbol") or "").upper()
        if not symbol:
            continue
        quantity = float(order.get("quantity") or 0.0)
        signed = quantity if str(order.get("side", "")).upper() == "SELL" else -quantity
        closures[symbol] = closures.get(symbol, 0.0) + signed
    return closures


def _apply_cleanup_closures_to_intents(
    expected: Mapping[str, Mapping[str, Any]],
    closures: Mapping[str, float],
) -> dict[str, Mapping[str, Any]]:
    adjusted: dict[str, Mapping[str, Any]] = {symbol: dict(intent) for symbol, intent in expected.items()}
    for symbol, closed_quantity in closures.items():
        if symbol not in adjusted:
            continue
        intent = dict(adjusted[symbol])
        remaining = float(intent.get("expected_quantity") or 0.0) - closed_quantity
        if abs(remaining) <= 1e-6:
            adjusted.pop(symbol, None)
        else:
            intent["expected_quantity"] = remaining
            adjusted[symbol] = intent
    return adjusted


def _intent_from_submitted_order(order: Mapping[str, Any]) -> dict:
    side = str(order.get("side", "")).upper()
    quantity = float(order.get("filled_quantity") or order.get("quantity") or 0.0)
    return {
        "symbol": str(order.get("symbol", "")).upper(),
        "side": side,
        "strategy_name": order.get("strategy_name") or "unknown",
        "expected_quantity": quantity if side == "BUY" else -quantity,
        "requested_quantity": _optional_float(order.get("quantity")),
        "filled_quantity": quantity,
        "average_fill_price": order.get("average_fill_price"),
        "broker_status": order.get("execution_status") or order.get("status"),
        "order_type": order.get("order_type"),
        "time_in_force": order.get("time_in_force"),
        "fill_timestamp": order.get("fill_timestamp") or order.get("submitted_at"),
        "opened_at": order.get("created_at"),
        "estimated_notional": order.get("estimated_notional"),
        "source_report_path": order.get("source_report_path"),
    }


def _observed_position_payloads(position_snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    observed: dict[str, Mapping[str, Any]] = {}
    for position in position_snapshot.get("positions_seen") or ():
        if isinstance(position, Mapping) and position.get("symbol"):
            observed[str(position["symbol"]).upper()] = position
    return observed


def _position_lifecycle(
    symbol: str,
    expected: Mapping[str, Any] | None,
    observed: Mapping[str, Any] | None,
    portfolio_report: Mapping[str, Any],
    now: datetime,
) -> PaperPositionLifecycle:
    expected_quantity = float((expected or {}).get("expected_quantity") or 0.0)
    observed_quantity = float((observed or {}).get("quantity") or 0.0)
    target_notional = _optional_float((expected or {}).get("estimated_notional"))
    market_value = _optional_float((observed or {}).get("market_value"))
    average_fill_price = _optional_float((expected or {}).get("average_fill_price")) or _average_entry_price(observed)
    reference_price = _optional_float((expected or {}).get("latest_price"))
    age_hours = _age_hours((expected or {}).get("opened_at"), now)
    status = _position_status(expected, observed, age_hours)
    return PaperPositionLifecycle(
        symbol=symbol,
        strategy_name=str((expected or {}).get("strategy_name") or "unknown"),
        expected_quantity=expected_quantity,
        observed_quantity=observed_quantity,
        target_notional=target_notional,
        market_value=market_value,
        requested_quantity=_optional_float((expected or {}).get("requested_quantity")),
        filled_quantity=_optional_float((expected or {}).get("filled_quantity")),
        average_fill_price=average_fill_price,
        reference_price=reference_price,
        slippage_per_share=_slippage_per_share(average_fill_price, reference_price, (expected or {}).get("side")),
        slippage_bps=_slippage_bps(average_fill_price, reference_price, (expected or {}).get("side")),
        unrealized_pnl=_unrealized_pnl(observed),
        notional_drift=_notional_drift(market_value, target_notional),
        broker_status=(expected or {}).get("broker_status"),
        order_type=(expected or {}).get("order_type"),
        time_in_force=(expected or {}).get("time_in_force"),
        fill_timestamp=(expected or {}).get("fill_timestamp"),
        risk_budget=_risk_budget(portfolio_report),
        source_report_path=(expected or {}).get("source_report_path"),
        opened_at=(expected or {}).get("opened_at"),
        age_hours=age_hours,
        status=status,
        owner_type="promoted_strategy" if expected else "unknown_broker_position",
    )


def _position_status(expected: Mapping[str, Any] | None, observed: Mapping[str, Any] | None, age_hours: float | None) -> str:
    if expected is None and observed is not None:
        return "orphan"
    if expected is not None and observed is None:
        return "missing"
    if age_hours is None:
        return "active"
    if age_hours <= FRESH_MAX_HOURS:
        return "fresh"
    if age_hours <= ACTIVE_MAX_HOURS:
        return "active"
    return "stale"


def _exposure_registry(positions: Sequence[PaperPositionLifecycle]) -> PaperExposureRegistry:
    return PaperExposureRegistry(
        active_expected_symbols=tuple(position.symbol for position in positions if position.status in {"fresh", "active"}),
        orphan_symbols=tuple(position.symbol for position in positions if position.status == "orphan"),
        missing_expected_symbols=tuple(position.symbol for position in positions if position.status == "missing"),
        stale_symbols=tuple(position.symbol for position in positions if position.status == "stale"),
        expired_symbols=tuple(position.symbol for position in positions if position.status == "expired"),
    )


def _risk_budget(portfolio_report: Mapping[str, Any]) -> dict:
    budget = ((portfolio_report.get("submission") or {}).get("notional_budget") or {})
    return {
        "max_notional": budget.get("max_notional"),
        "estimated_notional": budget.get("estimated_notional"),
        "budget_passed": budget.get("passed"),
    }


def _position_scorecard(position: PaperPositionLifecycle) -> PaperPositionScorecard:
    reason = "passed"
    if not position.matched:
        reason = "paper_position_quantity_mismatch"
    elif position.average_fill_price is None:
        reason = "missing_average_fill_price"
    elif position.market_value is None:
        reason = "missing_market_value"
    return PaperPositionScorecard(
        symbol=position.symbol,
        quantity_matched=position.matched,
        fill_price_present=position.average_fill_price is not None,
        market_value_present=position.market_value is not None,
        notional_drift=position.notional_drift,
        slippage_bps=position.slippage_bps,
        unrealized_pnl=position.unrealized_pnl,
        reason=reason,
    )


def _execution_reports_by_order_id(portfolio_report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    reports = {}
    submission = portfolio_report.get("submission") if isinstance(portfolio_report.get("submission"), Mapping) else {}
    for report in submission.get("execution_reports") or portfolio_report.get("execution_reports") or ():
        if isinstance(report, Mapping) and report.get("order_id"):
            reports[str(report["order_id"])] = report
    return reports


def _submitted_order_with_execution(order: Mapping[str, Any], executions: Mapping[str, Mapping[str, Any]]) -> dict:
    payload = dict(order)
    execution = executions.get(str(order.get("id"))) or executions.get(str(order.get("order_id")))
    if execution:
        if execution.get("filled_quantity") is not None:
            payload["filled_quantity"] = execution["filled_quantity"]
        if execution.get("average_fill_price") is not None:
            payload["average_fill_price"] = execution["average_fill_price"]
        payload["execution_status"] = execution.get("status")
        payload["fill_timestamp"] = execution.get("submitted_at")
    return payload


def _average_entry_price(observed: Mapping[str, Any] | None) -> float | None:
    if not observed:
        return None
    if observed.get("average_entry_price") is not None:
        return _optional_float(observed.get("average_entry_price"))
    raw = observed.get("raw") or {}
    return _optional_float(raw.get("avg_entry_price")) if isinstance(raw, Mapping) else None


def _unrealized_pnl(observed: Mapping[str, Any] | None) -> float | None:
    if not observed:
        return None
    if observed.get("unrealized_pl") is not None:
        return _optional_float(observed.get("unrealized_pl"))
    raw = observed.get("raw") or {}
    return _optional_float(raw.get("unrealized_pl")) if isinstance(raw, Mapping) else None


def _notional_drift(market_value: float | None, target_notional: float | None) -> float | None:
    if market_value is None or target_notional is None:
        return None
    return abs(market_value) - abs(target_notional)


def _slippage_per_share(fill_price: float | None, reference_price: float | None, side: Any) -> float | None:
    if fill_price is None or reference_price in {None, 0}:
        return None
    direction = 1.0 if str(side).upper() == "BUY" else -1.0
    return (fill_price - reference_price) * direction


def _slippage_bps(fill_price: float | None, reference_price: float | None, side: Any) -> float | None:
    per_share = _slippage_per_share(fill_price, reference_price, side)
    if per_share is None or reference_price in {None, 0}:
        return None
    return per_share / abs(reference_price) * 10_000.0


def _age_hours(raw: Any, now: datetime) -> float | None:
    if not raw:
        return None
    try:
        opened = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    return max((now - opened.astimezone(timezone.utc)).total_seconds() / 3600.0, 0.0)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
