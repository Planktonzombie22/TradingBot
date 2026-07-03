from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.config import AlpacaConfig, MarketDataConfig
from src.utils.retry import RetryPolicy

from .alpaca import AlpacaHistoricalDataFeed
from .alpaca_stream import AlpacaMarketDataStream
from .interface import DataFeed
from .normalization import normalize_ohlcv_frame
from .quality import DataQualityValidator
from .sample import events_from_ohlcv, sample_ohlcv
from .stream import MarketDataStream, ReplayMarketDataStream, YFinancePollingStream


@dataclass
class MarketDataManager:
    """Coordinates validation and retrieval around a concrete data feed."""

    feed: DataFeed
    alpaca: AlpacaConfig = AlpacaConfig()
    retry_policy: RetryPolicy = RetryPolicy()
    quality_validator: DataQualityValidator = DataQualityValidator()

    def historical(self, config: MarketDataConfig) -> pd.DataFrame:
        if config.provider.lower() == "sample":
            return sample_ohlcv(config.symbol)
        if config.provider.lower() == "alpaca":
            data = self.retry_policy.run(
                lambda: AlpacaHistoricalDataFeed(self.alpaca).get_historical(
                    symbol=config.symbol,
                    start=config.start,
                    end=config.end,
                    interval=config.interval,
                    period=config.period,
                )
            )
            return self._normalize_ohlcv(data, config.symbol)

        data = self.retry_policy.run(
            lambda: self.feed.get_historical(
                symbol=config.symbol,
                start=config.start,
                end=config.end,
                interval=config.interval,
                period=config.period,
            )
        )
        return self._normalize_ohlcv(data, config.symbol)

    def stream(self, config: MarketDataConfig, alpaca: AlpacaConfig) -> MarketDataStream:
        provider = config.provider.lower()
        if provider == "sample":
            data = sample_ohlcv(config.symbol)
            return ReplayMarketDataStream(events_from_ohlcv(config.symbol, data))
        if provider.lower() == "alpaca":
            return AlpacaMarketDataStream(alpaca)
        if provider.lower() == "yfinance":
            return YFinancePollingStream()
        raise ValueError(f"Unsupported market data stream provider: {provider}")

    @staticmethod
    def _normalize_ohlcv(data: pd.DataFrame, symbol: Optional[str] = None) -> pd.DataFrame:
        if data.empty:
            raise ValueError(f"No historical data returned for {symbol or 'requested symbol'}.")

        required = {"Open", "High", "Low", "Close"}
        missing = required.difference(data.columns)
        if missing:
            raise ValueError(f"Historical data is missing required OHLC columns: {sorted(missing)}")

        normalized = normalize_ohlcv_frame(data)
        report = DataQualityValidator().validate_ohlcv(normalized)
        if not report.passed:
            messages = "; ".join(issue.message for issue in report.issues if issue.severity == "ERROR")
            raise ValueError(f"Historical data quality check failed: {messages}")
        return normalized
