import json
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from src.config import AlpacaConfig
from src.models import Bar

from .interface import DataFeed


class AlpacaHistoricalDataFeed(DataFeed):
    """Historical bar data feed backed by Alpaca Market Data REST."""

    def __init__(self, config: AlpacaConfig):
        self.config = config

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
        query = {
            "timeframe": timeframe,
            "feed": self.config.feed,
            "limit": 10_000,
        }
        if start:
            query["start"] = start
        if end:
            query["end"] = end

        url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?{urlencode(query)}"
        request = Request(
            url,
            headers={
                "APCA-API-KEY-ID": self.config.api_key,
                "APCA-API-SECRET-KEY": self.config.secret_key,
            },
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _bars_payload_to_frame(payload.get("bars", []))

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
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
