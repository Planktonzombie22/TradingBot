from dataclasses import dataclass

from src.models import Order

from ..core.interfaces import CommissionModel, ExecutionModel, ExecutionOutcome, LiquidityModel, SlippageModel
from ..core.types import AccountSnapshot, Fill, MarketSnapshot, OrderRejection, RejectionReason


@dataclass(frozen=True)
class BarExecutionModel(ExecutionModel):
    """Executes orders against an OHLCV bar using pluggable market assumptions."""

    slippage_model: SlippageModel
    commission_model: CommissionModel
    liquidity_model: LiquidityModel
    price_column: str = "Close"

    def execute(self, order: Order, snapshot: MarketSnapshot, account: AccountSnapshot) -> ExecutionOutcome:
        if not self._is_triggered(order, snapshot):
            return OrderRejection(
                order=order,
                timestamp=snapshot.timestamp,
                reason=RejectionReason.NOT_TRIGGERED,
                message="Limit or stop condition was not touched by this bar.",
            )

        quantity = self.liquidity_model.fillable_quantity(order, snapshot)
        if quantity <= 0:
            return OrderRejection(
                order=order,
                timestamp=snapshot.timestamp,
                reason=RejectionReason.NOT_TRIGGERED,
                message="Liquidity model produced no fillable quantity.",
            )

        reference_price = self._reference_price(order, snapshot)
        fill_price = self.slippage_model.apply(order, snapshot, reference_price)
        commission = self.commission_model.calculate(order, fill_price, quantity)
        return Fill(
            order=order,
            timestamp=snapshot.timestamp,
            quantity=quantity,
            price=fill_price,
            commission=commission,
            slippage=fill_price - reference_price,
            liquidity_fraction=quantity / order.quantity if order.quantity else 0.0,
        )

    def _reference_price(self, order: Order, snapshot: MarketSnapshot) -> float:
        if order.order_type == "LIMIT" and order.limit_price is not None:
            return order.limit_price
        if order.order_type == "STOP" and order.stop_price is not None:
            return order.stop_price
        return snapshot.price(self.price_column)

    @staticmethod
    def _is_triggered(order: Order, snapshot: MarketSnapshot) -> bool:
        if order.order_type == "MARKET":
            return True
        if order.order_type == "LIMIT" and order.limit_price is not None:
            return snapshot.low <= order.limit_price if order.side == "BUY" else snapshot.high >= order.limit_price
        if order.order_type == "STOP" and order.stop_price is not None:
            return snapshot.high >= order.stop_price if order.side == "BUY" else snapshot.low <= order.stop_price
        return False
