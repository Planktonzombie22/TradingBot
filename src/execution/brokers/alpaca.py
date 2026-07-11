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
