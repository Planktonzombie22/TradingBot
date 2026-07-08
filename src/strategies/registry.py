from typing import Dict, Mapping, Type

from .base import Strategy
from .buy_hold import BuyAndHoldStrategy
from .parameters import ParameterSpec, StrategySpec
from .published_systems import PublishedSmaCrossStrategy
from .research_systems import (
    MeanReversionSystem,
    AroonVortexTrendSystem,
    ChoppinessRangeSystem,
    FVGRebalanceSystem,
    GapFadeSystem,
    IchimokuCloudTrendSystem,
    LiquiditySweepReversalSystem,
    MomentumRegimeSystem,
    StructureBreakoutRetestSystem,
    SkewReversionSystem,
    SqueezeExpansionSystem,
    TrendPullbackSystem,
    TuffConsensusSystem,
    TuffContrarianSystem,
    TuffRegimeSwitchSystem,
    VolatilityBreakoutSystem,
    VolumeMomentumSystem,
    VWAPValueReversionSystem,
)
from .tuff_system import TuffSystem

StrategyRegistry = Dict[str, Type[Strategy]]
StrategySpecRegistry = Dict[str, StrategySpec]


STRATEGIES: StrategyRegistry = {
    "buyHold": BuyAndHoldStrategy,
    "aroonVortexTrend": AroonVortexTrendSystem,
    "choppinessRange": ChoppinessRangeSystem,
    "fvgRebalance": FVGRebalanceSystem,
    "gapFade": GapFadeSystem,
    "ichimokuCloudTrend": IchimokuCloudTrendSystem,
    "liquiditySweepReversal": LiquiditySweepReversalSystem,
    "meanReversion": MeanReversionSystem,
    "momentumRegime": MomentumRegimeSystem,
    "publishedSmaCross": PublishedSmaCrossStrategy,
    "squeezeExpansion": SqueezeExpansionSystem,
    "skewReversion": SkewReversionSystem,
    "structureBreakoutRetest": StructureBreakoutRetestSystem,
    "tuffConsensus": TuffConsensusSystem,
    "tuffContrarian": TuffContrarianSystem,
    "tuffRegimeSwitch": TuffRegimeSwitchSystem,
    "tuffSystem": TuffSystem,
    "trendPullback": TrendPullbackSystem,
    "volatilityBreakout": VolatilityBreakoutSystem,
    "volumeMomentum": VolumeMomentumSystem,
    "vwapValueReversion": VWAPValueReversionSystem,
}

STRATEGY_SPECS: StrategySpecRegistry = {
    "buyHold": StrategySpec(
        BuyAndHoldStrategy,
        parameters={
            "stop_percent": ParameterSpec("stop_percent", default=0.05, type_=float, minimum=0.0001, maximum=0.99),
            "target_fraction": ParameterSpec("target_fraction", default=1.0, type_=float, minimum=0.0, maximum=1.0),
            "use_stop_loss": ParameterSpec("use_stop_loss", default=False, type_=bool),
        },
    ),
    "tuffSystem": StrategySpec(
        TuffSystem,
        parameters={
            "adx_minimum": ParameterSpec("adx_minimum", default=30, type_=int, minimum=0),
            "rsi_deviation": ParameterSpec("rsi_deviation", default=5, type_=int, minimum=0, maximum=49),
        },
    ),
    "publishedSmaCross": StrategySpec(
        PublishedSmaCrossStrategy,
        parameters={
            "fast_period": ParameterSpec("fast_period", default=10, type_=int, minimum=2, optimize_values=[5, 10, 15]),
            "slow_period": ParameterSpec("slow_period", default=20, type_=int, minimum=3, optimize_values=[15, 20, 30]),
            "target_fraction": ParameterSpec("target_fraction", default=1.0, type_=float, minimum=0.0, maximum=1.0),
            "signal_delay_bars": ParameterSpec("signal_delay_bars", default=1, type_=int, minimum=0, maximum=5),
            "commission_bps": ParameterSpec("commission_bps", default=0.0, type_=float, minimum=0.0),
        },
    ),
    "momentumRegime": StrategySpec(
        MomentumRegimeSystem,
        parameters={
            "fast_ema": ParameterSpec("fast_ema", default=20, type_=int, minimum=2, optimize_values=[10, 15, 20, 30]),
            "slow_ema": ParameterSpec("slow_ema", default=50, type_=int, minimum=3, optimize_values=[40, 50, 75, 100]),
            "roc_period": ParameterSpec("roc_period", default=20, type_=int, minimum=2, optimize_values=[10, 20, 30]),
            "min_roc": ParameterSpec("min_roc", default=0.0, type_=float, minimum=0.0, optimize_values=[0.0, 0.02, 0.05]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=3.0, type_=float, minimum=0.1, optimize_values=[2.0, 3.0, 4.0]),
        },
    ),
    "meanReversion": StrategySpec(
        MeanReversionSystem,
        parameters={
            "band_period": ParameterSpec("band_period", default=20, type_=int, minimum=5, optimize_values=[15, 20, 30]),
            "band_deviation": ParameterSpec("band_deviation", default=2.0, type_=float, minimum=0.5, optimize_values=[1.5, 2.0, 2.5]),
            "oversold": ParameterSpec("oversold", default=30, type_=int, minimum=1, maximum=49, optimize_values=[25, 30, 35]),
            "overbought": ParameterSpec("overbought", default=70, type_=int, minimum=51, maximum=99, optimize_values=[65, 70, 75]),
            "min_zscore": ParameterSpec("min_zscore", default=1.5, type_=float, minimum=0.1, optimize_values=[1.0, 1.5, 2.0]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.0, type_=float, minimum=0.1, optimize_values=[1.5, 2.0, 2.5]),
        },
    ),
    "volatilityBreakout": StrategySpec(
        VolatilityBreakoutSystem,
        parameters={
            "channel_period": ParameterSpec("channel_period", default=55, type_=int, minimum=5, optimize_values=[20, 40, 55, 80]),
            "min_adx": ParameterSpec("min_adx", default=18, type_=int, minimum=0, optimize_values=[12, 18, 25]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=3.0, type_=float, minimum=0.1, optimize_values=[2.0, 3.0, 4.0]),
            "min_channel_width": ParameterSpec("min_channel_width", default=0.02, type_=float, minimum=0.0, optimize_values=[0.0, 0.02, 0.05]),
        },
    ),
    "trendPullback": StrategySpec(
        TrendPullbackSystem,
        parameters={
            "fast_ema": ParameterSpec("fast_ema", default=20, type_=int, minimum=2, optimize_values=[10, 20, 30]),
            "slow_ema": ParameterSpec("slow_ema", default=100, type_=int, minimum=3, optimize_values=[75, 100, 150]),
            "pullback_rsi": ParameterSpec("pullback_rsi", default=45, type_=int, minimum=1, maximum=49, optimize_values=[40, 45, 50]),
            "rebound_rsi": ParameterSpec("rebound_rsi", default=55, type_=int, minimum=51, maximum=99, optimize_values=[52, 55, 60]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.5, type_=float, minimum=0.1, optimize_values=[2.0, 2.5, 3.0]),
        },
    ),
    "volumeMomentum": StrategySpec(
        VolumeMomentumSystem,
        parameters={
            "roc_period": ParameterSpec("roc_period", default=20, type_=int, minimum=2, optimize_values=[10, 20, 30]),
            "min_roc": ParameterSpec("min_roc", default=0.03, type_=float, minimum=0.0, optimize_values=[0.0, 0.03, 0.06]),
            "obv_ema_period": ParameterSpec("obv_ema_period", default=20, type_=int, minimum=2, optimize_values=[10, 20, 30]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=3.0, type_=float, minimum=0.1, optimize_values=[2.0, 3.0, 4.0]),
        },
    ),
    "squeezeExpansion": StrategySpec(
        SqueezeExpansionSystem,
        parameters={
            "band_period": ParameterSpec("band_period", default=20, type_=int, minimum=5, optimize_values=[15, 20, 30]),
            "band_deviation": ParameterSpec("band_deviation", default=2.0, type_=float, minimum=0.5, optimize_values=[1.5, 2.0]),
            "keltner_multiple": ParameterSpec("keltner_multiple", default=1.5, type_=float, minimum=0.5, optimize_values=[1.0, 1.5, 2.0]),
            "momentum_period": ParameterSpec("momentum_period", default=20, type_=int, minimum=2, optimize_values=[10, 20, 30]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.5, type_=float, minimum=0.1, optimize_values=[2.0, 2.5, 3.0]),
        },
    ),
    "gapFade": StrategySpec(
        GapFadeSystem,
        parameters={
            "gap_threshold": ParameterSpec("gap_threshold", default=0.015, type_=float, minimum=0.0, optimize_values=[0.01, 0.015, 0.025]),
            "oversold": ParameterSpec("oversold", default=35, type_=int, minimum=1, maximum=49, optimize_values=[30, 35, 40]),
            "overbought": ParameterSpec("overbought", default=65, type_=int, minimum=51, maximum=99, optimize_values=[60, 65, 70]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.0, type_=float, minimum=0.1, optimize_values=[1.5, 2.0, 2.5]),
        },
    ),
    "skewReversion": StrategySpec(
        SkewReversionSystem,
        parameters={
            "lookback": ParameterSpec("lookback", default=20, type_=int, minimum=5, optimize_values=[15, 20, 30]),
            "zscore_entry": ParameterSpec("zscore_entry", default=1.5, type_=float, minimum=0.1, optimize_values=[1.0, 1.5, 2.0]),
            "skew_threshold": ParameterSpec("skew_threshold", default=0.2, type_=float, minimum=0.0, optimize_values=[0.0, 0.2, 0.5]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.0, type_=float, minimum=0.1, optimize_values=[1.5, 2.0, 2.5]),
        },
    ),
    "fvgRebalance": StrategySpec(
        FVGRebalanceSystem,
        parameters={
            "min_gap_atr": ParameterSpec("min_gap_atr", default=0.15, type_=float, minimum=0.0, optimize_values=[0.05, 0.15, 0.30]),
            "rsi_floor": ParameterSpec("rsi_floor", default=48, type_=int, minimum=1, maximum=99, optimize_values=[45, 48, 52]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=1.8, type_=float, minimum=0.1, optimize_values=[1.5, 1.8, 2.2]),
        },
    ),
    "liquiditySweepReversal": StrategySpec(
        LiquiditySweepReversalSystem,
        parameters={
            "sweep_lookback": ParameterSpec("sweep_lookback", default=20, type_=int, minimum=3, optimize_values=[10, 20, 30]),
            "mfi_extreme": ParameterSpec("mfi_extreme", default=45, type_=int, minimum=1, maximum=49, optimize_values=[35, 40, 45]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.0, type_=float, minimum=0.1, optimize_values=[1.5, 2.0, 2.5]),
        },
    ),
    "structureBreakoutRetest": StrategySpec(
        StructureBreakoutRetestSystem,
        parameters={
            "structure_lookback": ParameterSpec("structure_lookback", default=30, type_=int, minimum=5, optimize_values=[20, 30, 50]),
            "min_relative_volume": ParameterSpec("min_relative_volume", default=1.1, type_=float, minimum=0.0, optimize_values=[0.8, 1.1, 1.5]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.5, type_=float, minimum=0.1, optimize_values=[2.0, 2.5, 3.0]),
        },
    ),
    "vwapValueReversion": StrategySpec(
        VWAPValueReversionSystem,
        parameters={
            "distance_threshold": ParameterSpec("distance_threshold", default=0.04, type_=float, minimum=0.0, optimize_values=[0.02, 0.04, 0.06]),
            "cmf_period": ParameterSpec("cmf_period", default=20, type_=int, minimum=2, optimize_values=[10, 20, 30]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.0, type_=float, minimum=0.1, optimize_values=[1.5, 2.0, 2.5]),
        },
    ),
    "ichimokuCloudTrend": StrategySpec(
        IchimokuCloudTrendSystem,
        parameters={
            "min_cloud_bias": ParameterSpec("min_cloud_bias", default=0.0, type_=float, minimum=0.0, optimize_values=[0.0, 0.5, 1.0]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=3.0, type_=float, minimum=0.1, optimize_values=[2.0, 3.0, 4.0]),
        },
    ),
    "choppinessRange": StrategySpec(
        ChoppinessRangeSystem,
        parameters={
            "chop_threshold": ParameterSpec("chop_threshold", default=55.0, type_=float, minimum=0.0, optimize_values=[50.0, 55.0, 60.0]),
            "band_deviation": ParameterSpec("band_deviation", default=2.0, type_=float, minimum=0.5, optimize_values=[1.5, 2.0, 2.5]),
            "mfi_extreme": ParameterSpec("mfi_extreme", default=40, type_=int, minimum=1, maximum=49, optimize_values=[35, 40, 45]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=1.8, type_=float, minimum=0.1, optimize_values=[1.5, 1.8, 2.2]),
        },
    ),
    "aroonVortexTrend": StrategySpec(
        AroonVortexTrendSystem,
        parameters={
            "aroon_threshold": ParameterSpec("aroon_threshold", default=20.0, type_=float, minimum=0.0, optimize_values=[10.0, 20.0, 35.0]),
            "vortex_threshold": ParameterSpec("vortex_threshold", default=0.05, type_=float, minimum=0.0, optimize_values=[0.0, 0.05, 0.10]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.8, type_=float, minimum=0.1, optimize_values=[2.0, 2.8, 3.5]),
        },
    ),
    "tuffConsensus": StrategySpec(
        TuffConsensusSystem,
        parameters={
            "adx_minimum": ParameterSpec("adx_minimum", default=18, type_=int, minimum=0, optimize_values=[12, 18, 25]),
            "vote_threshold": ParameterSpec("vote_threshold", default=4, type_=int, minimum=1, maximum=6, optimize_values=[3, 4, 5]),
            "rsi_deviation": ParameterSpec("rsi_deviation", default=3, type_=int, minimum=0, maximum=49, optimize_values=[0, 3, 6]),
            "roc_period": ParameterSpec("roc_period", default=20, type_=int, minimum=2, optimize_values=[10, 20, 30]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.5, type_=float, minimum=0.1, optimize_values=[2.0, 2.5, 3.0]),
        },
    ),
    "tuffRegimeSwitch": StrategySpec(
        TuffRegimeSwitchSystem,
        parameters={
            "trend_adx": ParameterSpec("trend_adx", default=22, type_=int, minimum=0, optimize_values=[18, 22, 28]),
            "range_adx": ParameterSpec("range_adx", default=18, type_=int, minimum=0, optimize_values=[12, 18, 22]),
            "rsi_deviation": ParameterSpec("rsi_deviation", default=5, type_=int, minimum=0, maximum=49, optimize_values=[3, 5, 8]),
            "band_period": ParameterSpec("band_period", default=20, type_=int, minimum=5, optimize_values=[15, 20, 30]),
            "band_deviation": ParameterSpec("band_deviation", default=1.8, type_=float, minimum=0.5, optimize_values=[1.5, 1.8, 2.2]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=2.0, type_=float, minimum=0.1, optimize_values=[1.5, 2.0, 2.5]),
        },
    ),
    "tuffContrarian": StrategySpec(
        TuffContrarianSystem,
        parameters={
            "adx_minimum": ParameterSpec("adx_minimum", default=25, type_=int, minimum=0, optimize_values=[18, 25, 32]),
            "rsi_extreme": ParameterSpec("rsi_extreme", default=68, type_=int, minimum=51, maximum=99, optimize_values=[62, 68, 74]),
            "zscore_extreme": ParameterSpec("zscore_extreme", default=1.5, type_=float, minimum=0.1, optimize_values=[1.0, 1.5, 2.0]),
            "band_period": ParameterSpec("band_period", default=20, type_=int, minimum=5, optimize_values=[15, 20, 30]),
            "atr_stop_multiple": ParameterSpec("atr_stop_multiple", default=1.8, type_=float, minimum=0.1, optimize_values=[1.5, 1.8, 2.2]),
        },
    ),
}


def register_strategy(
    name: str,
    strategy_cls: Type[Strategy],
    parameters: Mapping[str, ParameterSpec] | None = None,
    replace: bool = False,
) -> None:
    """Register a strategy without editing the built-in registry tables."""

    if name in STRATEGIES and not replace:
        raise ValueError(f"Strategy '{name}' is already registered.")
    STRATEGIES[name] = strategy_cls
    STRATEGY_SPECS[name] = StrategySpec(strategy_cls, parameters=dict(parameters or {}))


def get_strategy(name: str) -> Type[Strategy]:
    try:
        return STRATEGIES[name]
    except KeyError as exc:
        available = ", ".join(sorted(STRATEGIES))
        raise KeyError(f"Unknown strategy '{name}'. Available strategies: {available}") from exc


def validate_strategy_params(name: str, params: Mapping[str, object] | None = None) -> Dict[str, object]:
    try:
        return STRATEGY_SPECS[name].validate_params(params)
    except KeyError as exc:
        available = ", ".join(sorted(STRATEGY_SPECS))
        raise KeyError(f"Unknown strategy '{name}'. Available strategies: {available}") from exc


def strategy_schema(name: str) -> Dict[str, object]:
    try:
        return STRATEGY_SPECS[name].to_schema()
    except KeyError as exc:
        available = ", ".join(sorted(STRATEGY_SPECS))
        raise KeyError(f"Unknown strategy '{name}'. Available strategies: {available}") from exc


def list_strategies() -> list[str]:
    return sorted(STRATEGIES)
