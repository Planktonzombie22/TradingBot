import importlib as _importlib
import sys as _sys

from .core import Indicator
from .momentum import ROC, RSI, StochasticOscillator
from .structure import FairValueGap, LiquiditySweep, MarketStructureBreak, PivotPoints, SwingPoints
from .trend import (
    ADX,
    Aroon,
    ChoppinessIndex,
    DEMA,
    DonchianChannel,
    EfficiencyRatio,
    ElderRayIndex,
    EMA,
    IchimokuCloud,
    MACD,
    RollingZScore,
    SMA,
    SuperTrend,
    UlcerIndex,
    VortexIndicator,
)
from .volatility import ATR, BollingerBands, KeltnerChannel
from .volume import AnchoredVWAP, ChaikinMoneyFlow, MoneyFlowIndex, OBV, RelativeVolume, VWAP

__all__ = [
    "ADX",
    "Aroon",
    "AnchoredVWAP",
    "ATR",
    "BollingerBands",
    "ChaikinMoneyFlow",
    "ChoppinessIndex",
    "DEMA",
    "DonchianChannel",
    "EfficiencyRatio",
    "ElderRayIndex",
    "EMA",
    "FairValueGap",
    "IchimokuCloud",
    "Indicator",
    "KeltnerChannel",
    "LiquiditySweep",
    "MACD",
    "MarketStructureBreak",
    "MoneyFlowIndex",
    "OBV",
    "PivotPoints",
    "ROC",
    "RSI",
    "RollingZScore",
    "RelativeVolume",
    "SMA",
    "StochasticOscillator",
    "SwingPoints",
    "SuperTrend",
    "UlcerIndex",
    "VortexIndicator",
    "VWAP",
]

_MODULE_ALIASES = {
    "_smoothing": "core.smoothing",
    "adx": "trend.adx",
    "atr": "volatility.atr",
    "base": "core.base",
    "bollinger": "volatility.bollinger",
    "dema": "trend.dema",
    "donchian": "trend.donchian",
    "ema": "trend.ema",
    "keltner": "volatility.keltner",
    "macd": "trend.macd",
    "obv": "volume.obv",
    "price_action": "structure.price_action",
    "regime": "trend.regime",
    "roc": "momentum.roc",
    "rsi": "momentum.rsi",
    "sma": "trend.sma",
    "stochastic": "momentum.stochastic",
    "supertrend": "trend.supertrend",
    "volume_flow": "volume.flow",
}

for _old_module, _new_module in _MODULE_ALIASES.items():
    _module = _importlib.import_module(f"{__name__}.{_new_module}")
    _sys.modules[f"{__name__}.{_old_module}"] = _module
    globals()[_old_module] = _module

del _importlib, _sys, _MODULE_ALIASES, _old_module, _new_module, _module
