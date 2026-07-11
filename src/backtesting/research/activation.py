from dataclasses import dataclass
from typing import Mapping, Sequence

from .regime import MarketRegimeProfile


DEFAULT_STRATEGY_MODES: dict[str, tuple[str, ...]] = {
    "buyHold": ("benchmark",),
    "meanReversion": ("mean_reversion",),
    "choppinessRange": ("mean_reversion", "range_scalping"),
    "vwapValueReversion": ("mean_reversion",),
    "gapFade": ("mean_reversion",),
    "skewReversion": ("mean_reversion",),
    "liquiditySweepReversal": ("mean_reversion",),
    "momentumRegime": ("trend_following",),
    "trendPullback": ("trend_following",),
    "volumeMomentum": ("trend_following", "breakout"),
    "volatilityBreakout": ("breakout",),
    "squeezeExpansion": ("breakout",),
    "structureBreakoutRetest": ("trend_following", "breakout"),
    "ichimokuCloudTrend": ("trend_following",),
    "aroonVortexTrend": ("trend_following",),
    "tuffSystem": ("trend_following",),
    "tuffConsensus": ("trend_following",),
    "tuffRegimeSwitch": ("trend_following", "mean_reversion"),
    "tuffContrarian": ("mean_reversion",),
}


@dataclass(frozen=True)
class StrategyActivationDecision:
    symbol: str
    strategy: str
    active: bool
    strategy_modes: tuple[str, ...]
    matched_modes: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "active": self.active,
            "strategy_modes": list(self.strategy_modes),
            "matched_modes": list(self.matched_modes),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyActivationReport:
    profile: MarketRegimeProfile
    decisions: tuple[StrategyActivationDecision, ...]

    @property
    def active_strategies(self) -> tuple[str, ...]:
        return tuple(decision.strategy for decision in self.decisions if decision.active)

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.to_dict(),
            "active_strategies": list(self.active_strategies),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


def activate_strategies_for_regime(
    strategies: Sequence[str],
    profile: MarketRegimeProfile,
    strategy_modes: Mapping[str, Sequence[str]] | None = None,
) -> StrategyActivationReport:
    """Gate strategies by the regime modes they are designed to trade."""

    mode_map = strategy_modes or DEFAULT_STRATEGY_MODES
    eligible_modes = set(profile.eligible_modes)
    decisions = []

    for strategy in strategies:
        modes = tuple(mode_map.get(strategy, ("benchmark",)))
        matched = tuple(mode for mode in modes if mode in eligible_modes)
        active = bool(matched)
        decisions.append(
            StrategyActivationDecision(
                symbol=profile.symbol,
                strategy=strategy,
                active=active,
                strategy_modes=modes,
                matched_modes=matched,
                reason="mode_match" if active else "regime_not_eligible",
            )
        )

    return StrategyActivationReport(profile=profile, decisions=tuple(decisions))
