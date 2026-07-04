from typing import Dict, Mapping, Type

from .base import Strategy
from .buy_hold import BuyAndHoldStrategy
from .parameters import ParameterSpec, StrategySpec
from .research_systems import MeanReversionSystem, MomentumRegimeSystem, VolatilityBreakoutSystem
from .tuff_system import TuffSystem

StrategyRegistry = Dict[str, Type[Strategy]]
StrategySpecRegistry = Dict[str, StrategySpec]


STRATEGIES: StrategyRegistry = {
    "buyHold": BuyAndHoldStrategy,
    "meanReversion": MeanReversionSystem,
    "momentumRegime": MomentumRegimeSystem,
    "tuffSystem": TuffSystem,
    "volatilityBreakout": VolatilityBreakoutSystem,
}

STRATEGY_SPECS: StrategySpecRegistry = {
    "buyHold": StrategySpec(
        BuyAndHoldStrategy,
        parameters={
            "stop_percent": ParameterSpec("stop_percent", default=0.05, type_=float, minimum=0.0001, maximum=0.99),
        },
    ),
    "tuffSystem": StrategySpec(
        TuffSystem,
        parameters={
            "adx_minimum": ParameterSpec("adx_minimum", default=30, type_=int, minimum=0),
            "rsi_deviation": ParameterSpec("rsi_deviation", default=5, type_=int, minimum=0, maximum=49),
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
