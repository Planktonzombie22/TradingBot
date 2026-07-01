from typing import Dict, Type

from .base import Strategy
from .tuff_system import TuffSystem

StrategyRegistry = Dict[str, Type[Strategy]]


STRATEGIES: StrategyRegistry = {
    "tuffSystem": TuffSystem,
}


def get_strategy(name: str) -> Type[Strategy]:
    try:
        return STRATEGIES[name]
    except KeyError as exc:
        available = ", ".join(sorted(STRATEGIES))
        raise KeyError(f"Unknown strategy '{name}'. Available strategies: {available}") from exc
