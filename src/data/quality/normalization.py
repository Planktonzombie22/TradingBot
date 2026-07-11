from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.models import Bar

from ..streams.events import MarketDataEvent, MarketDataEventType

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def normalize_ohlcv_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Return canonical historical OHLCV data used by strategies/backtests."""

    if data.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    rename_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    normalized = data.rename(columns={key: value for key, value in rename_map.items() if key in data.columns}).copy()
    if "Volume" not in normalized.columns:
        normalized["Volume"] = 0.0

    for column in OHLCV_COLUMNS:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    if not isinstance(normalized.index, pd.DatetimeIndex):
        normalized.index = pd.to_datetime(normalized.index, utc=True)
    normalized.index.name = "timestamp"
    return normalized[OHLCV_COLUMNS].sort_index()


def normalize_bar(symbol: str, payload: dict[str, Any]) -> MarketDataEvent:
    """Normalize provider bar payloads into the live-stream event contract."""

    timestamp = _parse_timestamp(payload.get("t") or payload.get("timestamp"))
    bar = Bar(
        timestamp=timestamp,
        open=float(payload.get("o", payload.get("open"))),
        high=float(payload.get("h", payload.get("high"))),
        low=float(payload.get("l", payload.get("low"))),
        close=float(payload.get("c", payload.get("close"))),
        volume=float(payload.get("v", payload.get("volume", 0.0))),
    )
    return MarketDataEvent(
        event_type=MarketDataEventType.BAR,
        symbol=symbol,
        timestamp=timestamp,
        bar=bar,
        payload=payload,
    )


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        timestamp = datetime.now(timezone.utc)
    return timestamp.astimezone(timezone.utc) if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
