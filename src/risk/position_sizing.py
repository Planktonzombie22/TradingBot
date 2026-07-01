from dataclasses import dataclass
from math import floor
from typing import Optional


@dataclass(frozen=True)
class PositionSizingRequest:
    equity: float
    entry_price: float
    stop_price: Optional[float]
    risk_fraction: float
    buying_power: Optional[float] = None
    allow_fractional: bool = True


@dataclass(frozen=True)
class PositionSizer:
    """Converts account risk into a position quantity."""

    def size_from_stop(self, request: PositionSizingRequest) -> float:
        if request.stop_price is None:
            return 0.0

        stop_distance = abs(request.entry_price - request.stop_price)
        if stop_distance <= 0 or request.entry_price <= 0:
            return 0.0

        risk_fraction = request.risk_fraction / 100 if request.risk_fraction > 1 else request.risk_fraction
        risk_budget = max(request.equity, 0.0) * risk_fraction
        quantity = risk_budget / stop_distance

        if request.buying_power is not None:
            quantity = min(quantity, max(request.buying_power, 0.0) / request.entry_price)

        if not request.allow_fractional:
            quantity = floor(quantity)
        return max(quantity, 0.0)
