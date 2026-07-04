from dataclasses import dataclass
from typing import Iterable, Optional

from .costs import SpreadVolumeSlippageModel


@dataclass(frozen=True)
class FillObservation:
    symbol: str
    side: str
    expected_price: float
    fill_price: float
    quantity: float
    quoted_bid: Optional[float] = None
    quoted_ask: Optional[float] = None
    bar_volume: Optional[float] = None

    @property
    def realized_slippage_bps(self) -> float:
        direction = 1 if self.side == "BUY" else -1
        return direction * (self.fill_price / self.expected_price - 1) * 10_000

    @property
    def spread_bps(self) -> Optional[float]:
        if self.quoted_bid is None or self.quoted_ask is None:
            return None
        midpoint = (self.quoted_bid + self.quoted_ask) / 2
        if midpoint <= 0:
            return None
        return (self.quoted_ask - self.quoted_bid) / midpoint * 10_000

    @property
    def volume_share(self) -> Optional[float]:
        if not self.bar_volume or self.bar_volume <= 0:
            return None
        return min(abs(self.quantity) / self.bar_volume, 1.0)


@dataclass(frozen=True)
class TransactionCostCalibration:
    spread_bps: float
    impact_bps_per_volume_share: float
    observations: int

    @classmethod
    def from_observations(cls, observations: Iterable[FillObservation]) -> "TransactionCostCalibration":
        items = list(observations)
        if not items:
            return cls(spread_bps=0.0, impact_bps_per_volume_share=0.0, observations=0)

        spread_values = [item.spread_bps for item in items if item.spread_bps is not None]
        spread_bps = sum(spread_values) / len(spread_values) if spread_values else 0.0

        residuals = []
        for item in items:
            volume_share = item.volume_share
            if volume_share is None or volume_share <= 0:
                continue
            residual = max(item.realized_slippage_bps - spread_bps / 2, 0.0)
            residuals.append(residual / volume_share)
        impact = sum(residuals) / len(residuals) if residuals else 0.0
        return cls(spread_bps=spread_bps, impact_bps_per_volume_share=impact, observations=len(items))

    def to_slippage_model(self) -> SpreadVolumeSlippageModel:
        return SpreadVolumeSlippageModel(
            spread_bps=self.spread_bps,
            impact_bps_per_volume_share=self.impact_bps_per_volume_share,
        )
