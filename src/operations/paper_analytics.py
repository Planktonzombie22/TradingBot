import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .paper_exit import PaperExitPreviewOrder
from .paper_lifecycle import PaperPositionLifecycle, PaperPositionLifecycleReport


@dataclass(frozen=True)
class PaperEndOfDayCloseoutDecision:
    symbol: str
    strategy_name: str
    policy: str
    action: str
    current_quantity: float
    target_quantity: float
    order: PaperExitPreviewOrder | None = None
    reason: str = "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "policy": self.policy,
            "action": self.action,
            "current_quantity": self.current_quantity,
            "target_quantity": self.target_quantity,
            "order": self.order.to_dict() if self.order else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperEndOfDayCloseoutReport:
    decisions: tuple[PaperEndOfDayCloseoutDecision, ...]
    default_overnight_policy: str = "hold"
    reduce_fraction: float = 0.5
    artifact_path: str | None = None

    @property
    def orders(self) -> tuple[PaperExitPreviewOrder, ...]:
        return tuple(decision.order for decision in self.decisions if decision.order is not None)

    @property
    def passed(self) -> bool:
        return all(decision.action in {"hold", "flatten", "reduce"} for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.orders:
            return "end_of_day_closeout_orders_planned"
        return "end_of_day_hold_all"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "default_overnight_policy": self.default_overnight_policy,
            "reduce_fraction": self.reduce_fraction,
            "orders": [order.to_dict() for order in self.orders],
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PaperPnlAttributionBucket:
    key: str
    strategy_name: str
    symbol: str
    signal_family: str
    regime: str
    execution_session: str
    positions: int
    market_value: float
    unrealized_pnl: float
    notional_drift: float
    slippage_bps: float | None = None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "signal_family": self.signal_family,
            "regime": self.regime,
            "execution_session": self.execution_session,
            "positions": self.positions,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "notional_drift": self.notional_drift,
            "slippage_bps": self.slippage_bps,
        }


@dataclass(frozen=True)
class PaperPnlAttributionReport:
    buckets: tuple[PaperPnlAttributionBucket, ...]
    total_market_value: float
    total_unrealized_pnl: float
    total_notional_drift: float
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return True

    @property
    def reason(self) -> str:
        return "pnl_attribution_created" if self.buckets else "no_positions_to_attribute"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "total_market_value": self.total_market_value,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "total_notional_drift": self.total_notional_drift,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PaperDrawdownReport:
    broker_equity: float | None
    mark_to_market_position_value: float
    mark_to_market_equity: float
    peak_equity: float
    drawdown: float
    drawdown_pct: float
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.drawdown >= 0.0

    @property
    def reason(self) -> str:
        return "paper_drawdown_tracked"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "broker_equity": self.broker_equity,
            "mark_to_market_position_value": self.mark_to_market_position_value,
            "mark_to_market_equity": self.mark_to_market_equity,
            "peak_equity": self.peak_equity,
            "drawdown": self.drawdown,
            "drawdown_pct": self.drawdown_pct,
            "artifact_path": self.artifact_path,
        }


def build_paper_eod_closeout_report(
    lifecycle_report: PaperPositionLifecycleReport,
    default_overnight_policy: str = "hold",
    policy_by_strategy: Mapping[str, str] | None = None,
    reduce_fraction: float = 0.5,
) -> PaperEndOfDayCloseoutReport:
    policies = {str(key): str(value).lower() for key, value in (policy_by_strategy or {}).items()}
    decisions = tuple(
        _eod_decision(
            position,
            policies.get(position.strategy_name, default_overnight_policy).lower(),
            reduce_fraction,
        )
        for position in lifecycle_report.positions
        if abs(position.observed_quantity) > 1e-12
    )
    return PaperEndOfDayCloseoutReport(
        decisions=decisions,
        default_overnight_policy=default_overnight_policy,
        reduce_fraction=reduce_fraction,
    )


def build_paper_pnl_attribution_report(
    lifecycle_report: PaperPositionLifecycleReport,
    metadata_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
) -> PaperPnlAttributionReport:
    metadata = {str(key).upper(): value for key, value in (metadata_by_symbol or {}).items()}
    raw_buckets: dict[tuple[str, str, str, str, str], list[PaperPositionLifecycle]] = {}
    for position in lifecycle_report.positions:
        meta = metadata.get(position.symbol.upper(), {})
        key = (
            position.strategy_name,
            position.symbol,
            str(meta.get("signal_family") or position.strategy_name or "unknown"),
            str(meta.get("regime") or "unknown"),
            str(meta.get("execution_session") or _execution_session(position)),
        )
        raw_buckets.setdefault(key, []).append(position)
    buckets = tuple(_attribution_bucket(key, positions) for key, positions in sorted(raw_buckets.items()))
    return PaperPnlAttributionReport(
        buckets=buckets,
        total_market_value=sum(bucket.market_value for bucket in buckets),
        total_unrealized_pnl=sum(bucket.unrealized_pnl for bucket in buckets),
        total_notional_drift=sum(bucket.notional_drift for bucket in buckets),
    )


def build_paper_drawdown_report(
    lifecycle_report: PaperPositionLifecycleReport,
    account_snapshot: Mapping[str, Any] | None = None,
    prior_peak_equity: float | None = None,
) -> PaperDrawdownReport:
    broker_equity = _optional_float((account_snapshot or {}).get("equity"))
    position_value = sum(abs(position.market_value or 0.0) for position in lifecycle_report.positions)
    mark_to_market_equity = broker_equity if broker_equity is not None else position_value
    peak_equity = max(prior_peak_equity or mark_to_market_equity, mark_to_market_equity)
    drawdown = max(0.0, peak_equity - mark_to_market_equity)
    drawdown_pct = drawdown / peak_equity if peak_equity else 0.0
    return PaperDrawdownReport(
        broker_equity=broker_equity,
        mark_to_market_position_value=position_value,
        mark_to_market_equity=mark_to_market_equity,
        peak_equity=peak_equity,
        drawdown=drawdown,
        drawdown_pct=drawdown_pct,
    )


def write_paper_eod_closeout_report(report: PaperEndOfDayCloseoutReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_paper_pnl_attribution_report(report: PaperPnlAttributionReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_paper_drawdown_report(report: PaperDrawdownReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def _eod_decision(
    position: PaperPositionLifecycle,
    policy: str,
    reduce_fraction: float,
) -> PaperEndOfDayCloseoutDecision:
    normalized = "flatten" if position.forced_exit_needed else policy
    if normalized in {"flat", "flatten", "intraday_flat"}:
        target_quantity = 0.0
        action = "flatten"
    elif normalized in {"reduce", "reduce_overnight"}:
        target_quantity = position.observed_quantity * max(0.0, min(reduce_fraction, 1.0))
        action = "reduce"
    else:
        target_quantity = position.observed_quantity
        action = "hold"
    order = _closeout_order(position, target_quantity, action, normalized)
    return PaperEndOfDayCloseoutDecision(
        symbol=position.symbol,
        strategy_name=position.strategy_name,
        policy=normalized,
        action=action,
        current_quantity=position.observed_quantity,
        target_quantity=target_quantity,
        order=order,
        reason="forced_exit_needed" if position.forced_exit_needed else f"overnight_policy_{normalized}",
    )


def _closeout_order(
    position: PaperPositionLifecycle,
    target_quantity: float,
    action: str,
    policy: str,
) -> PaperExitPreviewOrder | None:
    delta = position.observed_quantity - target_quantity
    if abs(delta) <= 1e-12:
        return None
    side = "SELL" if delta > 0 else "BUY"
    estimated_notional = abs(delta) * _unit_value(position)
    return PaperExitPreviewOrder(
        symbol=position.symbol,
        side=side,
        quantity=abs(delta),
        strategy_name=position.strategy_name,
        owner_type=position.owner_type,
        estimated_notional=estimated_notional,
        expected_realized_pnl=position.unrealized_pnl if action == "flatten" else None,
        position_status=position.status,
        reason=f"end_of_day_{policy}",
    )


def _unit_value(position: PaperPositionLifecycle) -> float:
    if position.market_value is not None and abs(position.observed_quantity) > 1e-12:
        return abs(position.market_value / position.observed_quantity)
    return float(position.average_fill_price or 0.0)


def _attribution_bucket(
    key: tuple[str, str, str, str, str],
    positions: list[PaperPositionLifecycle],
) -> PaperPnlAttributionBucket:
    strategy_name, symbol, signal_family, regime, execution_session = key
    slippages = [position.slippage_bps for position in positions if position.slippage_bps is not None]
    bucket_key = "|".join(key)
    return PaperPnlAttributionBucket(
        key=bucket_key,
        strategy_name=strategy_name,
        symbol=symbol,
        signal_family=signal_family,
        regime=regime,
        execution_session=execution_session,
        positions=len(positions),
        market_value=sum(abs(position.market_value or 0.0) for position in positions),
        unrealized_pnl=sum(position.unrealized_pnl or 0.0 for position in positions),
        notional_drift=sum(position.notional_drift or 0.0 for position in positions),
        slippage_bps=sum(slippages) / len(slippages) if slippages else None,
    )


def _execution_session(position: PaperPositionLifecycle) -> str:
    timestamp = position.fill_timestamp or position.opened_at or ""
    if "T" not in timestamp:
        return "unknown"
    hour = int(timestamp.split("T", 1)[1][:2])
    if hour < 14:
        return "pre_market_or_open"
    if hour < 19:
        return "regular"
    return "late_or_after_hours"


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
