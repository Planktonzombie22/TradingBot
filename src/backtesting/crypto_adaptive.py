from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class CryptoAdaptiveSelectionConfig:
    momentum_lookback: int = 30
    sharpe_lookback: int = 30
    volatility_lookback: int = 30
    drawdown_lookback: int = 90
    liquidity_lookback: int = 20
    annualization_bars: int = 365
    top_n: int = 5
    min_rolling_sharpe: float = 0.15
    max_drawdown_allowed: float = -0.65
    min_average_dollar_volume: float = 0.0
    target_volatility: float = 0.45
    max_symbol_weight: float = 0.35
    cash_reserve: float = 0.10


@dataclass(frozen=True)
class CryptoAdaptiveAssetScore:
    symbol: str
    rank: int
    score: float
    target_weight: float
    momentum: float
    rolling_sharpe: float
    realized_volatility: float
    drawdown: float
    average_dollar_volume: float
    selected: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "rank": self.rank,
            "score": self.score,
            "target_weight": self.target_weight,
            "momentum": self.momentum,
            "rolling_sharpe": self.rolling_sharpe,
            "realized_volatility": self.realized_volatility,
            "drawdown": self.drawdown,
            "average_dollar_volume": self.average_dollar_volume,
            "selected": self.selected,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CryptoAdaptiveSelectionReport:
    as_of: pd.Timestamp
    config: CryptoAdaptiveSelectionConfig
    assets: tuple[CryptoAdaptiveAssetScore, ...]
    skipped_symbols: Mapping[str, str]

    @property
    def selected_symbols(self) -> tuple[str, ...]:
        return tuple(asset.symbol for asset in self.assets if asset.selected)

    @property
    def invested_weight(self) -> float:
        return sum(asset.target_weight for asset in self.assets if asset.selected)

    @property
    def cash_weight(self) -> float:
        return max(0.0, 1.0 - self.invested_weight)

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "selected_symbols": list(self.selected_symbols),
            "invested_weight": self.invested_weight,
            "cash_weight": self.cash_weight,
            "assets": [asset.to_dict() for asset in self.assets],
            "skipped_symbols": dict(self.skipped_symbols),
            "config": {
                "momentum_lookback": self.config.momentum_lookback,
                "sharpe_lookback": self.config.sharpe_lookback,
                "volatility_lookback": self.config.volatility_lookback,
                "drawdown_lookback": self.config.drawdown_lookback,
                "liquidity_lookback": self.config.liquidity_lookback,
                "annualization_bars": self.config.annualization_bars,
                "top_n": self.config.top_n,
                "min_rolling_sharpe": self.config.min_rolling_sharpe,
                "max_drawdown_allowed": self.config.max_drawdown_allowed,
                "min_average_dollar_volume": self.config.min_average_dollar_volume,
                "target_volatility": self.config.target_volatility,
                "max_symbol_weight": self.config.max_symbol_weight,
                "cash_reserve": self.config.cash_reserve,
            },
        }


def select_crypto_adaptive_universe(
    data_by_symbol: Mapping[str, pd.DataFrame],
    as_of: str | pd.Timestamp | None = None,
    config: CryptoAdaptiveSelectionConfig | None = None,
) -> CryptoAdaptiveSelectionReport:
    if not data_by_symbol:
        raise ValueError("Crypto adaptive selection requires at least one symbol.")

    config = config or CryptoAdaptiveSelectionConfig()
    as_of_timestamp = _resolve_as_of(data_by_symbol, as_of)
    rows = []
    skipped = {}
    for raw_symbol, raw_data in sorted(data_by_symbol.items()):
        symbol = str(raw_symbol).upper()
        data = _history_until(raw_data, as_of_timestamp)
        reason = _skip_reason(data, config)
        if reason:
            skipped[symbol] = reason
            continue
        rows.append({"symbol": symbol, **_metrics(data, config)})

    if not rows:
        raise ValueError("No crypto symbols had enough clean history for adaptive selection.")

    frame = pd.DataFrame(rows).set_index("symbol")
    frame["score"] = (
        _zscore(frame["momentum"]) * 0.40
        + _zscore(frame["rolling_sharpe"]) * 0.35
        + _zscore(-frame["realized_volatility"]) * 0.15
        + _zscore(frame["average_dollar_volume"]) * 0.10
    )
    ranked_symbols = tuple(frame["score"].sort_values(ascending=False).index)
    selected = _selected_symbols(frame, ranked_symbols, config)
    target_weights = _target_weights(frame, selected, config)

    assets = []
    for rank, symbol in enumerate(ranked_symbols, start=1):
        reason = _selection_reason(frame.loc[symbol], symbol in selected, config)
        assets.append(
            CryptoAdaptiveAssetScore(
                symbol=symbol,
                rank=rank,
                score=float(frame.loc[symbol, "score"]),
                target_weight=float(target_weights.get(symbol, 0.0)),
                momentum=float(frame.loc[symbol, "momentum"]),
                rolling_sharpe=float(frame.loc[symbol, "rolling_sharpe"]),
                realized_volatility=float(frame.loc[symbol, "realized_volatility"]),
                drawdown=float(frame.loc[symbol, "drawdown"]),
                average_dollar_volume=float(frame.loc[symbol, "average_dollar_volume"]),
                selected=symbol in selected,
                reason=reason,
            )
        )

    return CryptoAdaptiveSelectionReport(
        as_of=as_of_timestamp,
        config=config,
        assets=tuple(assets),
        skipped_symbols=skipped,
    )


def _resolve_as_of(data_by_symbol: Mapping[str, pd.DataFrame], as_of: str | pd.Timestamp | None) -> pd.Timestamp:
    if as_of is not None:
        return pd.Timestamp(as_of)
    timestamps = [pd.Timestamp(data.index.max()) for data in data_by_symbol.values() if len(data.index)]
    if not timestamps:
        raise ValueError("Crypto adaptive selection received only empty data frames.")
    return max(timestamps)


def _history_until(data: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if data.empty:
        return data
    indexed = data.sort_index()
    return indexed.loc[indexed.index <= as_of].copy()


def _skip_reason(data: pd.DataFrame, config: CryptoAdaptiveSelectionConfig) -> str | None:
    if data.empty:
        return "empty_history"
    missing = sorted({"Close", "Volume"}.difference(data.columns))
    if missing:
        return f"missing_columns:{','.join(missing)}"
    required = max(
        config.momentum_lookback,
        config.sharpe_lookback,
        config.volatility_lookback,
        config.drawdown_lookback,
        config.liquidity_lookback,
    )
    if len(data) <= required:
        return "insufficient_history"
    if data["Close"].dropna().empty:
        return "missing_close"
    return None


def _metrics(data: pd.DataFrame, config: CryptoAdaptiveSelectionConfig) -> dict[str, float]:
    close = data["Close"].astype(float)
    volume = data["Volume"].astype(float)
    returns = close.pct_change()
    momentum = close.iloc[-1] / close.iloc[-1 - config.momentum_lookback] - 1.0
    sharpe_vol = returns.tail(config.sharpe_lookback).std()
    rolling_sharpe = 0.0 if not sharpe_vol or pd.isna(sharpe_vol) else returns.tail(config.sharpe_lookback).mean() / sharpe_vol * (config.annualization_bars**0.5)
    realized_volatility = returns.tail(config.volatility_lookback).std() * (config.annualization_bars**0.5)
    rolling_high = close.tail(config.drawdown_lookback).max()
    drawdown = close.iloc[-1] / rolling_high - 1.0
    average_dollar_volume = (close * volume).tail(config.liquidity_lookback).mean()
    return {
        "momentum": float(momentum),
        "rolling_sharpe": float(rolling_sharpe),
        "realized_volatility": float(realized_volatility) if pd.notna(realized_volatility) else 0.0,
        "drawdown": float(drawdown),
        "average_dollar_volume": float(average_dollar_volume),
    }


def _selected_symbols(frame: pd.DataFrame, ranked_symbols: tuple[str, ...], config: CryptoAdaptiveSelectionConfig) -> tuple[str, ...]:
    selected = []
    for symbol in ranked_symbols:
        row = frame.loc[symbol]
        if row["rolling_sharpe"] < config.min_rolling_sharpe:
            continue
        if row["drawdown"] < config.max_drawdown_allowed:
            continue
        if row["average_dollar_volume"] < config.min_average_dollar_volume:
            continue
        selected.append(symbol)
        if len(selected) >= config.top_n:
            break
    return tuple(selected)


def _target_weights(frame: pd.DataFrame, selected: tuple[str, ...], config: CryptoAdaptiveSelectionConfig) -> dict[str, float]:
    available = max(0.0, 1.0 - config.cash_reserve)
    if not selected or available <= 0:
        return {}
    raw_weights = {}
    for symbol in selected:
        volatility = max(float(frame.loc[symbol, "realized_volatility"]), 0.0001)
        raw_weights[symbol] = min(config.max_symbol_weight, config.target_volatility / volatility / len(selected))
    total = sum(raw_weights.values())
    if total <= available:
        return raw_weights
    scale = available / total
    return {symbol: weight * scale for symbol, weight in raw_weights.items()}


def _selection_reason(row: pd.Series, selected: bool, config: CryptoAdaptiveSelectionConfig) -> str:
    if selected:
        return "selected"
    if row["rolling_sharpe"] < config.min_rolling_sharpe:
        return "sharpe_below_threshold"
    if row["drawdown"] < config.max_drawdown_allowed:
        return "drawdown_gate"
    if row["average_dollar_volume"] < config.min_average_dollar_volume:
        return "liquidity_below_threshold"
    return "ranked_below_cutoff"


def _zscore(values: pd.Series) -> pd.Series:
    mean = values.mean()
    std = values.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return ((values - mean) / std).fillna(0.0)
