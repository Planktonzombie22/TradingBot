from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd


@dataclass(frozen=True)
class FactorSpreadDefinition:
    name: str
    long_symbols: tuple[str, ...]
    short_symbols: tuple[str, ...] = tuple()
    category: str = "factor"
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "long_symbols": list(self.long_symbols),
            "short_symbols": list(self.short_symbols),
            "description": self.description,
        }


@dataclass(frozen=True)
class FactorTrendConfig:
    spreads: tuple[FactorSpreadDefinition, ...] = tuple()
    momentum_lookback: int = 63
    trend_lookback: int = 126
    volatility_lookback: int = 63
    min_history: int = 90
    min_abs_trend_score: float = 0.15
    gross_exposure_per_spread: float = 0.25
    max_active_spreads: int = 5
    allow_short_legs: bool = True


@dataclass(frozen=True)
class FactorTrendLeg:
    symbol: str
    side: str
    weight: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class FactorTrendSignal:
    name: str
    category: str
    action: str
    trend_score: float
    momentum: float
    realized_volatility: float
    spread_return: float
    legs: tuple[FactorTrendLeg, ...]
    definition: FactorSpreadDefinition

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "action": self.action,
            "trend_score": self.trend_score,
            "momentum": self.momentum,
            "realized_volatility": self.realized_volatility,
            "spread_return": self.spread_return,
            "legs": [leg.to_dict() for leg in self.legs],
            "definition": self.definition.to_dict(),
        }


@dataclass(frozen=True)
class FactorTrendReport:
    as_of: pd.Timestamp
    config: FactorTrendConfig
    signals: tuple[FactorTrendSignal, ...]
    skipped_spreads: Mapping[str, str]

    @property
    def active_signals(self) -> tuple[FactorTrendSignal, ...]:
        return tuple(signal for signal in self.signals if signal.action != "watch")

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "active_count": len(self.active_signals),
            "signals": [signal.to_dict() for signal in self.signals],
            "skipped_spreads": dict(self.skipped_spreads),
            "config": {
                "momentum_lookback": self.config.momentum_lookback,
                "trend_lookback": self.config.trend_lookback,
                "volatility_lookback": self.config.volatility_lookback,
                "min_history": self.config.min_history,
                "min_abs_trend_score": self.config.min_abs_trend_score,
                "gross_exposure_per_spread": self.config.gross_exposure_per_spread,
                "max_active_spreads": self.config.max_active_spreads,
                "allow_short_legs": self.config.allow_short_legs,
                "spreads": [spread.to_dict() for spread in self.config.spreads],
            },
        }


DEFAULT_FACTOR_SPREADS: tuple[FactorSpreadDefinition, ...] = (
    FactorSpreadDefinition("value_vs_growth", ("VLUE",), ("IWF",), "style", "Value factor trend versus growth."),
    FactorSpreadDefinition("quality_vs_market", ("QUAL",), ("SPY",), "style", "Quality factor trend versus broad market."),
    FactorSpreadDefinition("low_vol_vs_high_beta", ("USMV",), ("SPHB",), "style", "Defensive low-volatility trend versus high beta."),
    FactorSpreadDefinition("small_vs_large", ("IWM",), ("SPY",), "size", "Small-cap trend versus large-cap market."),
    FactorSpreadDefinition("tech_vs_market", ("XLK",), ("SPY",), "sector", "Technology sector trend versus broad market."),
    FactorSpreadDefinition("defensive_vs_cyclical", ("XLU", "XLP"), ("XLY", "XLI"), "sector", "Defensive sector trend versus cyclical sectors."),
    FactorSpreadDefinition("long_duration_vs_intermediate", ("TLT",), ("IEF",), "rates", "Long-duration Treasury trend versus intermediate duration."),
)


def build_factor_trend_report(
    data_by_symbol: Mapping[str, pd.DataFrame],
    as_of: str | pd.Timestamp | None = None,
    config: FactorTrendConfig | None = None,
) -> FactorTrendReport:
    if not data_by_symbol:
        raise ValueError("Factor trend research requires at least one symbol.")

    config = config or FactorTrendConfig(spreads=DEFAULT_FACTOR_SPREADS)
    if not config.spreads:
        config = FactorTrendConfig(
            spreads=DEFAULT_FACTOR_SPREADS,
            momentum_lookback=config.momentum_lookback,
            trend_lookback=config.trend_lookback,
            volatility_lookback=config.volatility_lookback,
            min_history=config.min_history,
            min_abs_trend_score=config.min_abs_trend_score,
            gross_exposure_per_spread=config.gross_exposure_per_spread,
            max_active_spreads=config.max_active_spreads,
            allow_short_legs=config.allow_short_legs,
        )
    normalized = {str(symbol).upper(): data.sort_index() for symbol, data in data_by_symbol.items()}
    as_of_timestamp = _resolve_as_of(normalized, as_of)
    signals = []
    skipped = {}

    for definition in config.spreads:
        spread_prices = _spread_price(normalized, definition, as_of_timestamp, config)
        if isinstance(spread_prices, str):
            skipped[definition.name] = spread_prices
            continue
        signal = _signal_from_spread(definition, spread_prices, config)
        signals.append(signal)

    signals = tuple(sorted(signals, key=lambda signal: abs(signal.trend_score), reverse=True))
    active = [signal for signal in signals if signal.action != "watch"][: config.max_active_spreads]
    active_names = {signal.name for signal in active}
    capped_signals = tuple(
        signal if signal.name in active_names else _watch_signal(signal)
        for signal in signals
    )
    return FactorTrendReport(
        as_of=as_of_timestamp,
        config=config,
        signals=capped_signals,
        skipped_spreads=skipped,
    )


def _resolve_as_of(data_by_symbol: Mapping[str, pd.DataFrame], as_of: str | pd.Timestamp | None) -> pd.Timestamp:
    if as_of is not None:
        return pd.Timestamp(as_of)
    timestamps = [pd.Timestamp(data.index.max()) for data in data_by_symbol.values() if len(data.index)]
    if not timestamps:
        raise ValueError("Factor trend research received only empty data frames.")
    return max(timestamps)


def _spread_price(
    data_by_symbol: Mapping[str, pd.DataFrame],
    definition: FactorSpreadDefinition,
    as_of: pd.Timestamp,
    config: FactorTrendConfig,
) -> pd.Series | str:
    long_basket = _basket_price(data_by_symbol, definition.long_symbols, as_of, config)
    if isinstance(long_basket, str):
        return long_basket
    short_basket = _basket_price(data_by_symbol, definition.short_symbols, as_of, config)
    if isinstance(short_basket, str):
        return short_basket
    if short_basket is None:
        return long_basket
    aligned = pd.concat([long_basket.rename("long"), short_basket.rename("short")], axis=1).dropna()
    if len(aligned) < config.min_history:
        return "insufficient_overlap"
    return aligned["long"] / aligned["short"]


def _basket_price(
    data_by_symbol: Mapping[str, pd.DataFrame],
    symbols: Sequence[str],
    as_of: pd.Timestamp,
    config: FactorTrendConfig,
) -> pd.Series | str | None:
    if not symbols:
        return None
    normalized_prices = []
    missing = []
    for symbol in symbols:
        history = _history(data_by_symbol, symbol, as_of)
        if history is None:
            missing.append(symbol)
            continue
        reason = _skip_reason(history, config)
        if reason:
            return f"{symbol}:{reason}"
        close = history["Close"].astype(float)
        normalized_prices.append((close / close.iloc[0]).rename(symbol))
    if missing:
        return f"missing_symbols:{','.join(missing)}"
    basket = pd.concat(normalized_prices, axis=1).dropna()
    if len(basket) < config.min_history:
        return "insufficient_overlap"
    return basket.mean(axis=1)


def _history(data_by_symbol: Mapping[str, pd.DataFrame], symbol: str, as_of: pd.Timestamp) -> pd.DataFrame | None:
    data = data_by_symbol.get(symbol.upper())
    if data is None:
        return None
    indexed = data.sort_index()
    return indexed.loc[indexed.index <= as_of].copy()


def _skip_reason(data: pd.DataFrame, config: FactorTrendConfig) -> str | None:
    if data.empty:
        return "empty_history"
    if "Close" not in data.columns:
        return "missing_columns:Close"
    if len(data) < config.min_history:
        return "insufficient_history"
    if data["Close"].dropna().empty:
        return "missing_close"
    if (data["Close"].dropna() <= 0).any():
        return "non_positive_prices"
    return None


def _signal_from_spread(
    definition: FactorSpreadDefinition,
    spread_price: pd.Series,
    config: FactorTrendConfig,
) -> FactorTrendSignal:
    returns = spread_price.pct_change()
    momentum = spread_price.iloc[-1] / spread_price.iloc[-1 - config.momentum_lookback] - 1.0
    trend_base = spread_price.tail(config.trend_lookback).mean()
    trend_score = _clamp((spread_price.iloc[-1] / trend_base - 1.0) / 0.10, -1.0, 1.0) if trend_base else 0.0
    volatility = returns.tail(config.volatility_lookback).std() * (252**0.5)
    spread_return = spread_price.iloc[-1] / spread_price.iloc[0] - 1.0
    action = _action(trend_score, config)
    legs = _legs(definition, action, config)
    return FactorTrendSignal(
        name=definition.name,
        category=definition.category,
        action=action,
        trend_score=float(trend_score),
        momentum=float(momentum),
        realized_volatility=float(volatility) if pd.notna(volatility) else 0.0,
        spread_return=float(spread_return),
        legs=legs,
        definition=definition,
    )


def _action(trend_score: float, config: FactorTrendConfig) -> str:
    if abs(trend_score) < config.min_abs_trend_score:
        return "watch"
    if trend_score > 0:
        return "long_spread"
    return "short_spread" if config.allow_short_legs else "watch"


def _legs(
    definition: FactorSpreadDefinition,
    action: str,
    config: FactorTrendConfig,
) -> tuple[FactorTrendLeg, ...]:
    if action == "watch":
        return tuple()
    gross = config.gross_exposure_per_spread
    long_weight = gross / 2 if definition.short_symbols else gross
    short_weight = gross / 2 if definition.short_symbols else 0.0
    legs = []
    long_side = "BUY" if action == "long_spread" else "SELL"
    short_side = "SELL" if action == "long_spread" else "BUY"
    long_sign = 1.0 if long_side == "BUY" else -1.0
    short_sign = -1.0 if short_side == "SELL" else 1.0
    for symbol in definition.long_symbols:
        legs.append(FactorTrendLeg(symbol, long_side, long_sign * long_weight / len(definition.long_symbols)))
    for symbol in definition.short_symbols:
        legs.append(FactorTrendLeg(symbol, short_side, short_sign * short_weight / len(definition.short_symbols)))
    return tuple(legs)


def _watch_signal(signal: FactorTrendSignal) -> FactorTrendSignal:
    return FactorTrendSignal(
        name=signal.name,
        category=signal.category,
        action="watch",
        trend_score=signal.trend_score,
        momentum=signal.momentum,
        realized_volatility=signal.realized_volatility,
        spread_return=signal.spread_return,
        legs=tuple(),
        definition=signal.definition,
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
