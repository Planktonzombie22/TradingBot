from dataclasses import dataclass, field
from typing import List, Optional

from src.models import Order, Signal

from .position_sizing import PositionSizer, PositionSizingRequest


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reason: Optional[str] = None
    order: Optional[Order] = None


@dataclass
class RiskManager:
    """Strategy-agnostic risk gateway for order creation and validation."""

    sizer: PositionSizer = field(default_factory=PositionSizer)
    max_order_notional: Optional[float] = None
    allow_shorting: bool = True

    def order_from_signal(
        self,
        signal: Signal,
        equity: float,
        price: float,
        risk_fraction: float,
        buying_power: Optional[float] = None,
    ) -> RiskDecision:
        if signal.action == "HOLD":
            return RiskDecision(False, "No order for HOLD signal.")
        if signal.action == "CLOSE":
            return RiskDecision(False, "Close signals require current position context.")
        if signal.action == "SELL" and not self.allow_shorting:
            return RiskDecision(False, "Shorting is disabled.")

        if signal.stop_loss is None:
            target_fraction = signal.meta.get("target_notional_fraction")
            if target_fraction is None:
                return RiskDecision(False, "Signal requires a stop loss or target notional fraction.")
            target_notional = max(equity, 0.0) * float(target_fraction)
            if buying_power is not None:
                target_notional = min(target_notional, max(buying_power, 0.0))
            quantity = target_notional / price if price > 0 else 0.0
        else:
            quantity = self.sizer.size_from_stop(
                PositionSizingRequest(
                    equity=equity,
                    entry_price=price,
                    stop_price=signal.stop_loss,
                    risk_fraction=risk_fraction,
                    buying_power=buying_power,
                )
            )
        if quantity <= 0:
            return RiskDecision(False, "Risk model produced zero quantity.")

        notional = quantity * price
        if self.max_order_notional is not None and notional > self.max_order_notional:
            quantity = self.max_order_notional / price

        return RiskDecision(True, order=Order(symbol=signal.symbol, side=signal.action, quantity=quantity, stop_price=signal.stop_loss))

    def validate_batch(self, orders: List[Order]) -> List[RiskDecision]:
        return [self._validate_order(order) for order in orders]

    def _validate_order(self, order: Order) -> RiskDecision:
        if order.quantity <= 0:
            return RiskDecision(False, "Order quantity must be positive.", order)
        if order.side == "SELL" and not self.allow_shorting:
            return RiskDecision(False, "Shorting is disabled.", order)
        return RiskDecision(True, order=order)
