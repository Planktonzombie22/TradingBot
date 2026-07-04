from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional

import pandas as pd
import numpy as np


@dataclass(frozen=True)
class PortfolioLimitDecision:
    accepted: bool
    reason: Optional[str] = None


@dataclass
class PortfolioRiskLimits:
    """Portfolio-level risk gates for allocation and concentration."""

    max_symbol_weight: float = 0.25
    max_gross_exposure: float = 1.0
    max_sector_weight: float = 0.40
    max_pairwise_correlation: Optional[float] = None
    min_cash_reserve: float = 0.0
    max_net_beta: Optional[float] = None
    sector_map: Dict[str, str] = field(default_factory=dict)
    beta_map: Dict[str, float] = field(default_factory=dict)

    def evaluate_order(
        self,
        symbol: str,
        order_notional: float,
        equity: float,
        exposures: Mapping[str, float],
    ) -> PortfolioLimitDecision:
        if equity <= 0:
            return PortfolioLimitDecision(False, "Portfolio equity must be positive.")

        projected = dict(exposures)
        projected[symbol] = projected.get(symbol, 0.0) + order_notional

        symbol_weight = abs(projected[symbol]) / equity
        if symbol_weight > self.max_symbol_weight:
            return PortfolioLimitDecision(False, f"{symbol} exceeds max symbol weight.")

        gross_exposure = sum(abs(value) for value in projected.values()) / equity
        if gross_exposure > self.max_gross_exposure:
            return PortfolioLimitDecision(False, "Portfolio exceeds max gross exposure.")

        cash_reserve = max((equity - sum(max(value, 0.0) for value in projected.values())) / equity, 0.0)
        if cash_reserve < self.min_cash_reserve:
            return PortfolioLimitDecision(False, "Portfolio cash reserve would fall below minimum.")

        sector_exposure: Dict[str, float] = {}
        for projected_symbol, exposure in projected.items():
            sector = self.sector_map.get(projected_symbol, "UNKNOWN")
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + abs(exposure)
        if any(value / equity > self.max_sector_weight for value in sector_exposure.values()):
            return PortfolioLimitDecision(False, "Portfolio exceeds max sector exposure.")

        if self.max_net_beta is not None:
            net_beta = sum((exposure / equity) * self.beta_map.get(symbol, 1.0) for symbol, exposure in projected.items())
            if abs(net_beta) > self.max_net_beta:
                return PortfolioLimitDecision(False, "Portfolio exceeds max net beta exposure.")

        return PortfolioLimitDecision(True)

    def evaluate_correlation(self, returns: pd.DataFrame) -> PortfolioLimitDecision:
        if self.max_pairwise_correlation is None or returns.shape[1] < 2:
            return PortfolioLimitDecision(True)
        corr = returns.corr().abs()
        upper = np.triu(np.ones(corr.shape), k=1).astype(bool)
        max_corr = corr.where(upper).max().max()
        if pd.notna(max_corr) and max_corr > self.max_pairwise_correlation:
            return PortfolioLimitDecision(False, f"Pairwise correlation {max_corr:.2f} exceeds limit.")
        return PortfolioLimitDecision(True)
