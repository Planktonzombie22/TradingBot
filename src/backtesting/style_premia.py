from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd


@dataclass(frozen=True)
class StylePremiaConfig:
    momentum_lookback: int = 63
    long_momentum_lookback: int = 126
    momentum_skip_bars: int = 0
    volatility_lookback: int = 63
    value_lookback: int = 126
    quality_lookback: int = 63
    carry_lookback: int = 21
    min_history: int = 80
    top_n: int = 5
    bottom_n: int = 0
    long_gross_exposure: float = 1.0
    short_gross_exposure: float = 0.0
    momentum_weight: float = 0.35
    value_weight: float = 0.20
    quality_weight: float = 0.20
    low_volatility_weight: float = 0.15
    carry_weight: float = 0.10
    score_weighted_allocations: bool = False

    @property
    def factor_weights(self) -> dict[str, float]:
        return {
            "momentum": self.momentum_weight,
            "value": self.value_weight,
            "quality": self.quality_weight,
            "low_volatility": self.low_volatility_weight,
            "carry": self.carry_weight,
        }


@dataclass(frozen=True)
class StylePremiaScore:
    symbol: str
    rank: int
    composite_score: float
    target_weight: float
    component_scores: Mapping[str, float]
    raw_metrics: Mapping[str, float | None]

    @property
    def side(self) -> str:
        if self.target_weight > 0:
            return "long"
        if self.target_weight < 0:
            return "short"
        return "watch"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "rank": self.rank,
            "side": self.side,
            "composite_score": self.composite_score,
            "target_weight": self.target_weight,
            "component_scores": dict(self.component_scores),
            "raw_metrics": dict(self.raw_metrics),
        }


@dataclass(frozen=True)
class StylePremiaRankingReport:
    as_of: pd.Timestamp
    config: StylePremiaConfig
    scores: tuple[StylePremiaScore, ...]
    skipped_symbols: Mapping[str, str]

    @property
    def long_symbols(self) -> tuple[str, ...]:
        return tuple(score.symbol for score in self.scores if score.target_weight > 0)

    @property
    def short_symbols(self) -> tuple[str, ...]:
        return tuple(score.symbol for score in self.scores if score.target_weight < 0)

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "config": {
                "momentum_lookback": self.config.momentum_lookback,
                "long_momentum_lookback": self.config.long_momentum_lookback,
                "momentum_skip_bars": self.config.momentum_skip_bars,
                "volatility_lookback": self.config.volatility_lookback,
                "value_lookback": self.config.value_lookback,
                "quality_lookback": self.config.quality_lookback,
                "carry_lookback": self.config.carry_lookback,
                "min_history": self.config.min_history,
                "top_n": self.config.top_n,
                "bottom_n": self.config.bottom_n,
                "long_gross_exposure": self.config.long_gross_exposure,
                "short_gross_exposure": self.config.short_gross_exposure,
                "factor_weights": self.config.factor_weights,
                "score_weighted_allocations": self.config.score_weighted_allocations,
            },
            "long_symbols": list(self.long_symbols),
            "short_symbols": list(self.short_symbols),
            "scores": [score.to_dict() for score in self.scores],
            "skipped_symbols": dict(self.skipped_symbols),
        }


def build_style_premia_ranking(
    data_by_symbol: Mapping[str, pd.DataFrame],
    as_of: str | pd.Timestamp | None = None,
    config: StylePremiaConfig | None = None,
) -> StylePremiaRankingReport:
    """Rank a cross-section by momentum, value proxy, quality, low-vol, and carry."""

    if not data_by_symbol:
        raise ValueError("Style premia ranking requires at least one symbol.")

    config = config or StylePremiaConfig()
    as_of_timestamp = _resolve_as_of(data_by_symbol, as_of)
    raw_rows = []
    skipped: dict[str, str] = {}

    for raw_symbol, raw_data in sorted(data_by_symbol.items()):
        symbol = str(raw_symbol).upper()
        data = _history_until(raw_data, as_of_timestamp)
        reason = _skip_reason(data, config)
        if reason:
            skipped[symbol] = reason
            continue
        raw_rows.append({"symbol": symbol, **_raw_metrics(data, config)})

    if not raw_rows:
        raise ValueError("No symbols had enough clean history for style premia ranking.")

    raw_frame = pd.DataFrame(raw_rows).set_index("symbol")
    raw_frame["blended_momentum"] = raw_frame[["momentum", "long_momentum"]].mean(axis=1, skipna=True)
    component_frame = pd.DataFrame(index=raw_frame.index)
    component_frame["momentum"] = _zscore(raw_frame["blended_momentum"])
    component_frame["value"] = _zscore(raw_frame["value_proxy"])
    component_frame["quality"] = _zscore(raw_frame["quality_proxy"])
    component_frame["low_volatility"] = _zscore(raw_frame["low_volatility_proxy"])
    component_frame["carry"] = _zscore(raw_frame["carry_proxy"])
    composite = _weighted_composite(component_frame, raw_frame, config)
    ranked_symbols = tuple(composite.sort_values(ascending=False).index)
    target_weights = _target_weights(composite, ranked_symbols, config)

    scores = []
    for rank, symbol in enumerate(ranked_symbols, start=1):
        raw_metrics = {
            column: _optional_float(raw_frame.loc[symbol, column])
            for column in raw_frame.columns
        }
        component_scores = {
            column: float(component_frame.loc[symbol, column])
            for column in component_frame.columns
        }
        scores.append(
            StylePremiaScore(
                symbol=symbol,
                rank=rank,
                composite_score=float(composite.loc[symbol]),
                target_weight=float(target_weights.get(symbol, 0.0)),
                component_scores=component_scores,
                raw_metrics=raw_metrics,
            )
        )

    return StylePremiaRankingReport(
        as_of=as_of_timestamp,
        config=config,
        scores=tuple(scores),
        skipped_symbols=skipped,
    )


def _resolve_as_of(data_by_symbol: Mapping[str, pd.DataFrame], as_of: str | pd.Timestamp | None) -> pd.Timestamp:
    if as_of is not None:
        return pd.Timestamp(as_of)
    latest_timestamps = []
    for data in data_by_symbol.values():
        if len(data.index):
            latest_timestamps.append(pd.Timestamp(data.index.max()))
    if not latest_timestamps:
        raise ValueError("Style premia ranking received only empty data frames.")
    return max(latest_timestamps)


def _history_until(data: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if data.empty:
        return data
    indexed = data.sort_index()
    return indexed.loc[indexed.index <= as_of].copy()


def _skip_reason(data: pd.DataFrame, config: StylePremiaConfig) -> str | None:
    if data.empty:
        return "empty_history"
    required_columns = {"Close", "Volume"}
    missing_columns = sorted(required_columns.difference(data.columns))
    if missing_columns:
        return f"missing_columns:{','.join(missing_columns)}"
    if len(data) < config.min_history:
        return "insufficient_history"
    if data["Close"].dropna().empty:
        return "missing_close"
    return None


def _raw_metrics(data: pd.DataFrame, config: StylePremiaConfig) -> dict[str, float | None]:
    close = data["Close"].astype(float)
    returns = close.pct_change()
    momentum = _lookback_return(close, config.momentum_lookback, config.momentum_skip_bars)
    long_momentum = _lookback_return(close, config.long_momentum_lookback, config.momentum_skip_bars)
    volatility = returns.tail(config.volatility_lookback).std() * (252**0.5)
    moving_average = close.tail(config.value_lookback).mean()
    value_proxy = -(close.iloc[-1] / moving_average - 1.0) if moving_average else None
    quality_window = close.tail(config.quality_lookback)
    quality_proxy = _quality_proxy(quality_window)
    carry_proxy = _carry_proxy(data, close, config)
    dollar_volume = float((data["Close"].astype(float) * data["Volume"].astype(float)).tail(config.carry_lookback).mean())

    return {
        "momentum": momentum,
        "long_momentum": long_momentum,
        "value_proxy": _optional_float(value_proxy),
        "quality_proxy": quality_proxy,
        "low_volatility_proxy": -float(volatility) if pd.notna(volatility) else None,
        "carry_proxy": carry_proxy,
        "realized_volatility": float(volatility) if pd.notna(volatility) else None,
        "average_dollar_volume": dollar_volume,
    }


def _lookback_return(close: pd.Series, lookback: int, skip_bars: int) -> float | None:
    end_offset = max(0, int(skip_bars))
    start_offset = int(lookback) + end_offset
    if len(close) <= start_offset:
        return None
    end_price = float(close.iloc[-1 - end_offset])
    start_price = float(close.iloc[-1 - start_offset])
    if start_price <= 0:
        return None
    return end_price / start_price - 1.0


def _quality_proxy(close: pd.Series) -> float | None:
    if len(close) < 2:
        return None
    total_move = abs(float(close.iloc[-1] / close.iloc[0] - 1.0))
    path_churn = close.pct_change().abs().sum()
    if not path_churn or pd.isna(path_churn):
        efficiency = 0.0
    else:
        efficiency = min(1.0, total_move / float(path_churn))
    running_high = close.cummax()
    drawdown = (close / running_high - 1.0).min()
    return float(efficiency + drawdown)


def _carry_proxy(data: pd.DataFrame, close: pd.Series, config: StylePremiaConfig) -> float | None:
    for column in ("Carry", "carry", "DividendYield", "dividend_yield", "Yield", "yield", "FundingRate", "funding_rate"):
        if column in data.columns and pd.notna(data[column].iloc[-1]):
            return float(data[column].iloc[-1])
    carry_return = close.pct_change(config.carry_lookback).iloc[-1]
    return float(carry_return) if pd.notna(carry_return) else None


def _zscore(values: pd.Series) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    mean = clean.mean(skipna=True)
    std = clean.std(skipna=True)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return ((clean - mean) / std).fillna(0.0)


def _weighted_composite(
    component_frame: pd.DataFrame,
    raw_frame: pd.DataFrame,
    config: StylePremiaConfig,
) -> pd.Series:
    composite = pd.Series(0.0, index=component_frame.index)
    used_weight = pd.Series(0.0, index=component_frame.index)
    raw_column_by_factor = {
        "momentum": "blended_momentum",
        "value": "value_proxy",
        "quality": "quality_proxy",
        "low_volatility": "low_volatility_proxy",
        "carry": "carry_proxy",
    }
    for factor, weight in config.factor_weights.items():
        raw_column = raw_column_by_factor[factor]
        has_factor = raw_frame[raw_column].notna()
        composite.loc[has_factor] += component_frame.loc[has_factor, factor] * weight
        used_weight.loc[has_factor] += abs(weight)
    used_weight = used_weight.replace(0.0, 1.0)
    return composite / used_weight


def _target_weights(
    composite: pd.Series,
    ranked_symbols: Sequence[str],
    config: StylePremiaConfig,
) -> dict[str, float]:
    weights = {symbol: 0.0 for symbol in ranked_symbols}
    longs = tuple(ranked_symbols[: max(0, config.top_n)])
    long_set = set(longs)
    short_candidates = tuple(symbol for symbol in ranked_symbols if symbol not in long_set)
    shorts = tuple(short_candidates[-max(0, config.bottom_n) :]) if config.bottom_n else tuple()
    weights.update(_side_weights(composite, longs, abs(config.long_gross_exposure), 1.0, config.score_weighted_allocations))
    weights.update(_side_weights(composite, shorts, abs(config.short_gross_exposure), -1.0, config.score_weighted_allocations))
    return weights


def _side_weights(
    composite: pd.Series,
    symbols: Sequence[str],
    gross_exposure: float,
    direction: float,
    score_weighted: bool,
) -> dict[str, float]:
    if not symbols or gross_exposure <= 0:
        return {}
    if not score_weighted:
        return {symbol: direction * gross_exposure / len(symbols) for symbol in symbols}
    magnitudes = {symbol: abs(float(composite.loc[symbol])) for symbol in symbols}
    total = sum(magnitudes.values())
    if total <= 0:
        return {symbol: direction * gross_exposure / len(symbols) for symbol in symbols}
    return {symbol: direction * gross_exposure * magnitudes[symbol] / total for symbol in symbols}


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
