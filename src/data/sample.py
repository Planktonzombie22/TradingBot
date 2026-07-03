from datetime import datetime
from typing import Iterable

import numpy as np
import pandas as pd

from src.models import Bar

from .events import MarketDataEvent
from .normalization import normalize_bar, normalize_ohlcv_frame


def sample_ohlcv(
    symbol: str = "SPY",
    periods: int = 160,
    start: str = "2024-01-01",
    freq: str = "D",
) -> pd.DataFrame:
    """Deterministic OHLCV data for demos, tests, and offline smoke runs."""

    index = pd.date_range(start=start, periods=periods, freq=freq)
    x = np.arange(periods, dtype=float)
    trend = 100 + x * 0.12
    cycle = np.sin(x / 6) * 2.5
    close = trend + cycle
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + 0.8
    low = np.minimum(open_, close) - 0.8
    volume = 1_000_000 + (np.cos(x / 4) * 50_000).astype(int)

    return normalize_ohlcv_frame(pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    ))


def bars_from_ohlcv(symbol: str, data: pd.DataFrame) -> Iterable[Bar]:
    for timestamp, row in data.iterrows():
        ts = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
        yield Bar(
            timestamp=ts,
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=float(row.get("Volume", 0.0)),
        )


def events_from_ohlcv(symbol: str, data: pd.DataFrame) -> Iterable[MarketDataEvent]:
    for bar in bars_from_ohlcv(symbol, data):
        yield normalize_bar(
            symbol,
            {
                "timestamp": bar.timestamp if isinstance(bar.timestamp, datetime) else pd.Timestamp(bar.timestamp).to_pydatetime(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            },
        )
