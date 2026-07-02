from typing import Dict, Mapping, Type

from .base import Strategy
from .buy_hold import BuyAndHoldStrategy
from .parameters import ParameterSpec, StrategySpec
from .tuff_system import TuffSystem

StrategyRegistry = Dict[str, Type[Strategy]]
StrategySpecRegistry = Dict[str, StrategySpec]


STRATEGIES: StrategyRegistry = {
    "buyHold": BuyAndHoldStrategy,
    "tuffSystem": TuffSystem,
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
}


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
