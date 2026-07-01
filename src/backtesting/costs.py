from dataclasses import dataclass

from src.models import Order

from .interfaces import BorrowCostModel, CommissionModel, LiquidityModel, SlippageModel
from .types import AccountSnapshot, MarketSnapshot


@dataclass(frozen=True)
class ZeroCommissionModel(CommissionModel):
    """No explicit commission or exchange fees."""

    def calculate(self, order: Order, fill_price: float, fill_quantity: float) -> float:
        return 0.0


@dataclass(frozen=True)
class BpsCommissionModel(CommissionModel):
    """Charges a basis-point fee on filled notional."""

    basis_points: float
    minimum: float = 0.0

    def calculate(self, order: Order, fill_price: float, fill_quantity: float) -> float:
        fee = abs(fill_price * fill_quantity) * (self.basis_points / 10_000)
        return max(fee, self.minimum)


@dataclass(frozen=True)
class NoSlippageModel(SlippageModel):
    """Fills at the reference price."""

    def apply(self, order: Order, snapshot: MarketSnapshot, reference_price: float) -> float:
        return reference_price


@dataclass(frozen=True)
class FixedBpsSlippageModel(SlippageModel):
    """Applies directional basis-point slippage to the reference price."""

    basis_points: float

    def apply(self, order: Order, snapshot: MarketSnapshot, reference_price: float) -> float:
        direction = 1 if order.side == "BUY" else -1
        return reference_price * (1 + direction * self.basis_points / 10_000)


@dataclass(frozen=True)
class UnlimitedLiquidityModel(LiquidityModel):
    """Assumes every valid order can fully fill on the bar."""

    def fillable_quantity(self, order: Order, snapshot: MarketSnapshot) -> float:
        return order.quantity


@dataclass(frozen=True)
class VolumeShareLiquidityModel(LiquidityModel):
    """Caps fills to a fraction of bar volume when volume is available."""

    max_volume_share: float = 0.10

    def fillable_quantity(self, order: Order, snapshot: MarketSnapshot) -> float:
        if snapshot.volume is None:
            return order.quantity
        cap = max(snapshot.volume * self.max_volume_share, 0.0)
        return min(order.quantity, cap)


@dataclass(frozen=True)
class NoBorrowCostModel(BorrowCostModel):
    """Placeholder for short borrow fees and locate failures."""

    def accrue(self, account: AccountSnapshot, snapshot: MarketSnapshot) -> float:
        return 0.0
