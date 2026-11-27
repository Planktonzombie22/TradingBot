from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from urllib.parse import urlencode

import pandas as pd

from src.config import AlpacaConfig
from src.models import Bar
from src.utils.alpaca_rest import AlpacaRestClient

from .interface import DataFeed
from ..quality.cache import HistoricalDataCache
from ..quality.normalization import normalize_ohlcv_frame


class AlpacaHistoricalDataFeed(DataFeed):
    """Historical bar data feed backed by Alpaca Market Data REST."""

    cache_provider_key = "alpaca-adjusted-all"

    def __init__(self, config: AlpacaConfig, cache: Optional[HistoricalDataCache] = None):
        self.config = config
        self.client = AlpacaRestClient(config)
        self.cache = cache

    def get_historical(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        interval: str = "1d",
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        self._validate_credentials()
        timeframe = _to_alpaca_timeframe(interval)
        effective_start = start or _period_to_start(period)
        effective_end = end
        if self.cache is not None:
            cached = self.cache.read(self.cache_provider_key, symbol, timeframe, effective_start, effective_end)
            if cached is not None:
                return cached

        query = {
            "timeframe": timeframe,
            "feed": self.config.feed,
            "adjustment": "all",
            "limit": 10_000,
        }
        if effective_start:
            query["start"] = effective_start
        if effective_end:
            query["end"] = effective_end

        bars: list[dict] = []
        page_token = None
        while True:
            page_query = dict(query)
            if page_token:
                page_query["page_token"] = page_token
            url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?{urlencode(page_query)}"
            payload = self.client.request("GET", url)
            bars.extend(payload.get("bars") or [])
            page_token = payload.get("next_page_token")
            if not page_token:
                break

        data = normalize_ohlcv_frame(_bars_payload_to_frame(bars))
        if self.cache is not None and not data.empty:
            self.cache.write(self.cache_provider_key, symbol, timeframe, data, effective_start, effective_end)
        return data

    def get_stream(self, symbol: str) -> Iterable[Bar]:
        raise NotImplementedError("Use AlpacaMarketDataStream for live streaming.")

    def _validate_credentials(self) -> None:
        if not self.config.api_key or not self.config.secret_key:
            raise ValueError("Alpaca API credentials are missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env.")


def _to_alpaca_timeframe(interval: str) -> str:
    mapping = {
        "1m": "1Min",
        "5m": "5Min",
        "15m": "15Min",
        "1h": "1Hour",
        "1d": "1Day",
    }
    return mapping.get(interval, interval)


def _period_to_start(period: Optional[str], now: Optional[datetime] = None) -> Optional[str]:
    if not period:
        return None
    text = period.strip().lower()
    if len(text) < 2 or not text[:-1].isdigit():
        return None
    amount = int(text[:-1])
    unit = text[-1]
    days_by_unit = {
        "d": 1,
        "w": 7,
        "m": 31,
        "y": 365,
    }
    if unit not in days_by_unit or amount <= 0:
        return None
    anchor = now or datetime.now(timezone.utc)
    return (anchor - timedelta(days=amount * days_by_unit[unit])).isoformat()


def _bars_payload_to_frame(bars: list[dict]) -> pd.DataFrame:
    rows = []
    for bar in bars:
        rows.append(
            {
                "timestamp": _parse_timestamp(bar["t"]),
                "Open": float(bar["o"]),
                "High": float(bar["h"]),
                "Low": float(bar["l"]),
                "Close": float(bar["c"]),
                "Volume": float(bar.get("v", 0.0)),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    return normalize_ohlcv_frame(pd.DataFrame(rows).set_index("timestamp").sort_index())


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
