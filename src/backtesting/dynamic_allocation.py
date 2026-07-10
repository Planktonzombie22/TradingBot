from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd


@dataclass(frozen=True)
class DynamicAllocationConfig:
    growth_symbols: tuple[str, ...] = ("SPY", "QQQ")
    defensive_symbols: tuple[str, ...] = ("XLU", "XLP")
    bond_symbols: tuple[str, ...] = ("TLT", "IEF")
    commodity_symbols: tuple[str, ...] = ("GLD", "DBC")
    hedge_symbols: tuple[str, ...] = ("VIXY",)
    cash_symbol: str = "CASH"
    trend_lookback: int = 80
    drawdown_lookback: int = 120
    volatility_short_lookback: int = 20
    volatility_long_lookback: int = 80
    liquidity_lookback: int = 20
    macro_lookback: int = 60
    min_history: int = 90
    cash_min_weight: float = 0.05
    cash_max_weight: float = 0.60
    growth_min_weight: float = 0.10
    growth_max_weight: float = 0.70
    defensive_max_weight: float = 0.35
    bond_max_weight: float = 0.45
    commodity_max_weight: float = 0.25
    hedge_max_weight: float = 0.15
    max_symbol_weight: float = 0.35


@dataclass(frozen=True)
class DynamicMarketStressScore:
    trend_score: float
    drawdown_stress: float
    volatility_stress: float
    rates_stress: float
    liquidity_stress: float
    aggregate_stress: float
    regime: str

    def to_dict(self) -> dict:
        return {
            "trend_score": self.trend_score,
            "drawdown_stress": self.drawdown_stress,
            "volatility_stress": self.volatility_stress,
            "rates_stress": self.rates_stress,
            "liquidity_stress": self.liquidity_stress,
            "aggregate_stress": self.aggregate_stress,
            "regime": self.regime,
        }


@dataclass(frozen=True)
class DynamicAllocationTarget:
    sleeve: str
    symbol: str
    weight: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "sleeve": self.sleeve,
            "symbol": self.symbol,
            "weight": self.weight,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DynamicAllocationReport:
    as_of: pd.Timestamp
    stress: DynamicMarketStressScore
    targets: tuple[DynamicAllocationTarget, ...]
    skipped_symbols: Mapping[str, str]
    config: DynamicAllocationConfig

    @property
    def weights_by_symbol(self) -> dict[str, float]:
        weights: dict[str, float] = {}
        for target in self.targets:
            weights[target.symbol] = weights.get(target.symbol, 0.0) + target.weight
        return weights

    @property
    def invested_weight(self) -> float:
        return sum(target.weight for target in self.targets if target.sleeve != "cash")

    @property
    def cash_weight(self) -> float:
        return sum(target.weight for target in self.targets if target.sleeve == "cash")

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "stress": self.stress.to_dict(),
            "invested_weight": self.invested_weight,
            "cash_weight": self.cash_weight,
            "weights_by_symbol": self.weights_by_symbol,
            "targets": [target.to_dict() for target in self.targets],
            "skipped_symbols": dict(self.skipped_symbols),
            "config": {
                "growth_symbols": list(self.config.growth_symbols),
                "defensive_symbols": list(self.config.defensive_symbols),
                "bond_symbols": list(self.config.bond_symbols),
                "commodity_symbols": list(self.config.commodity_symbols),
                "hedge_symbols": list(self.config.hedge_symbols),
                "cash_symbol": self.config.cash_symbol,
                "trend_lookback": self.config.trend_lookback,
                "drawdown_lookback": self.config.drawdown_lookback,
                "volatility_short_lookback": self.config.volatility_short_lookback,
                "volatility_long_lookback": self.config.volatility_long_lookback,
                "liquidity_lookback": self.config.liquidity_lookback,
                "macro_lookback": self.config.macro_lookback,
                "min_history": self.config.min_history,
                "max_symbol_weight": self.config.max_symbol_weight,
            },
        }


def build_dynamic_allocation(
    data_by_symbol: Mapping[str, pd.DataFrame],
    as_of: str | pd.Timestamp | None = None,
    config: DynamicAllocationConfig | None = None,
) -> DynamicAllocationReport:
    """Build a smooth risk-on/risk-off allocation overlay from market context."""

    if not data_by_symbol:
        raise ValueError("Dynamic allocation requires at least one symbol.")

    config = config or DynamicAllocationConfig()
    normalized = {str(symbol).upper(): data.sort_index() for symbol, data in data_by_symbol.items()}
    as_of_timestamp = _resolve_as_of(normalized, as_of)
    skipped = _skipped_symbols(normalized, as_of_timestamp, config)
    stress = _market_stress(normalized, as_of_timestamp, config)
    sleeve_weights = _sleeve_weights(stress, config)
    targets = _targets_for_sleeves(normalized, as_of_timestamp, sleeve_weights, config)

    return DynamicAllocationReport(
        as_of=as_of_timestamp,
        stress=stress,
        targets=targets,
        skipped_symbols=skipped,
        config=config,
    )


def _resolve_as_of(data_by_symbol: Mapping[str, pd.DataFrame], as_of: str | pd.Timestamp | None) -> pd.Timestamp:
    if as_of is not None:
        return pd.Timestamp(as_of)
    timestamps = [pd.Timestamp(data.index.max()) for data in data_by_symbol.values() if len(data.index)]
    if not timestamps:
        raise ValueError("Dynamic allocation received only empty data frames.")
    return max(timestamps)


def _skipped_symbols(
    data_by_symbol: Mapping[str, pd.DataFrame],
    as_of: pd.Timestamp,
    config: DynamicAllocationConfig,
) -> dict[str, str]:
    skipped = {}
    for symbol, data in data_by_symbol.items():
        history = _history_until(data, as_of)
        reason = _skip_reason(history, config)
        if reason:
            skipped[symbol] = reason
    return skipped


def _market_stress(
    data_by_symbol: Mapping[str, pd.DataFrame],
    as_of: pd.Timestamp,
    config: DynamicAllocationConfig,
) -> DynamicMarketStressScore:
    growth = _first_clean_history(data_by_symbol, config.growth_symbols, as_of, config)
    if growth is None:
        raise ValueError("Dynamic allocation requires at least one clean growth proxy.")

    close = growth["Close"].astype(float)
    volume = growth["Volume"].astype(float) if "Volume" in growth.columns else pd.Series(1.0, index=growth.index)
    moving_average = close.tail(config.trend_lookback).mean()
    trend_score = _clamp((close.iloc[-1] / moving_average - 1.0) / 0.10, -1.0, 1.0) if moving_average else 0.0
    rolling_high = close.tail(config.drawdown_lookback).max()
    drawdown = close.iloc[-1] / rolling_high - 1.0
    drawdown_stress = _clamp(abs(min(0.0, drawdown)) / 0.30, 0.0, 1.0)
    returns = close.pct_change()
    short_vol = returns.tail(config.volatility_short_lookback).std()
    long_vol = returns.tail(config.volatility_long_lookback).std()
    volatility_ratio = short_vol / long_vol if long_vol and pd.notna(long_vol) else 1.0
    volatility_stress = _clamp((volatility_ratio - 1.0) / 1.0, 0.0, 1.0)
    recent_volume = volume.tail(config.liquidity_lookback).mean()
    baseline_volume = volume.tail(config.volatility_long_lookback).mean()
    liquidity_stress = _clamp(1.0 - recent_volume / baseline_volume, 0.0, 1.0) if baseline_volume else 0.0
    rates_stress = _rates_stress(data_by_symbol, as_of, config)
    aggregate = _clamp(
        0.30 * (1.0 - (trend_score + 1.0) / 2.0)
        + 0.25 * drawdown_stress
        + 0.20 * volatility_stress
        + 0.15 * rates_stress
        + 0.10 * liquidity_stress,
        0.0,
        1.0,
    )
    return DynamicMarketStressScore(
        trend_score=float(trend_score),
        drawdown_stress=float(drawdown_stress),
        volatility_stress=float(volatility_stress),
        rates_stress=float(rates_stress),
        liquidity_stress=float(liquidity_stress),
        aggregate_stress=float(aggregate),
        regime=_regime(aggregate),
    )


def _rates_stress(
    data_by_symbol: Mapping[str, pd.DataFrame],
    as_of: pd.Timestamp,
    config: DynamicAllocationConfig,
) -> float:
    bond = _first_clean_history(data_by_symbol, config.bond_symbols, as_of, config)
    if bond is None:
        return 0.0
    close = bond["Close"].astype(float)
    if len(close) <= config.macro_lookback:
        return 0.0
    bond_return = close.iloc[-1] / close.iloc[-1 - config.macro_lookback] - 1.0
    return _clamp(-bond_return / 0.15, 0.0, 1.0)


def _sleeve_weights(stress: DynamicMarketStressScore, config: DynamicAllocationConfig) -> dict[str, float]:
    s = stress.aggregate_stress
    cash = config.cash_min_weight + (config.cash_max_weight - config.cash_min_weight) * s
    growth = config.growth_max_weight - (config.growth_max_weight - config.growth_min_weight) * s
    defensive = config.defensive_max_weight * s * 0.65
    bonds = config.bond_max_weight * s * (1.0 - 0.50 * stress.rates_stress)
    commodities = config.commodity_max_weight * (0.35 + 0.65 * max(stress.rates_stress, stress.volatility_stress))
    hedge = config.hedge_max_weight * max(stress.drawdown_stress, stress.volatility_stress)
    raw = {
        "growth": growth,
        "defensive": defensive,
        "bonds": bonds,
        "commodities": commodities,
        "hedge": hedge,
        "cash": cash,
    }
    total = sum(raw.values()) or 1.0
    return {sleeve: weight / total for sleeve, weight in raw.items()}


def _targets_for_sleeves(
    data_by_symbol: Mapping[str, pd.DataFrame],
    as_of: pd.Timestamp,
    sleeve_weights: Mapping[str, float],
    config: DynamicAllocationConfig,
) -> tuple[DynamicAllocationTarget, ...]:
    sleeve_symbols = {
        "growth": config.growth_symbols,
        "defensive": config.defensive_symbols,
        "bonds": config.bond_symbols,
        "commodities": config.commodity_symbols,
        "hedge": config.hedge_symbols,
    }
    targets = []
    for sleeve, symbols in sleeve_symbols.items():
        clean_symbols = tuple(symbol for symbol in symbols if _clean_history(data_by_symbol, symbol, as_of, config) is not None)
        targets.extend(_split_sleeve(sleeve, clean_symbols, sleeve_weights.get(sleeve, 0.0), config.max_symbol_weight))
    cash_weight = max(0.0, 1.0 - sum(target.weight for target in targets))
    if cash_weight > 0:
        targets.append(DynamicAllocationTarget("cash", config.cash_symbol, cash_weight, "residual_cash"))
    return tuple(targets)


def _split_sleeve(
    sleeve: str,
    symbols: Sequence[str],
    sleeve_weight: float,
    max_symbol_weight: float,
) -> tuple[DynamicAllocationTarget, ...]:
    if not symbols or sleeve_weight <= 0:
        return tuple()
    equal_weight = min(max_symbol_weight, sleeve_weight / len(symbols))
    allocated = []
    remaining = sleeve_weight
    for symbol in symbols:
        if remaining <= 0:
            break
        weight = min(equal_weight, remaining)
        allocated.append(DynamicAllocationTarget(sleeve, symbol, weight, f"{sleeve}_sleeve"))
        remaining -= weight
    return tuple(allocated)


def _first_clean_history(
    data_by_symbol: Mapping[str, pd.DataFrame],
    symbols: Sequence[str],
    as_of: pd.Timestamp,
    config: DynamicAllocationConfig,
) -> pd.DataFrame | None:
    for symbol in symbols:
        history = _clean_history(data_by_symbol, symbol, as_of, config)
        if history is not None:
            return history
    return None


def _clean_history(
    data_by_symbol: Mapping[str, pd.DataFrame],
    symbol: str,
    as_of: pd.Timestamp,
    config: DynamicAllocationConfig,
) -> pd.DataFrame | None:
    data = data_by_symbol.get(symbol.upper())
    if data is None:
        return None
    history = _history_until(data, as_of)
    return None if _skip_reason(history, config) else history


def _history_until(data: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if data.empty:
        return data
    indexed = data.sort_index()
    return indexed.loc[indexed.index <= as_of].copy()


def _skip_reason(data: pd.DataFrame, config: DynamicAllocationConfig) -> str | None:
    if data.empty:
        return "empty_history"
    missing = sorted({"Close"}.difference(data.columns))
    if missing:
        return f"missing_columns:{','.join(missing)}"
    if len(data) < config.min_history:
        return "insufficient_history"
    if data["Close"].dropna().empty:
        return "missing_close"
    return None


def _regime(stress: float) -> str:
    if stress >= 0.75:
        return "crisis"
    if stress >= 0.50:
        return "risk_off"
    if stress >= 0.25:
        return "balanced"
    return "risk_on"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
