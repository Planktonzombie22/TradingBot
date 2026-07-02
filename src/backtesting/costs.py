from dataclasses import dataclass
from typing import Optional

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
class SpreadVolumeSlippageModel(SlippageModel):
    """Combines a fixed spread estimate with volume participation impact."""

    spread_bps: float = 1.0
    impact_bps_per_volume_share: float = 10.0

    def apply(self, order: Order, snapshot: MarketSnapshot, reference_price: float) -> float:
        direction = 1 if order.side == "BUY" else -1
        volume_share = 0.0
        if snapshot.volume:
            volume_share = min(abs(order.quantity) / snapshot.volume, 1.0)
        slippage_bps = self.spread_bps / 2 + self.impact_bps_per_volume_share * volume_share
        return reference_price * (1 + direction * slippage_bps / 10_000)


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


@dataclass(frozen=True)
class AnnualizedBorrowCostModel(BorrowCostModel):
    """Accrues short borrow cost from annualized borrow rate."""

    annual_rate: float = 0.03
    periods_per_year: int = 252
    hard_to_borrow_symbols: Optional[set[str]] = None

    def accrue(self, account: AccountSnapshot, snapshot: MarketSnapshot) -> float:
        quantity = account.positions.get(snapshot.symbol, 0.0)
        if quantity >= 0:
            return 0.0
        if self.hard_to_borrow_symbols and snapshot.symbol in self.hard_to_borrow_symbols:
            rate = self.annual_rate * 2
        else:
            rate = self.annual_rate
        notional = abs(quantity) * snapshot.close
        return notional * rate / self.periods_per_year


def commission_model_for_broker(name: str) -> CommissionModel:
    broker = name.lower()
    if broker in {"alpaca", "robinhood"}:
        return ZeroCommissionModel()
    if broker in {"interactive_brokers", "ibkr"}:
        return BpsCommissionModel(basis_points=0.5, minimum=1.0)
    if broker in {"generic"}:
        return BpsCommissionModel(basis_points=1.0, minimum=0.0)
    raise ValueError(f"Unknown broker commission preset: {name}")
