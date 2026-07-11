import importlib as _importlib
import sys as _sys

from .core import (
    STRATEGIES,
    STRATEGY_SPECS,
    ParameterSpec,
    Strategy,
    StrategySchedule,
    StrategySpec,
    get_strategy,
    list_strategies,
    register_strategy,
    strategy_schema,
    validate_strategy_params,
)
from .systems import (
    AroonVortexTrendSystem,
    BuyAndHoldStrategy,
    ChoppinessRangeSystem,
    CryptoAdaptiveTrendSystem,
    FVGRebalanceSystem,
    GapFadeSystem,
    IchimokuCloudTrendSystem,
    LiquiditySweepReversalSystem,
    ManagedFuturesMomentumSystem,
    MeanReversionSystem,
    MomentumRegimeSystem,
    SkewReversionSystem,
    SqueezeExpansionSystem,
    StructureBreakoutRetestSystem,
    TrendPullbackSystem,
    TuffConsensusSystem,
    TuffContrarianSystem,
    TuffRegimeSwitchSystem,
    VolatilityBreakoutSystem,
    VolumeMomentumSystem,
    VWAPValueReversionSystem,
    PublishedSmaCrossStrategy,
    TuffSystem,
)

__all__ = [
    "AroonVortexTrendSystem",
    "BuyAndHoldStrategy",
    "ChoppinessRangeSystem",
    "CryptoAdaptiveTrendSystem",
    "FVGRebalanceSystem",
    "GapFadeSystem",
    "IchimokuCloudTrendSystem",
    "LiquiditySweepReversalSystem",
    "ManagedFuturesMomentumSystem",
    "MeanReversionSystem",
    "MomentumRegimeSystem",
    "ParameterSpec",
    "PublishedSmaCrossStrategy",
    "STRATEGIES",
    "STRATEGY_SPECS",
    "Strategy",
    "StrategySchedule",
    "StrategySpec",
    "StructureBreakoutRetestSystem",
    "SkewReversionSystem",
    "SqueezeExpansionSystem",
    "TuffSystem",
    "TuffConsensusSystem",
    "TuffContrarianSystem",
    "TuffRegimeSwitchSystem",
    "TrendPullbackSystem",
    "VolatilityBreakoutSystem",
    "VolumeMomentumSystem",
    "VWAPValueReversionSystem",
    "get_strategy",
    "list_strategies",
    "register_strategy",
    "strategy_schema",
    "validate_strategy_params",
]

_MODULE_ALIASES = {
    "base": "core.base",
    "buy_hold": "systems.buy_hold",
    "parameters": "core.parameters",
    "published_systems": "systems.published",
    "registry": "core.registry",
    "research_systems": "systems.research",
    "scheduling": "core.scheduling",
    "tuff_system": "systems.tuff",
}

for _old_module, _new_module in _MODULE_ALIASES.items():
    _module = _importlib.import_module(f"{__name__}.{_new_module}")
    _sys.modules[f"{__name__}.{_old_module}"] = _module
    globals()[_old_module] = _module

del _importlib, _sys, _MODULE_ALIASES, _old_module, _new_module, _module
