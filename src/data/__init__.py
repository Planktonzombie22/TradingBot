import importlib as _importlib
import sys as _sys

from .providers import AlpacaHistoricalDataFeed, DataFeed, YFinanceDataFeed
from .quality import (
    CorporateActionPolicy,
    CorporateActionSet,
    DataDriftIssue,
    DataDriftPolicy,
    DataDriftReport,
    DataQualityIssue,
    DataQualityReport,
    DataQualityValidator,
    DataSourceSnapshot,
    DividendAction,
    HistoricalDataCache,
    OHLCV_COLUMNS,
    PriceAdjustmentMode,
    SplitAction,
    SymbolChangeAction,
    compare_live_data_sources,
    compare_many_live_data_sources,
    normalize_bar,
    normalize_ohlcv_frame,
)
from .runtime import MarketDataManager, MarketSession, MarketSessionCalendar, MarketSessionPolicy, UniverseConfig, UniverseLoader
from .streams import MarketDataEvent, MarketDataEventType, MarketDataHandler, MarketDataStream, ReplayMarketDataStream, YFinancePollingStream
from .streams.alpaca_stream import AlpacaMarketDataStream, StreamHealth
from .streams.sample import bars_from_ohlcv, events_from_ohlcv, sample_ohlcv

__all__ = [
    "AlpacaMarketDataStream",
    "AlpacaHistoricalDataFeed",
    "CorporateActionPolicy",
    "CorporateActionSet",
    "DataDriftIssue",
    "DataDriftPolicy",
    "DataDriftReport",
    "DataFeed",
    "DividendAction",
    "MarketDataEvent",
    "MarketDataEventType",
    "MarketDataHandler",
    "MarketDataManager",
    "MarketDataStream",
    "MarketSession",
    "MarketSessionCalendar",
    "MarketSessionPolicy",
    "HistoricalDataCache",
    "OHLCV_COLUMNS",
    "PriceAdjustmentMode",
    "DataQualityIssue",
    "DataQualityReport",
    "DataQualityValidator",
    "DataSourceSnapshot",
    "ReplayMarketDataStream",
    "SplitAction",
    "StreamHealth",
    "SymbolChangeAction",
    "UniverseConfig",
    "UniverseLoader",
    "bars_from_ohlcv",
    "compare_live_data_sources",
    "compare_many_live_data_sources",
    "events_from_ohlcv",
    "normalize_bar",
    "normalize_ohlcv_frame",
    "sample_ohlcv",
    "YFinanceDataFeed",
    "YFinancePollingStream",
]

_MODULE_ALIASES = {
    "alpaca": "providers.alpaca",
    "alpaca_stream": "streams.alpaca_stream",
    "cache": "quality.cache",
    "calendar": "runtime.calendar",
    "corporate_actions": "quality.corporate_actions",
    "events": "streams.events",
    "interface": "providers.interface",
    "manager": "runtime.manager",
    "normalization": "quality.normalization",
    "drift": "quality.drift",
    "sample": "streams.sample",
    "stream": "streams.stream",
    "universe": "runtime.universe",
    "yfinance": "providers.yfinance",
}

for _old_module, _new_module in _MODULE_ALIASES.items():
    _module = _importlib.import_module(f"{__name__}.{_new_module}")
    _sys.modules[f"{__name__}.{_old_module}"] = _module
    globals()[_old_module] = _module

del _importlib, _sys, _MODULE_ALIASES, _old_module, _new_module, _module
