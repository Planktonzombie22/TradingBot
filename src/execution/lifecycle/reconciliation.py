from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from src.models import Order


@dataclass(frozen=True)
class ExecutionReport:
    """Broker-facing order lifecycle record."""

    order_id: str
    status: str
    broker_order_id: Optional[str] = None
    fill_id: str = field(default_factory=lambda: str(uuid4()))
    filled_quantity: float = 0.0
    average_fill_price: Optional[float] = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_order(cls, order: Order, broker_order_id: Optional[str] = None, raw: Optional[dict] = None) -> "ExecutionReport":
        return cls(
            order_id=order.id,
            status=order.status,
            broker_order_id=broker_order_id,
            filled_quantity=order.quantity if order.status == "FILLED" else 0.0,
            raw=raw or {},
        )


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    symbol: str
    quantity: float
    average_entry_price: float = 0.0
    market_value: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    cash: float
    buying_power: float
    equity: float
    daytrade_count: int = 0
    pattern_day_trader: bool = False
    trading_blocked: bool = False
    account_blocked: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class BrokerSyncSnapshot:
    account: BrokerAccountSnapshot
    positions: List[BrokerPositionSnapshot] = field(default_factory=list)
    open_orders: List[Order] = field(default_factory=list)
    reports: List[ExecutionReport] = field(default_factory=list)
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    LOCAL_ONLY = "LOCAL_ONLY"
    BROKER_ONLY = "BROKER_ONLY"
    STATUS_MISMATCH = "STATUS_MISMATCH"


@dataclass(frozen=True)
class OrderReconciliation:
    order_id: str
    status: ReconciliationStatus
    local_status: Optional[str] = None
    broker_status: Optional[str] = None
    broker_order_id: Optional[str] = None
    message: str = ""


@dataclass(frozen=True)
class ReconciliationResult:
    orders: List[OrderReconciliation]
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def unresolved(self) -> List[OrderReconciliation]:
        return [item for item in self.orders if item.status != ReconciliationStatus.MATCHED]

    @property
    def is_clean(self) -> bool:
        return not self.unresolved


class BrokerReconciler:
    """Compare local order state with the latest broker lifecycle records."""

    def reconcile_orders(
        self,
        local_orders: Iterable[Order],
        broker_reports: Iterable[ExecutionReport],
    ) -> ReconciliationResult:
        local_by_id = {order.id: order for order in local_orders}
        reports_by_order_id = {report.order_id: report for report in broker_reports}
        reconciliations: List[OrderReconciliation] = []

        for order_id, order in sorted(local_by_id.items()):
            report = reports_by_order_id.get(order_id)
            if report is None:
                reconciliations.append(
                    OrderReconciliation(
                        order_id=order_id,
                        status=ReconciliationStatus.LOCAL_ONLY,
                        local_status=order.status,
                        message="Local order has no broker execution report.",
                    )
                )
                continue
            if report.status != order.status:
                reconciliations.append(
                    OrderReconciliation(
                        order_id=order_id,
                        status=ReconciliationStatus.STATUS_MISMATCH,
                        local_status=order.status,
                        broker_status=report.status,
                        broker_order_id=report.broker_order_id,
                        message="Local order status differs from broker report.",
                    )
                )
                continue
            reconciliations.append(
                OrderReconciliation(
                    order_id=order_id,
                    status=ReconciliationStatus.MATCHED,
                    local_status=order.status,
                    broker_status=report.status,
                    broker_order_id=report.broker_order_id,
                )
            )

        for order_id, report in sorted(reports_by_order_id.items()):
            if order_id not in local_by_id:
                reconciliations.append(
                    OrderReconciliation(
                        order_id=order_id,
                        status=ReconciliationStatus.BROKER_ONLY,
                        broker_status=report.status,
                        broker_order_id=report.broker_order_id,
                        message="Broker report has no matching local order.",
                    )
                )

        return ReconciliationResult(reconciliations)
