import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


LIVE_ENDPOINT = "https://api.alpaca.markets"
PAPER_ENDPOINT = "https://paper-api.alpaca.markets"
LIVE_VALIDATION_CHECKS = (
    "live_order_preview",
    "live_micro_proof",
    "live_account_monitor",
    "live_reconciliation",
    "live_risk_caps",
    "live_command_confirmation",
)


@dataclass(frozen=True)
class LiveBrokerAdapterBoundaryReport:
    paper_endpoint: str
    live_endpoint: str
    account_fingerprint: str
    approved_account_fingerprints: tuple[str, ...]
    shared_submit_defaults: bool = False
    live_submit_default_enabled: bool = False

    @property
    def passed(self) -> bool:
        return (
            self.paper_endpoint.rstrip("/") != self.live_endpoint.rstrip("/")
            and self.live_endpoint.rstrip("/") == LIVE_ENDPOINT
            and self.account_fingerprint in self.approved_account_fingerprints
            and not self.shared_submit_defaults
            and not self.live_submit_default_enabled
        )

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "paper_endpoint": self.paper_endpoint,
            "live_endpoint": self.live_endpoint,
            "account_fingerprint": self.account_fingerprint,
            "approved_account_fingerprints": list(self.approved_account_fingerprints),
            "shared_submit_defaults": self.shared_submit_defaults,
            "live_submit_default_enabled": self.live_submit_default_enabled,
            "reason": "live_adapter_boundary_passed" if self.passed else "live_adapter_boundary_blocked",
        }


@dataclass(frozen=True)
class LiveOrderPreviewReport:
    orders: tuple[Mapping[str, Any], ...]
    risk_settings: Mapping[str, Any]
    refused_to_submit: bool = True

    @property
    def total_notional(self) -> float:
        return sum(_notional(order) for order in self.orders)

    @property
    def passed(self) -> bool:
        return bool(self.orders) and self.refused_to_submit

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "refused_to_submit": self.refused_to_submit,
            "orders": [dict(order) for order in self.orders],
            "risk_settings": dict(self.risk_settings),
            "total_notional": self.total_notional,
            "reason": "live_order_preview_created_without_submit" if self.passed else "live_order_preview_invalid",
        }


@dataclass(frozen=True)
class LiveMicroTradeProofReport:
    symbol: str
    planned_notional: float
    operator_approved: bool
    submitted: bool = False
    monitor_artifact: str | None = None

    @property
    def passed(self) -> bool:
        return self.operator_approved and self.planned_notional > 0 and not self.submitted and bool(self.monitor_artifact)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "symbol": self.symbol,
            "planned_notional": self.planned_notional,
            "operator_approved": self.operator_approved,
            "submitted": self.submitted,
            "monitor_artifact": self.monitor_artifact,
            "reason": "live_micro_proof_preview_ready" if self.passed else "live_micro_proof_blocked",
        }


@dataclass(frozen=True)
class LiveAccountMonitorReport:
    expected_positions: tuple[Mapping[str, Any], ...]
    broker_positions: tuple[Mapping[str, Any], ...]
    tolerance_quantity: float = 0.000001

    @property
    def mismatches(self) -> tuple[Mapping[str, Any], ...]:
        expected = {str(row.get("symbol", "")).upper(): _quantity(row) for row in self.expected_positions}
        broker = {str(row.get("symbol", "")).upper(): _quantity(row) for row in self.broker_positions}
        symbols = sorted(set(expected) | set(broker))
        rows = []
        for symbol in symbols:
            diff = broker.get(symbol, 0.0) - expected.get(symbol, 0.0)
            if abs(diff) > self.tolerance_quantity:
                rows.append({"symbol": symbol, "expected_quantity": expected.get(symbol, 0.0), "broker_quantity": broker.get(symbol, 0.0), "diff": diff})
        return tuple(rows)

    @property
    def passed(self) -> bool:
        return not self.mismatches

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "expected_positions": [dict(row) for row in self.expected_positions],
            "broker_positions": [dict(row) for row in self.broker_positions],
            "tolerance_quantity": self.tolerance_quantity,
            "mismatches": [dict(row) for row in self.mismatches],
        }


@dataclass(frozen=True)
class LiveOrderLifecycleReconciliationReport:
    lifecycle_events: tuple[Mapping[str, Any], ...]

    @property
    def missing_order_ids(self) -> tuple[str, ...]:
        by_order: dict[str, set[str]] = {}
        for event in self.lifecycle_events:
            order_id = str(event.get("order_id", ""))
            if order_id:
                by_order.setdefault(order_id, set()).add(str(event.get("stage", "")))
        return tuple(order_id for order_id, stages in by_order.items() if not {"intent", "submit", "reconcile"}.issubset(stages))

    @property
    def failed_events(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(event for event in self.lifecycle_events if str(event.get("status", "")).lower() in {"failed", "rejected", "missing", "blocked"})

    @property
    def passed(self) -> bool:
        return bool(self.lifecycle_events) and not self.missing_order_ids and not self.failed_events

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "events": [dict(event) for event in self.lifecycle_events],
            "missing_order_ids": list(self.missing_order_ids),
            "failed_events": [dict(event) for event in self.failed_events],
        }


@dataclass(frozen=True)
class LivePositionFlattenPlanReport:
    positions: tuple[Mapping[str, Any], ...]
    operator_approved: bool = False
    emergency_path: str | None = None

    @property
    def planned_orders(self) -> tuple[Mapping[str, Any], ...]:
        orders = []
        for row in self.positions:
            quantity = _quantity(row)
            if quantity == 0:
                continue
            orders.append(
                {
                    "symbol": str(row.get("symbol", "")).upper(),
                    "side": "SELL" if quantity > 0 else "BUY",
                    "quantity": abs(quantity),
                    "order_type": "MARKET",
                    "reason": "live_position_flatten_preview",
                }
            )
        return tuple(orders)

    @property
    def passed(self) -> bool:
        return self.operator_approved and bool(self.emergency_path) and bool(self.planned_orders)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "operator_approved": self.operator_approved,
            "emergency_path": self.emergency_path,
            "positions": [dict(row) for row in self.positions],
            "planned_orders": [dict(order) for order in self.planned_orders],
            "submitted": False,
        }


@dataclass(frozen=True)
class LiveReadinessValidationEvidenceReport:
    evidence: tuple[Mapping[str, Any], ...]

    @property
    def missing_checks(self) -> tuple[str, ...]:
        live_passed = {str(row.get("check_id")) for row in self.evidence if row.get("evidence_type") == "live" and row.get("status") == "passed"}
        return tuple(check for check in LIVE_VALIDATION_CHECKS if check not in live_passed)

    @property
    def passed(self) -> bool:
        return not self.missing_checks

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "evidence": [dict(row) for row in self.evidence],
            "missing_checks": list(self.missing_checks),
        }


@dataclass(frozen=True)
class LiveReleaseBundleReport:
    paper_soak_current: bool
    deployment_proof_current: bool
    monitor_proof_current: bool
    risk_settings_current: bool
    operator_approved: bool

    @property
    def passed(self) -> bool:
        return self.paper_soak_current and self.deployment_proof_current and self.monitor_proof_current and self.risk_settings_current and self.operator_approved

    def to_dict(self) -> dict:
        checks = {
            "paper_soak_current": self.paper_soak_current,
            "deployment_proof_current": self.deployment_proof_current,
            "monitor_proof_current": self.monitor_proof_current,
            "risk_settings_current": self.risk_settings_current,
            "operator_approved": self.operator_approved,
        }
        return {"passed": self.passed, "checks": checks, "blockers": [key for key, value in checks.items() if not value]}


@dataclass(frozen=True)
class LiveRiskCapReport:
    orders: tuple[Mapping[str, Any], ...]
    caps: Mapping[str, Any]
    current_daily_notional: float = 0.0
    current_daily_loss: float = 0.0
    current_open_positions: int = 0
    current_gross_exposure: float = 0.0

    @property
    def blockers(self) -> tuple[str, ...]:
        total_notional = sum(_notional(order) for order in self.orders)
        first_order = _notional(self.orders[0]) if self.orders else 0.0
        blockers = []
        if first_order > float(self.caps.get("max_first_order_notional", 0.0)):
            blockers.append("max_first_order_notional")
        if self.current_daily_notional + total_notional > float(self.caps.get("max_daily_notional", 0.0)):
            blockers.append("max_daily_notional")
        if abs(self.current_daily_loss) > float(self.caps.get("max_daily_loss", 0.0)):
            blockers.append("max_daily_loss")
        if self.current_open_positions + len({str(order.get("symbol", "")).upper() for order in self.orders}) > int(self.caps.get("max_open_positions", 0)):
            blockers.append("max_open_positions")
        if self.current_gross_exposure + total_notional > float(self.caps.get("max_gross_exposure", 0.0)):
            blockers.append("max_gross_exposure")
        return tuple(blockers)

    @property
    def passed(self) -> bool:
        return bool(self.orders) and not self.blockers

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "orders": [dict(order) for order in self.orders],
            "caps": dict(self.caps),
            "current_daily_notional": self.current_daily_notional,
            "current_daily_loss": self.current_daily_loss,
            "current_open_positions": self.current_open_positions,
            "current_gross_exposure": self.current_gross_exposure,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class LiveSchedulerModeReport:
    enabled: bool
    mode: str = "manual"
    micro_proof_passed: bool = False

    @property
    def passed(self) -> bool:
        return (not self.enabled and self.mode == "manual") or (self.enabled and self.micro_proof_passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "enabled": self.enabled,
            "mode": self.mode,
            "micro_proof_passed": self.micro_proof_passed,
            "reason": "live_scheduler_allowed" if self.passed else "live_scheduler_must_remain_disabled",
        }


@dataclass(frozen=True)
class LiveCommandConfirmationReport:
    timestamp: str
    account_fingerprint: str
    strategy: str
    notional: float
    expected_order: Mapping[str, Any]
    risk_settings: Mapping[str, Any]
    operator_approved: bool

    @property
    def passed(self) -> bool:
        return bool(self.timestamp and self.account_fingerprint and self.strategy and self.expected_order and self.risk_settings and self.operator_approved)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "timestamp": self.timestamp,
            "account_fingerprint": self.account_fingerprint,
            "strategy": self.strategy,
            "notional": self.notional,
            "expected_order": dict(self.expected_order),
            "risk_settings": dict(self.risk_settings),
            "operator_approved": self.operator_approved,
        }


@dataclass(frozen=True)
class OneLiveOrderPerDayReport:
    trade_date: str
    prior_orders: tuple[Mapping[str, Any], ...]
    requested_orders: tuple[Mapping[str, Any], ...]

    @property
    def passed(self) -> bool:
        return len(self.prior_orders) == 0 and len(self.requested_orders) <= 1

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "trade_date": self.trade_date,
            "prior_orders": [dict(order) for order in self.prior_orders],
            "requested_orders": [dict(order) for order in self.requested_orders],
            "reason": "one_live_order_per_day_passed" if self.passed else "one_live_order_per_day_blocked",
        }


@dataclass(frozen=True)
class LivePostOrderLockoutReport:
    live_order_seen: bool
    monitor_passed: bool
    reconciliation_passed: bool
    daily_report_passed: bool

    @property
    def locked(self) -> bool:
        return self.live_order_seen and not (self.monitor_passed and self.reconciliation_passed and self.daily_report_passed)

    @property
    def passed(self) -> bool:
        return not self.locked

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "locked": self.locked,
            "live_order_seen": self.live_order_seen,
            "monitor_passed": self.monitor_passed,
            "reconciliation_passed": self.reconciliation_passed,
            "daily_report_passed": self.daily_report_passed,
        }


@dataclass(frozen=True)
class LivePaperParityReplayReport:
    live_result: Mapping[str, Any]
    paper_result: Mapping[str, Any]
    backtest_result: Mapping[str, Any]
    max_notional_diff: float = 1.0
    max_signal_diff: int = 0

    @property
    def notional_diff(self) -> float:
        return abs(float(self.live_result.get("notional", 0.0) or 0.0) - float(self.paper_result.get("notional", 0.0) or 0.0))

    @property
    def signal_diff(self) -> int:
        values = (
            str(self.live_result.get("signal", "")),
            str(self.paper_result.get("signal", "")),
            str(self.backtest_result.get("signal", "")),
        )
        return len(set(values)) - 1

    @property
    def passed(self) -> bool:
        return self.notional_diff <= self.max_notional_diff and self.signal_diff <= self.max_signal_diff

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "live_result": dict(self.live_result),
            "paper_result": dict(self.paper_result),
            "backtest_result": dict(self.backtest_result),
            "notional_diff": self.notional_diff,
            "signal_diff": self.signal_diff,
            "max_notional_diff": self.max_notional_diff,
            "max_signal_diff": self.max_signal_diff,
        }


def build_live_broker_adapter_boundary_report(
    paper_endpoint: str = PAPER_ENDPOINT,
    live_endpoint: str = LIVE_ENDPOINT,
    account_id: str = "",
    approved_account_ids: Sequence[str] = (),
    shared_submit_defaults: bool = False,
    live_submit_default_enabled: bool = False,
) -> LiveBrokerAdapterBoundaryReport:
    return LiveBrokerAdapterBoundaryReport(
        paper_endpoint,
        live_endpoint,
        _fingerprint(account_id),
        tuple(_fingerprint(value) for value in approved_account_ids),
        shared_submit_defaults,
        live_submit_default_enabled,
    )


def build_live_order_preview_report(
    orders: Sequence[Mapping[str, Any]],
    risk_settings: Mapping[str, Any],
    refused_to_submit: bool = True,
) -> LiveOrderPreviewReport:
    return LiveOrderPreviewReport(tuple(dict(order) for order in orders), dict(risk_settings), refused_to_submit)


def build_live_micro_trade_proof_report(symbol: str, planned_notional: float, operator_approved: bool, submitted: bool = False, monitor_artifact: str | None = None) -> LiveMicroTradeProofReport:
    return LiveMicroTradeProofReport(symbol.upper(), planned_notional, operator_approved, submitted, monitor_artifact)


def build_live_account_monitor_report(expected_positions: Sequence[Mapping[str, Any]], broker_positions: Sequence[Mapping[str, Any]], tolerance_quantity: float = 0.000001) -> LiveAccountMonitorReport:
    return LiveAccountMonitorReport(tuple(dict(row) for row in expected_positions), tuple(dict(row) for row in broker_positions), tolerance_quantity)


def build_live_order_lifecycle_reconciliation_report(lifecycle_events: Sequence[Mapping[str, Any]]) -> LiveOrderLifecycleReconciliationReport:
    return LiveOrderLifecycleReconciliationReport(tuple(dict(event) for event in lifecycle_events))


def build_live_position_flatten_plan_report(positions: Sequence[Mapping[str, Any]], operator_approved: bool = False, emergency_path: str | None = None) -> LivePositionFlattenPlanReport:
    return LivePositionFlattenPlanReport(tuple(dict(row) for row in positions), operator_approved, emergency_path)


def build_live_readiness_validation_evidence_report(evidence: Sequence[Mapping[str, Any]]) -> LiveReadinessValidationEvidenceReport:
    return LiveReadinessValidationEvidenceReport(tuple(dict(row) for row in evidence))


def build_live_release_bundle_report(paper_soak_current: bool, deployment_proof_current: bool, monitor_proof_current: bool, risk_settings_current: bool, operator_approved: bool) -> LiveReleaseBundleReport:
    return LiveReleaseBundleReport(paper_soak_current, deployment_proof_current, monitor_proof_current, risk_settings_current, operator_approved)


def build_live_risk_cap_report(orders: Sequence[Mapping[str, Any]], caps: Mapping[str, Any], current_daily_notional: float = 0.0, current_daily_loss: float = 0.0, current_open_positions: int = 0, current_gross_exposure: float = 0.0) -> LiveRiskCapReport:
    return LiveRiskCapReport(tuple(dict(order) for order in orders), dict(caps), current_daily_notional, current_daily_loss, current_open_positions, current_gross_exposure)


def build_live_scheduler_mode_report(enabled: bool, mode: str = "manual", micro_proof_passed: bool = False) -> LiveSchedulerModeReport:
    return LiveSchedulerModeReport(enabled, mode, micro_proof_passed)


def build_live_command_confirmation_report(timestamp: str, account_id: str, strategy: str, notional: float, expected_order: Mapping[str, Any], risk_settings: Mapping[str, Any], operator_approved: bool) -> LiveCommandConfirmationReport:
    return LiveCommandConfirmationReport(timestamp, _fingerprint(account_id), strategy, notional, dict(expected_order), dict(risk_settings), operator_approved)


def build_one_live_order_per_day_report(trade_date: str, prior_orders: Sequence[Mapping[str, Any]], requested_orders: Sequence[Mapping[str, Any]]) -> OneLiveOrderPerDayReport:
    return OneLiveOrderPerDayReport(trade_date, tuple(dict(order) for order in prior_orders), tuple(dict(order) for order in requested_orders))


def build_live_post_order_lockout_report(live_order_seen: bool, monitor_passed: bool, reconciliation_passed: bool, daily_report_passed: bool) -> LivePostOrderLockoutReport:
    return LivePostOrderLockoutReport(live_order_seen, monitor_passed, reconciliation_passed, daily_report_passed)


def build_live_paper_parity_replay_report(live_result: Mapping[str, Any], paper_result: Mapping[str, Any], backtest_result: Mapping[str, Any], max_notional_diff: float = 1.0, max_signal_diff: int = 0) -> LivePaperParityReplayReport:
    return LivePaperParityReplayReport(dict(live_result), dict(paper_result), dict(backtest_result), max_notional_diff, max_signal_diff)


def write_live_readiness_report(report: Any, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return destination


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""


def _quantity(row: Mapping[str, Any]) -> float:
    try:
        return float(row.get("quantity", row.get("qty", 0.0)) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _notional(order: Mapping[str, Any]) -> float:
    try:
        if order.get("notional") is not None:
            return abs(float(order.get("notional") or 0.0))
        return abs(float(order.get("quantity", order.get("qty", 0.0)) or 0.0) * float(order.get("price", order.get("limit_price", 0.0)) or 0.0))
    except (TypeError, ValueError):
        return 0.0
