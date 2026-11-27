from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from src.execution import Broker, BrokerAccountSnapshot, BrokerPositionSnapshot, BrokerReconciler, ExecutionReport
from src.models import Order


@dataclass(frozen=True)
class ValidationProbe:
    name: str
    passed: bool
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class AlpacaDataConnectivityReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class PaperOrderLifecycleReport:
    probes: tuple[ValidationProbe, ...]
    orders: tuple[Mapping[str, Any], ...] = ()
    reports: tuple[Mapping[str, Any], ...] = ()

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "probes": [probe.to_dict() for probe in self.probes],
            "orders": [dict(order) for order in self.orders],
            "reports": [dict(report) for report in self.reports],
        }


@dataclass(frozen=True)
class BrokerAccountParityReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class FailureInjectionScenario:
    name: str
    operation: Callable[[], Any]
    expected_exception: type[BaseException] | tuple[type[BaseException], ...] = Exception
    expected_message: str | None = None


@dataclass(frozen=True)
class FailureInjectionReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class BrokerStatementSnapshot:
    cash: float
    equity: float
    positions: Mapping[str, float] = field(default_factory=dict)
    fills: tuple[Mapping[str, Any], ...] = ()
    source: str = "broker_statement"

    def to_dict(self) -> dict:
        return {
            "cash": self.cash,
            "equity": self.equity,
            "positions": dict(self.positions),
            "fills": [dict(fill) for fill in self.fills],
            "source": self.source,
        }


@dataclass(frozen=True)
class BrokerStatementIngestionReport:
    probes: tuple[ValidationProbe, ...]
    statement: BrokerStatementSnapshot | None = None

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "statement": self.statement.to_dict() if self.statement else None,
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class AlpacaFillPollingReport:
    probes: tuple[ValidationProbe, ...]
    polled_reports: tuple[ExecutionReport, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "polled_reports": [_report_payload(report) for report in self.polled_reports],
            "probes": [probe.to_dict() for probe in self.probes],
        }


def evaluate_alpaca_data_connectivity(
    historical_loader: Callable[[], pd.DataFrame],
    latest_probe: Callable[[], Mapping[str, Any]] | None = None,
    websocket_probe: Callable[[], Mapping[str, Any]] | None = None,
    secondary_loader: Callable[[], pd.DataFrame] | None = None,
    min_rows: int = 1,
    max_close_drift_pct: float = 0.02,
) -> AlpacaDataConnectivityReport:
    probes: list[ValidationProbe] = []
    primary: pd.DataFrame | None = None
    try:
        primary = historical_loader()
        rows = len(primary)
        probes.append(
            ValidationProbe(
                "historical_bars",
                rows >= min_rows and _has_ohlcv(primary),
                "passed" if rows >= min_rows and _has_ohlcv(primary) else "historical_bars_invalid",
                {"rows": rows, "min_rows": min_rows, "columns": list(primary.columns)},
            )
        )
    except Exception as exc:
        probes.append(ValidationProbe("historical_bars", False, "historical_loader_failed", {"error": str(exc)}))

    if latest_probe is not None:
        probes.append(_call_probe("latest_market_data", latest_probe))
    if websocket_probe is not None:
        probes.append(_call_probe("websocket_stream", websocket_probe))
    if secondary_loader is not None and primary is not None and not primary.empty:
        try:
            secondary = secondary_loader()
            drift = _last_close_drift(primary, secondary)
            probes.append(
                ValidationProbe(
                    "secondary_provider_drift",
                    drift is not None and drift <= max_close_drift_pct,
                    "passed" if drift is not None and drift <= max_close_drift_pct else "close_drift_too_high",
                    {"close_drift_pct": drift, "max_close_drift_pct": max_close_drift_pct},
                )
            )
        except Exception as exc:
            probes.append(ValidationProbe("secondary_provider_drift", False, "secondary_loader_failed", {"error": str(exc)}))
    return AlpacaDataConnectivityReport(tuple(probes))


def evaluate_paper_order_lifecycle(
    broker: Broker,
    order: Order,
    replacement: Order | None = None,
) -> PaperOrderLifecycleReport:
    probes: list[ValidationProbe] = []
    submitted = broker.submit_order(order)
    duplicate = broker.submit_order(order)
    reports = tuple(broker.execution_reports())
    probes.append(
        ValidationProbe(
            "submit_acknowledged",
            submitted.status in {"PENDING", "FILLED", "REJECTED"},
            "passed" if submitted.status in {"PENDING", "FILLED", "REJECTED"} else "unexpected_submit_status",
            {"status": submitted.status, "order_id": submitted.id},
        )
    )
    probes.append(
        ValidationProbe(
            "duplicate_client_order_protected",
            duplicate.id == submitted.id,
            "passed" if duplicate.id == submitted.id else "duplicate_order_created",
            {"first_order_id": submitted.id, "duplicate_order_id": duplicate.id},
        )
    )
    probes.append(
        ValidationProbe(
            "execution_report_recorded",
            any(report.order_id == submitted.id for report in reports),
            "passed" if any(report.order_id == submitted.id for report in reports) else "missing_execution_report",
            {"reports": len(reports)},
        )
    )
    if replacement is not None:
        replaced = broker.replace_order(submitted.id, replacement)
        probes.append(
            ValidationProbe(
                "replace_acknowledged",
                replaced is not None,
                "passed" if replaced is not None else "replace_not_supported_or_missing_order",
                {"order_id": submitted.id},
            )
        )
    cancelled = broker.cancel_order(submitted.id)
    probes.append(
        ValidationProbe(
            "cancel_acknowledged",
            cancelled is not None and cancelled.status == "CANCELLED",
            "passed" if cancelled is not None and cancelled.status == "CANCELLED" else "cancel_failed",
            {"status": cancelled.status if cancelled else None},
        )
    )
    final_reports = tuple(broker.execution_reports())
    reconciliation = BrokerReconciler().reconcile_orders([cancelled or submitted], final_reports)
    probes.append(
        ValidationProbe(
            "reconciliation_clean",
            reconciliation.is_clean,
            "passed" if reconciliation.is_clean else "reconciliation_unresolved",
            {"unresolved": len(reconciliation.unresolved)},
        )
    )
    return PaperOrderLifecycleReport(
        tuple(probes),
        orders=tuple(_order_payload(order) for order in [submitted, duplicate, cancelled] if order is not None),
        reports=tuple(_report_payload(report) for report in final_reports),
    )


def evaluate_broker_account_parity(
    local_account: BrokerAccountSnapshot,
    broker_account: BrokerAccountSnapshot,
    local_positions: Sequence[BrokerPositionSnapshot] = (),
    broker_positions: Sequence[BrokerPositionSnapshot] = (),
    local_orders: Sequence[Order] = (),
    broker_orders: Sequence[Order] = (),
    local_reports: Sequence[ExecutionReport] = (),
    broker_reports: Sequence[ExecutionReport] = (),
    cash_tolerance: float = 0.01,
    equity_tolerance: float = 0.01,
) -> BrokerAccountParityReport:
    probes = [
        _numeric_parity("cash", local_account.cash, broker_account.cash, cash_tolerance),
        _numeric_parity("buying_power", local_account.buying_power, broker_account.buying_power, cash_tolerance),
        _numeric_parity("equity", local_account.equity, broker_account.equity, equity_tolerance),
        _symbol_quantity_parity("positions", local_positions, broker_positions),
        _order_set_parity("open_orders", local_orders, broker_orders),
        _report_set_parity("execution_reports", local_reports, broker_reports),
    ]
    return BrokerAccountParityReport(tuple(probes))


def ingest_broker_statement(payload: Mapping[str, Any]) -> BrokerStatementSnapshot:
    positions = payload.get("positions", {})
    if isinstance(positions, Sequence) and not isinstance(positions, (str, bytes, dict)):
        positions = {str(item.get("symbol", "")): float(item.get("quantity", item.get("qty", 0)) or 0) for item in positions}
    return BrokerStatementSnapshot(
        cash=float(payload.get("cash", 0) or 0),
        equity=float(payload.get("equity", 0) or 0),
        positions={str(symbol).upper(): float(quantity) for symbol, quantity in dict(positions).items()},
        fills=tuple(dict(fill) for fill in payload.get("fills", ())),
        source=str(payload.get("source", "broker_statement")),
    )


def evaluate_broker_statement_ingestion(
    statement_payload: Mapping[str, Any],
    local_account: BrokerAccountSnapshot | None = None,
    local_positions: Sequence[BrokerPositionSnapshot] = (),
    cash_tolerance: float = 0.01,
    equity_tolerance: float = 0.01,
) -> BrokerStatementIngestionReport:
    probes: list[ValidationProbe] = []
    try:
        statement = ingest_broker_statement(statement_payload)
    except Exception as exc:
        return BrokerStatementIngestionReport(
            (ValidationProbe("statement_parse", False, "broker_statement_parse_failed", {"error": str(exc)}),),
            None,
        )
    probes.append(
        ValidationProbe(
            "statement_parse",
            statement.equity >= 0 and statement.cash >= 0,
            "passed" if statement.equity >= 0 and statement.cash >= 0 else "negative_statement_values",
            {"statement": statement.to_dict()},
        )
    )
    if local_account is not None:
        probes.extend(
            [
                _numeric_parity("statement_cash", local_account.cash, statement.cash, cash_tolerance),
                _numeric_parity("statement_equity", local_account.equity, statement.equity, equity_tolerance),
                _statement_position_parity(local_positions, statement.positions),
            ]
        )
    return BrokerStatementIngestionReport(tuple(probes), statement)


def evaluate_real_alpaca_fill_polling(
    expected_orders: Sequence[Order],
    fill_poller: Callable[[], Sequence[ExecutionReport] | Sequence[Mapping[str, Any]]],
) -> AlpacaFillPollingReport:
    probes: list[ValidationProbe] = []
    try:
        raw_reports = tuple(fill_poller())
        reports = tuple(_coerce_execution_report(item) for item in raw_reports)
    except Exception as exc:
        return AlpacaFillPollingReport(
            (ValidationProbe("fill_polling", False, "fill_polling_failed", {"error": str(exc)}),),
            (),
        )
    expected_ids = {order.id for order in expected_orders}
    broker_ids = {order.client_order_id for order in expected_orders if order.client_order_id}
    report_order_ids = {report.order_id for report in reports}
    report_broker_ids = {report.broker_order_id for report in reports if report.broker_order_id}
    missing = sorted(expected_ids - report_order_ids)
    matched_by_broker = sorted(broker_ids & report_broker_ids)
    fill_statuses = {report.status for report in reports}
    probes.extend(
        [
            ValidationProbe("fill_polling", True, "passed", {"reports": len(reports)}),
            ValidationProbe(
                "expected_orders_reported",
                not missing or bool(matched_by_broker),
                "passed" if not missing or bool(matched_by_broker) else "missing_polled_fills",
                {"missing_order_ids": missing, "matched_broker_ids": matched_by_broker},
            ),
            ValidationProbe(
                "real_fill_status_present",
                bool(fill_statuses & {"FILLED", "PARTIAL", "CANCELLED", "REJECTED", "PENDING"}),
                "passed" if bool(fill_statuses & {"FILLED", "PARTIAL", "CANCELLED", "REJECTED", "PENDING"}) else "missing_known_fill_status",
                {"statuses": sorted(fill_statuses)},
            ),
        ]
    )
    return AlpacaFillPollingReport(tuple(probes), reports)


def evaluate_failure_injection(scenarios: Sequence[FailureInjectionScenario]) -> FailureInjectionReport:
    probes: list[ValidationProbe] = []
    for scenario in scenarios:
        try:
            scenario.operation()
        except scenario.expected_exception as exc:
            message_ok = scenario.expected_message is None or scenario.expected_message in str(exc)
            probes.append(
                ValidationProbe(
                    scenario.name,
                    message_ok,
                    "passed" if message_ok else "unexpected_exception_message",
                    {"exception": type(exc).__name__, "message": str(exc), "expected_message": scenario.expected_message},
                )
            )
        except Exception as exc:
            probes.append(
                ValidationProbe(
                    scenario.name,
                    False,
                    "unexpected_exception_type",
                    {"exception": type(exc).__name__, "message": str(exc)},
                )
            )
        else:
            probes.append(ValidationProbe(scenario.name, False, "expected_failure_did_not_occur", {}))
    return FailureInjectionReport(tuple(probes))


def _call_probe(name: str, probe: Callable[[], Mapping[str, Any]]) -> ValidationProbe:
    try:
        evidence = dict(probe())
        passed = bool(evidence.get("passed", True))
        return ValidationProbe(name, passed, "passed" if passed else str(evidence.get("reason", f"{name}_failed")), evidence)
    except Exception as exc:
        return ValidationProbe(name, False, f"{name}_failed", {"error": str(exc)})


def _has_ohlcv(data: pd.DataFrame) -> bool:
    return {"Open", "High", "Low", "Close", "Volume"} <= set(data.columns)


def _last_close_drift(primary: pd.DataFrame, secondary: pd.DataFrame) -> float | None:
    if primary.empty or secondary.empty or "Close" not in primary or "Close" not in secondary:
        return None
    first = float(primary["Close"].dropna().iloc[-1])
    second = float(secondary["Close"].dropna().iloc[-1])
    if second == 0:
        return None
    return abs(first - second) / abs(second)


def _numeric_parity(name: str, local: float, broker: float, tolerance: float) -> ValidationProbe:
    delta = abs(float(local) - float(broker))
    passed = delta <= tolerance
    return ValidationProbe(
        name,
        passed,
        "passed" if passed else f"{name}_mismatch",
        {"local": local, "broker": broker, "delta": delta, "tolerance": tolerance},
    )


def _symbol_quantity_parity(
    name: str,
    local_positions: Sequence[BrokerPositionSnapshot],
    broker_positions: Sequence[BrokerPositionSnapshot],
) -> ValidationProbe:
    local = {position.symbol: float(position.quantity) for position in local_positions}
    broker = {position.symbol: float(position.quantity) for position in broker_positions}
    passed = local == broker
    return ValidationProbe(name, passed, "passed" if passed else "position_mismatch", {"local": local, "broker": broker})


def _order_set_parity(name: str, local_orders: Sequence[Order], broker_orders: Sequence[Order]) -> ValidationProbe:
    local = sorted(order.client_order_id or order.id for order in local_orders)
    broker = sorted(order.client_order_id or order.id for order in broker_orders)
    passed = local == broker
    return ValidationProbe(name, passed, "passed" if passed else "open_order_mismatch", {"local": local, "broker": broker})


def _report_set_parity(
    name: str,
    local_reports: Sequence[ExecutionReport],
    broker_reports: Sequence[ExecutionReport],
) -> ValidationProbe:
    local = sorted(report.broker_order_id or report.order_id for report in local_reports)
    broker = sorted(report.broker_order_id or report.order_id for report in broker_reports)
    passed = local == broker
    return ValidationProbe(name, passed, "passed" if passed else "execution_report_mismatch", {"local": local, "broker": broker})


def _statement_position_parity(
    local_positions: Sequence[BrokerPositionSnapshot],
    statement_positions: Mapping[str, float],
) -> ValidationProbe:
    local = {position.symbol.upper(): float(position.quantity) for position in local_positions}
    statement = {symbol.upper(): float(quantity) for symbol, quantity in statement_positions.items()}
    passed = local == statement
    return ValidationProbe("statement_positions", passed, "passed" if passed else "statement_position_mismatch", {"local": local, "statement": statement})


def _order_payload(order: Order) -> dict:
    return {
        "id": order.id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "status": order.status,
    }


def _report_payload(report: ExecutionReport) -> dict:
    return {
        "order_id": report.order_id,
        "status": report.status,
        "broker_order_id": report.broker_order_id,
        "filled_quantity": report.filled_quantity,
        "average_fill_price": report.average_fill_price,
    }


def _coerce_execution_report(item: ExecutionReport | Mapping[str, Any]) -> ExecutionReport:
    if isinstance(item, ExecutionReport):
        return item
    return ExecutionReport(
        order_id=str(item.get("order_id", item.get("id", ""))),
        status=str(item.get("status", "")).upper(),
        broker_order_id=item.get("broker_order_id") or item.get("broker_id") or item.get("client_order_id"),
        filled_quantity=float(item.get("filled_quantity", item.get("filled_qty", 0)) or 0),
        average_fill_price=float(item.get("average_fill_price", item.get("filled_avg_price", 0)) or 0),
        raw=dict(item),
    )
