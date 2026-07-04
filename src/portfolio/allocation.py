from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd


@dataclass(frozen=True)
class AllocationTarget:
    symbol: str
    weight: float
    notional: float


class AllocationPolicy:
    def allocate(self, symbols: Sequence[str], equity: float, **kwargs) -> list[AllocationTarget]:
        raise NotImplementedError


@dataclass(frozen=True)
class EqualWeightAllocation(AllocationPolicy):
    gross_exposure: float = 1.0

    def allocate(self, symbols: Sequence[str], equity: float, **kwargs) -> list[AllocationTarget]:
        if not symbols or equity <= 0:
            return []
        weight = self.gross_exposure / len(symbols)
        return [AllocationTarget(symbol, weight, equity * weight) for symbol in symbols]


@dataclass(frozen=True)
class FixedNotionalAllocation(AllocationPolicy):
    notional_per_symbol: float

    def allocate(self, symbols: Sequence[str], equity: float, **kwargs) -> list[AllocationTarget]:
        if equity <= 0:
            return []
        return [
            AllocationTarget(symbol, self.notional_per_symbol / equity, self.notional_per_symbol)
            for symbol in symbols
        ]


@dataclass(frozen=True)
class VolatilityTargetAllocation(AllocationPolicy):
    target_portfolio_volatility: float = 0.10
    max_gross_exposure: float = 1.0

    def allocate(self, symbols: Sequence[str], equity: float, **kwargs) -> list[AllocationTarget]:
        returns = kwargs.get("returns")
        if not symbols or equity <= 0 or returns is None:
            return EqualWeightAllocation(self.max_gross_exposure).allocate(symbols, equity)
        raw_weights = _inverse_vol_weights(symbols, returns)
        scaled = _scale_to_gross(raw_weights, min(self.target_portfolio_volatility, self.max_gross_exposure))
        return [AllocationTarget(symbol, scaled.get(symbol, 0.0), equity * scaled.get(symbol, 0.0)) for symbol in symbols]


@dataclass(frozen=True)
class RiskParityAllocation(AllocationPolicy):
    gross_exposure: float = 1.0

    def allocate(self, symbols: Sequence[str], equity: float, **kwargs) -> list[AllocationTarget]:
        returns = kwargs.get("returns")
        if not symbols or equity <= 0 or returns is None:
            return EqualWeightAllocation(self.gross_exposure).allocate(symbols, equity)
        weights = _scale_to_gross(_inverse_vol_weights(symbols, returns), self.gross_exposure)
        return [AllocationTarget(symbol, weights.get(symbol, 0.0), equity * weights.get(symbol, 0.0)) for symbol in symbols]


def _inverse_vol_weights(symbols: Sequence[str], returns: pd.DataFrame) -> Mapping[str, float]:
    vol = returns[list(symbols)].std().replace(0, pd.NA).dropna()
    if vol.empty:
        return {symbol: 1 / len(symbols) for symbol in symbols}
    inverse = 1 / vol
    total = inverse.sum()
    if not total:
        return {symbol: 1 / len(symbols) for symbol in symbols}
    return {symbol: float(inverse.get(symbol, 0.0) / total) for symbol in symbols}


def _scale_to_gross(weights: Mapping[str, float], gross_exposure: float) -> dict[str, float]:
    gross = sum(abs(value) for value in weights.values())
    if gross == 0:
        return dict(weights)
    return {symbol: value / gross * gross_exposure for symbol, value in weights.items()}
