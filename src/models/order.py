from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT", "TRAILING_STOP"]
OrderStatus = Literal["PENDING", "FILLED", "CANCELLED", "REJECTED"]


@dataclass
class Order:
    """Request sent to a broker or execution layer."""

    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = "MARKET"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trail_percent: Optional[float] = None
    time_in_force: str = "day"
    parent_order_id: Optional[str] = None
    order_group_id: Optional[str] = None
    status: OrderStatus = "PENDING"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid4()))
    client_order_id: Optional[str] = None
