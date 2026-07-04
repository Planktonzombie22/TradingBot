from dataclasses import dataclass
from typing import Literal

from .costs import (
    BpsCommissionModel,
    NoSlippageModel,
    SpreadVolumeSlippageModel,
    UnlimitedLiquidityModel,
    VolumeShareLiquidityModel,
    ZeroCommissionModel,
)
from .execution import BarExecutionModel

FillTiming = Literal["same_bar", "next_bar"]


@dataclass(frozen=True)
class BacktestExecutionProfile:
    """Named execution assumptions that can be aligned with paper fills."""

    name: str = "paper-like"
    fill_timing: FillTiming = "same_bar"
    price_column: str = "Close"
    spread_bps: float = 0.0
    impact_bps_per_volume_share: float = 0.0
    max_volume_share: float = 1.0
    commission_bps: float = 0.0
    minimum_commission: float = 0.0

    def build_execution_model(self) -> BarExecutionModel:
        slippage_model = (
            NoSlippageModel()
            if self.spread_bps == 0 and self.impact_bps_per_volume_share == 0
            else SpreadVolumeSlippageModel(self.spread_bps, self.impact_bps_per_volume_share)
        )
        commission_model = (
            ZeroCommissionModel()
            if self.commission_bps == 0 and self.minimum_commission == 0
            else BpsCommissionModel(self.commission_bps, minimum=self.minimum_commission)
        )
        liquidity_model = (
            UnlimitedLiquidityModel()
            if self.max_volume_share >= 1.0
            else VolumeShareLiquidityModel(max_volume_share=self.max_volume_share)
        )
        return BarExecutionModel(
            slippage_model=slippage_model,
            commission_model=commission_model,
            liquidity_model=liquidity_model,
            price_column=self.price_column,
        )

    def to_metadata(self) -> dict:
        return {
            "name": self.name,
            "fill_timing": self.fill_timing,
            "price_column": self.price_column,
            "spread_bps": self.spread_bps,
            "impact_bps_per_volume_share": self.impact_bps_per_volume_share,
            "max_volume_share": self.max_volume_share,
            "commission_bps": self.commission_bps,
            "minimum_commission": self.minimum_commission,
        }
