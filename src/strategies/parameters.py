from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Type

from .base import Strategy


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    default: Any
    type_: Type
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def validate(self, value: Any) -> Any:
        if not isinstance(value, self.type_):
            try:
                value = self.type_(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Strategy parameter '{self.name}' must be {self.type_.__name__}.") from exc
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"Strategy parameter '{self.name}' must be >= {self.minimum}.")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"Strategy parameter '{self.name}' must be <= {self.maximum}.")
        return value


@dataclass(frozen=True)
class StrategySpec:
    strategy_cls: Type[Strategy]
    parameters: Dict[str, ParameterSpec] = field(default_factory=dict)

    def validate_params(self, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        params = dict(params or {})
        unknown = set(params).difference(self.parameters)
        if unknown:
            raise ValueError(f"Unknown strategy parameters for {self.strategy_cls.__name__}: {sorted(unknown)}")

        validated = {}
        for name, spec in self.parameters.items():
            value = params.get(name, spec.default)
            validated[name] = spec.validate(value)
        return validated
