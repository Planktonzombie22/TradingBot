from dataclasses import replace
from hashlib import sha256

from src.models import Order, OrderStatus


def mark_order(order: Order, status: OrderStatus) -> Order:
    """Return a copy of an order with an updated lifecycle status."""

    return replace(order, status=status)


def ensure_client_order_id(order: Order, namespace: str = "tradingbot") -> Order:
    """Return an order with a stable client order id for idempotent broker submits."""

    if order.client_order_id:
        return order
    raw = "|".join(
        [
            namespace,
            order.id,
            order.symbol,
            order.side,
            str(order.quantity),
            order.order_type,
            str(order.limit_price),
            str(order.stop_price),
        ]
    )
    digest = sha256(raw.encode("utf-8")).hexdigest()[:24]
    return replace(order, client_order_id=f"{namespace}-{digest}")
