from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping

from src.engine import EngineState, PaperAccountState, RuntimeRiskMonitor
from src.execution import Broker, ExecutionReport


@dataclass(frozen=True)
class DashboardSnapshot:
    timestamp: datetime
    engine_state: str
    account: Dict[str, Any]
    open_orders: list[Dict[str, Any]]
    recent_fills: list[Dict[str, Any]]
    risk_halt: Dict[str, Any]
    health: Dict[str, Any] = field(default_factory=dict)


def build_dashboard_snapshot(
    engine_state: EngineState | str,
    account_state: PaperAccountState,
    broker: Broker,
    prices: Mapping[str, float],
    risk_monitor: RuntimeRiskMonitor | None = None,
    health: Mapping[str, Any] | None = None,
) -> DashboardSnapshot:
    reports = list(broker.execution_reports())
    return DashboardSnapshot(
        timestamp=datetime.now(timezone.utc),
        engine_state=engine_state.value if hasattr(engine_state, "value") else str(engine_state),
        account=account_state.snapshot(dict(prices)),
        open_orders=[_order_payload(order) for order in broker.open_orders()],
        recent_fills=[_report_payload(report) for report in reports if report.filled_quantity > 0],
        risk_halt={
            "halted": bool(risk_monitor.halted) if risk_monitor else False,
            "reason": risk_monitor.halt_reason if risk_monitor else None,
        },
        health=dict(health or {}),
    )


def _order_payload(order) -> Dict[str, Any]:
    return {
        "id": order.id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "status": order.status,
    }


def _report_payload(report: ExecutionReport) -> Dict[str, Any]:
    return {
        "order_id": report.order_id,
        "broker_order_id": report.broker_order_id,
        "status": report.status,
        "filled_quantity": report.filled_quantity,
        "average_fill_price": report.average_fill_price,
    }
