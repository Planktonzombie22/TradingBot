from dataclasses import replace

from src.models import Order, OrderStatus


def mark_order(order: Order, status: OrderStatus) -> Order:
    """Return a copy of an order with an updated lifecycle status."""

    return replace(order, status=status)
