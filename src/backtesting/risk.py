from dataclasses import dataclass
from typing import Optional, Set

from src.models import Order

from .interfaces import RiskModel
from .margin import SimpleMarginModel
from .types import AccountSnapshot, MarketSnapshot, OrderRejection, RejectionReason


@dataclass(frozen=True)
class CompositeRiskModel(RiskModel):
    """Default pre-trade checks for cash, margin, order shape, and shorting."""

    margin_model: SimpleMarginModel
    allow_shorting: bool = True
    shortable_symbols: Optional[Set[str]] = None
    price_column: str = "Close"

    def evaluate(self, order: Order, account: AccountSnapshot, snapshot: MarketSnapshot) -> Optional[OrderRejection]:
        if order.quantity <= 0:
            return self._reject(order, snapshot, RejectionReason.INVALID_ORDER, "Order quantity must be positive.")

        if order.side == "SELL" and not self.allow_shorting:
            held_quantity = account.positions.get(order.symbol, 0.0)
            if held_quantity < order.quantity:
                return self._reject(order, snapshot, RejectionReason.RISK_LIMIT, "Shorting is disabled.")

        if order.side == "SELL" and self.shortable_symbols is not None:
            held_quantity = account.positions.get(order.symbol, 0.0)
            opens_or_increases_short = held_quantity <= 0
            if opens_or_increases_short and order.symbol not in self.shortable_symbols:
                return self._reject(order, snapshot, RejectionReason.RISK_LIMIT, "Short locate unavailable.")

        if self._reduces_existing_exposure(order, account):
            return None

        margin_required = self.margin_model.required_initial_margin(order, snapshot.price(self.price_column))
        available_margin = max(account.equity - account.used_margin, 0.0)
        if margin_required > available_margin:
            return self._reject(
                order,
                snapshot,
                RejectionReason.INSUFFICIENT_MARGIN,
                "Order exceeds available buying power.",
                {"required_margin": margin_required, "available_margin": available_margin},
            )
        return None

    @staticmethod
    def _reduces_existing_exposure(order: Order, account: AccountSnapshot) -> bool:
        held_quantity = account.positions.get(order.symbol, 0.0)
        if held_quantity > 0 and order.side == "SELL":
            return order.quantity <= abs(held_quantity)
        if held_quantity < 0 and order.side == "BUY":
            return order.quantity <= abs(held_quantity)
        return False

    @staticmethod
    def _reject(
        order: Order,
        snapshot: MarketSnapshot,
        reason: RejectionReason,
        message: str,
        metadata: Optional[dict] = None,
    ) -> OrderRejection:
        return OrderRejection(
            order=order,
            timestamp=snapshot.timestamp,
            reason=reason,
            message=message,
            metadata=metadata or {},
        )
