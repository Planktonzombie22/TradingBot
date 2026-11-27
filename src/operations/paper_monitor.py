import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .paper_lifecycle import (
    PaperPositionLifecycleReport,
    append_paper_position_journal,
    build_paper_position_lifecycle_report,
)
from .paper_orders import PaperOpenOrderReport, build_paper_open_order_report


@dataclass(frozen=True)
class PaperPositionMatch:
    symbol: str
    expected_quantity: float
    observed_quantity: float
    difference: float
    market_value: float | None = None

    @property
    def matched(self) -> bool:
        return abs(self.difference) <= 1e-6

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "expected_quantity": self.expected_quantity,
            "observed_quantity": self.observed_quantity,
            "difference": self.difference,
            "market_value": self.market_value,
            "matched": self.matched,
        }


@dataclass(frozen=True)
class PaperMonitorReport:
    expected_positions: Mapping[str, float]
    observed_positions: Mapping[str, float]
    matches: tuple[PaperPositionMatch, ...]
    observed_notional: float
    max_expected_notional: float | None = None
    notional_tolerance: float = 0.0
    unexpected_symbols: tuple[str, ...] = ()
    missing_symbols: tuple[str, ...] = ()
    closed_symbols: tuple[str, ...] = ()
    lifecycle: PaperPositionLifecycleReport | None = None
    open_orders: PaperOpenOrderReport | None = None
    reason: str = "passed"
    artifact_path: str | None = None

    @property
    def exposure_within_budget(self) -> bool:
        return self.max_expected_notional is None or self.observed_notional <= self.max_expected_notional + self.notional_tolerance

    @property
    def passed(self) -> bool:
        return (
            all(match.matched for match in self.matches)
            and not self.unexpected_symbols
            and not self.missing_symbols
            and self.exposure_within_budget
            and (self.open_orders is None or self.open_orders.passed)
        )

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": "passed" if self.passed else self.reason,
            "expected_positions": dict(self.expected_positions),
            "observed_positions": dict(self.observed_positions),
            "matches": [match.to_dict() for match in self.matches],
            "observed_notional": self.observed_notional,
            "max_expected_notional": self.max_expected_notional,
            "notional_tolerance": self.notional_tolerance,
            "exposure_within_budget": self.exposure_within_budget,
            "unexpected_symbols": list(self.unexpected_symbols),
            "missing_symbols": list(self.missing_symbols),
            "closed_symbols": list(self.closed_symbols),
            "lifecycle": self.lifecycle.to_dict() if self.lifecycle else None,
            "open_orders": self.open_orders.to_dict() if self.open_orders else None,
            "artifact_path": self.artifact_path,
        }


def build_paper_monitor_report(
    portfolio_report: Mapping[str, Any],
    position_snapshot: Mapping[str, Any],
    max_expected_notional: float | None = None,
    open_order_snapshot: Mapping[str, Any] | None = None,
    max_open_order_age_minutes: float = 15.0,
    cleanup_evidence: Mapping[str, Any] | None = None,
    now=None,
) -> PaperMonitorReport:
    cleanup_closures = _cleanup_closed_positions(cleanup_evidence or {})
    expected = _apply_cleanup_closures(_expected_positions(portfolio_report), cleanup_closures)
    observed, market_values = _observed_positions(position_snapshot)
    symbols = tuple(sorted(set(expected) | set(observed)))
    matches = tuple(
        PaperPositionMatch(
            symbol=symbol,
            expected_quantity=expected.get(symbol, 0.0),
            observed_quantity=observed.get(symbol, 0.0),
            difference=observed.get(symbol, 0.0) - expected.get(symbol, 0.0),
            market_value=market_values.get(symbol),
        )
        for symbol in symbols
    )
    unexpected = tuple(symbol for symbol in sorted(set(observed) - set(expected)) if abs(observed[symbol]) > 1e-6)
    missing = tuple(symbol for symbol in sorted(set(expected) - set(observed)) if abs(expected[symbol]) > 1e-6)
    observed_notional = sum(abs(value) for value in market_values.values())
    limit = _monitor_notional_limit(portfolio_report, max_expected_notional)
    tolerance = _monitor_notional_tolerance(limit)
    lifecycle = build_paper_position_lifecycle_report(
        portfolio_report,
        position_snapshot,
        cleanup_evidence=cleanup_evidence,
        now=now,
    )
    open_orders = (
        build_paper_open_order_report(
            portfolio_report,
            open_order_snapshot,
            now=now,
            max_open_order_age_minutes=max_open_order_age_minutes,
        )
        if open_order_snapshot is not None
        else None
    )
    reason = _monitor_reason(matches, unexpected, missing, observed_notional, limit, tolerance, open_orders)
    return PaperMonitorReport(
        expected_positions=expected,
        observed_positions=observed,
        matches=matches,
        observed_notional=observed_notional,
        max_expected_notional=limit,
        notional_tolerance=tolerance,
        unexpected_symbols=unexpected,
        missing_symbols=missing,
        closed_symbols=tuple(sorted(cleanup_closures)),
        lifecycle=lifecycle,
        open_orders=open_orders,
        reason=reason,
    )


def write_paper_monitor_report(report: PaperMonitorReport, path: str | Path, journal_path: str | Path | None = None) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(output)
    if journal_path and report.lifecycle:
        payload["position_journal_path"] = append_paper_position_journal(report.lifecycle, journal_path)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def _expected_positions(portfolio_report: Mapping[str, Any]) -> dict[str, float]:
    submission = portfolio_report.get("submission") if isinstance(portfolio_report.get("submission"), Mapping) else {}
    submitted = submission.get("submitted_orders") or portfolio_report.get("submitted_orders") or ()
    positions: dict[str, float] = {}
    for order in submitted:
        if not isinstance(order, Mapping):
            continue
        if str(order.get("status", "")).upper() not in {"FILLED", "PARTIALLY_FILLED"}:
            continue
        symbol = str(order.get("symbol", "")).upper()
        if not symbol:
            continue
        quantity = float(order.get("quantity") or 0.0)
        signed = quantity if str(order.get("side", "")).upper() == "BUY" else -quantity
        positions[symbol] = positions.get(symbol, 0.0) + signed
    return positions


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


def _apply_cleanup_closures(expected: Mapping[str, float], closures: Mapping[str, float]) -> dict[str, float]:
    adjusted = dict(expected)
    for symbol, closed_quantity in closures.items():
        adjusted[symbol] = adjusted.get(symbol, 0.0) - closed_quantity
        if abs(adjusted[symbol]) <= 1e-6:
            adjusted.pop(symbol, None)
    return adjusted


def _observed_positions(position_snapshot: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    positions: dict[str, float] = {}
    market_values: dict[str, float] = {}
    for item in position_snapshot.get("positions_seen") or ():
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol", "")).upper()
        if not symbol:
            continue
        positions[symbol] = positions.get(symbol, 0.0) + float(item.get("quantity") or 0.0)
        if item.get("market_value") is not None:
            market_values[symbol] = market_values.get(symbol, 0.0) + float(item["market_value"])
    return positions, market_values


def _monitor_notional_limit(portfolio_report: Mapping[str, Any], override: float | None) -> float | None:
    if override is not None:
        return override
    submission = portfolio_report.get("submission") if isinstance(portfolio_report.get("submission"), Mapping) else {}
    budget = submission.get("notional_budget") or {}
    value = budget.get("max_notional")
    if value is not None:
        return float(value)
    risk_budget = portfolio_report.get("risk_budget") if isinstance(portfolio_report.get("risk_budget"), Mapping) else {}
    budget_payload = risk_budget.get("budget") if isinstance(risk_budget.get("budget"), Mapping) else {}
    value = budget_payload.get("max_session_notional")
    return float(value) if value is not None else None


def _monitor_reason(
    matches: Sequence[PaperPositionMatch],
    unexpected: Sequence[str],
    missing: Sequence[str],
    observed_notional: float,
    max_expected_notional: float | None,
    notional_tolerance: float = 0.0,
    open_orders: PaperOpenOrderReport | None = None,
) -> str:
    if unexpected:
        return "unexpected_paper_positions"
    if missing:
        return "missing_expected_paper_positions"
    if any(not match.matched for match in matches):
        return "paper_position_quantity_mismatch"
    if max_expected_notional is not None and observed_notional > max_expected_notional + notional_tolerance:
        return "paper_position_notional_exceeds_budget"
    if open_orders is not None and not open_orders.passed:
        return open_orders.reason
    return "passed"


def _monitor_notional_tolerance(max_expected_notional: float | None) -> float:
    if max_expected_notional is None:
        return 0.0
    return max(0.01, abs(max_expected_notional) * 0.02)
