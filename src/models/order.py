from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "STOP"]
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
    status: OrderStatus = "PENDING"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
