from dataclasses import dataclass
from typing import Literal, Optional

SideLike = Literal["LONG", "SHORT", "BUY", "SELL"]


@dataclass(frozen=True)
class StopLossPolicy:
    """Builds stop prices from a known reference price."""

    fixed_percent: Optional[float] = None
    atr_multiple: Optional[float] = None

    def from_reference(self, side: SideLike, price: float, atr: Optional[float] = None) -> Optional[float]:
        if price <= 0:
            return None

        direction = 1 if side in ("LONG", "BUY") else -1
        if self.atr_multiple is not None and atr is not None:
            return price - direction * abs(atr) * self.atr_multiple
        if self.fixed_percent is not None:
            fraction = self.fixed_percent / 100 if self.fixed_percent > 1 else self.fixed_percent
            return price * (1 - direction * fraction)
        return None


@dataclass(frozen=True)
class ExitPlan:
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass(frozen=True)
class ExitOrderPolicy:
    """Builds initial stop-loss and take-profit levels from an entry price."""

    stop_loss: StopLossPolicy
    take_profit_percent: Optional[float] = None

    def from_entry(self, side: SideLike, entry_price: float, atr: Optional[float] = None) -> ExitPlan:
        stop = self.stop_loss.from_reference(side, entry_price, atr)
        take_profit = None
        if self.take_profit_percent is not None:
            fraction = self.take_profit_percent / 100 if self.take_profit_percent > 1 else self.take_profit_percent
            direction = 1 if side in ("LONG", "BUY") else -1
            take_profit = entry_price * (1 + direction * fraction)
        return ExitPlan(stop_loss=stop, take_profit=take_profit)


@dataclass
class TrailingStop:
    """Maintains a trailing stop without loosening it."""

    side: SideLike
    trail_percent: float
    stop: Optional[float] = None

    def update(self, price: float) -> Optional[float]:
        if price <= 0:
            return self.stop
        fraction = self.trail_percent / 100 if self.trail_percent > 1 else self.trail_percent
        if self.side in ("LONG", "BUY"):
            candidate = price * (1 - fraction)
            self.stop = candidate if self.stop is None else max(self.stop, candidate)
        else:
            candidate = price * (1 + fraction)
            self.stop = candidate if self.stop is None else min(self.stop, candidate)
        return self.stop
