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
