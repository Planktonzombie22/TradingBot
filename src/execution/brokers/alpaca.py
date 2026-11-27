from datetime import datetime, timezone
from typing import Iterable, Optional

from src.config import AlpacaConfig
from src.models import Order
from src.utils.alpaca_rest import AlpacaRestClient

from .base import Broker
from ..lifecycle.reconciliation import BrokerAccountSnapshot, BrokerPositionSnapshot, ExecutionReport
from ..orders.ids import ensure_client_order_id, mark_order


class AlpacaPaperBroker(Broker):
    """Minimal Alpaca Trading REST broker for paper orders."""

    def __init__(self, config: AlpacaConfig):
        self.config = config
        self.client = AlpacaRestClient(config)
        self.orders: dict[str, Order] = {}
        self.reports: dict[str, ExecutionReport] = {}

    def submit_order(self, order: Order) -> Order:
        self._validate_credentials()
        order = ensure_client_order_id(order)
        duplicate = self._order_by_client_id(order.client_order_id)
        if duplicate is not None:
            return duplicate
        payload = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.lower(),
            "type": order.order_type.lower(),
            "time_in_force": "day",
            "client_order_id": order.client_order_id,
        }
        if order.limit_price is not None:
            payload["limit_price"] = str(order.limit_price)
        if order.stop_price is not None:
            payload["stop_price"] = str(order.stop_price)

        raw = self._request("POST", "/v2/orders", payload)
        status = _alpaca_status_to_order_status(raw.get("status", "accepted"))
        submitted = mark_order(order, status)
        self.orders[submitted.id] = submitted
        self.reports[submitted.id] = ExecutionReport.from_order(
            submitted,
            broker_order_id=raw.get("id"),
            raw=raw,
        )
        return submitted

    def cancel_order(self, order_id: str) -> Optional[Order]:
        order = self.orders.get(order_id)
        if order is None:
            return None
        report = self.reports.get(order_id)
        if report and report.broker_order_id:
            self._request("DELETE", f"/v2/orders/{report.broker_order_id}", None)
        cancelled = mark_order(order, "CANCELLED")
        self.orders[order_id] = cancelled
        self.reports[order_id] = ExecutionReport.from_order(
            cancelled,
            broker_order_id=report.broker_order_id if report else None,
        )
        return cancelled

    def replace_order(self, order_id: str, replacement: Order) -> Optional[Order]:
        existing = self.orders.get(order_id)
        if existing is None:
            return None
        report = self.reports.get(order_id)
        if report is None or report.broker_order_id is None:
            return None
        payload = {
            "qty": str(replacement.quantity),
            "time_in_force": "day",
        }
        if replacement.limit_price is not None:
            payload["limit_price"] = str(replacement.limit_price)
        if replacement.stop_price is not None:
            payload["stop_price"] = str(replacement.stop_price)
        raw = self._request("PATCH", f"/v2/orders/{report.broker_order_id}", payload)
        replacement.id = order_id
        updated = mark_order(replacement, _alpaca_status_to_order_status(raw.get("status", "accepted")))
        self.orders[order_id] = updated
        self.reports[order_id] = ExecutionReport.from_order(updated, broker_order_id=raw.get("id", report.broker_order_id), raw=raw)
        return updated

    def open_orders(self) -> Iterable[Order]:
        self._validate_credentials()
        raw_orders = self._request("GET", "/v2/orders?status=open", None)
        if isinstance(raw_orders, list):
            orders = tuple(_order_from_alpaca_order(raw) for raw in raw_orders)
            self.orders.update({order.id: order for order in orders})
            self.reports.update(
                {
                    order.id: ExecutionReport.from_order(order, broker_order_id=raw.get("id"), raw=raw)
                    for order, raw in zip(orders, raw_orders)
                }
            )
            return orders
        return [order for order in self.orders.values() if order.status == "PENDING"]

    def account_snapshot(self) -> BrokerAccountSnapshot:
        self._validate_credentials()
        raw = self._request("GET", "/v2/account", None)
        return BrokerAccountSnapshot(
            cash=float(raw.get("cash", 0) or 0),
            buying_power=float(raw.get("buying_power", 0) or 0),
            equity=float(raw.get("equity", 0) or 0),
            daytrade_count=int(raw.get("daytrade_count", 0) or 0),
            pattern_day_trader=bool(raw.get("pattern_day_trader", False)),
            trading_blocked=bool(raw.get("trading_blocked", False)),
            account_blocked=bool(raw.get("account_blocked", False)),
            raw=raw,
        )

    def positions(self) -> Iterable[BrokerPositionSnapshot]:
        self._validate_credentials()
        raw_positions = self._request("GET", "/v2/positions", None)
        return [
            BrokerPositionSnapshot(
                symbol=str(item.get("symbol", "")),
                quantity=float(item.get("qty", 0) or 0),
                average_entry_price=float(item.get("avg_entry_price", 0) or 0),
                market_value=float(item.get("market_value", 0) or 0),
                raw=item,
            )
            for item in raw_positions
        ]

    def execution_reports(self) -> Iterable[ExecutionReport]:
        return list(self.reports.values())

    def poll_execution_reports(self, orders: Iterable[Order]) -> Iterable[ExecutionReport]:
        """Refresh local execution reports from Alpaca Trading REST order state."""

        self._validate_credentials()
        polled: list[ExecutionReport] = []
        for order in orders:
            existing = self.reports.get(order.id)
            if existing is None or existing.broker_order_id is None:
                continue
            raw = self._request("GET", f"/v2/orders/{existing.broker_order_id}", None)
            status = _alpaca_status_to_order_status(str(raw.get("status", "accepted")))
            updated = mark_order(self.orders.get(order.id, order), status)
            self.orders[updated.id] = updated
            report = _execution_report_from_alpaca_order(updated, raw, existing.broker_order_id)
            self.reports[updated.id] = report
            polled.append(report)
        return polled

    def _request(self, method: str, path: str, payload: Optional[dict]) -> dict:
        return self.client.request(method, f"{self.config.base_url}{path}", payload)

    def _validate_credentials(self) -> None:
        if not self.config.api_key or not self.config.secret_key:
            raise ValueError("Alpaca API credentials are missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env.")

    def _order_by_client_id(self, client_order_id: Optional[str]) -> Optional[Order]:
        if not client_order_id:
            return None
        for order in self.orders.values():
            if order.client_order_id == client_order_id:
                return order
        return None


def _alpaca_status_to_order_status(status: str) -> str:
    if status in {"filled"}:
        return "FILLED"
    if status in {"canceled", "expired"}:
        return "CANCELLED"
    if status in {"rejected"}:
        return "REJECTED"
    return "PENDING"


def _execution_report_from_alpaca_order(order: Order, raw: dict, fallback_broker_order_id: str | None) -> ExecutionReport:
    return ExecutionReport(
        order_id=order.id,
        status=order.status,
        broker_order_id=raw.get("id") or fallback_broker_order_id,
        filled_quantity=float(raw.get("filled_qty", 0) or 0),
        average_fill_price=_optional_float(raw.get("filled_avg_price")),
        raw=raw,
    )


def _optional_float(value) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _order_from_alpaca_order(raw: dict) -> Order:
    side = str(raw.get("side") or "buy").upper()
    order_type = str(raw.get("type") or "market").upper()
    created_at = _optional_datetime(raw.get("created_at")) or datetime.now(timezone.utc)
    return Order(
        symbol=str(raw.get("symbol") or "").upper(),
        side="BUY" if side == "BUY" else "SELL",
        quantity=float(raw.get("qty") or 0.0),
        order_type=order_type,
        limit_price=_optional_float(raw.get("limit_price")),
        stop_price=_optional_float(raw.get("stop_price")),
        time_in_force=str(raw.get("time_in_force") or "day"),
        status=_alpaca_status_to_order_status(str(raw.get("status") or "accepted")),
        created_at=created_at,
        id=str(raw.get("client_order_id") or raw.get("id") or ""),
        client_order_id=raw.get("client_order_id"),
    )


def _optional_datetime(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
