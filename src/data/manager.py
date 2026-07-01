from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.config import MarketDataConfig

from .interface import DataFeed


@dataclass
class MarketDataManager:
    """Coordinates validation and retrieval around a concrete data feed."""

    feed: DataFeed

    def historical(self, config: MarketDataConfig) -> pd.DataFrame:
        data = self.feed.get_historical(
            symbol=config.symbol,
            start=config.start,
            end=config.end,
            interval=config.interval,
            period=config.period,
        )
        return self._normalize_ohlcv(data, config.symbol)

    @staticmethod
    def _normalize_ohlcv(data: pd.DataFrame, symbol: Optional[str] = None) -> pd.DataFrame:
        if data.empty:
            raise ValueError(f"No historical data returned for {symbol or 'requested symbol'}.")

        required = {"Open", "High", "Low", "Close"}
        missing = required.difference(data.columns)
        if missing:
            raise ValueError(f"Historical data is missing required OHLC columns: {sorted(missing)}")

        normalized = data.copy()
        if "Volume" not in normalized.columns:
            normalized["Volume"] = 0.0
        return normalized.sort_index()
