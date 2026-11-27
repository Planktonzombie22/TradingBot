# Indicators Package Layout

- `core/`: base indicator interface and smoothing helpers.
- `trend/`: moving averages, trend strength, regime/trend classifiers, channels, SuperTrend, and Hurst persistence/cycle estimates.
- `momentum/`: RSI, ROC, stochastic oscillator, and related momentum tools.
- `volatility/`: ATR, Bollinger Bands, Keltner Channels, and range/volatility helpers.
- `volume/`: OBV, VWAP, anchored VWAP, MFI, CMF, relative volume, close-location value, volume pressure, and absorption ratio.
- `structure/`: price-action and market-structure concepts such as FVGs, liquidity sweeps, pivots, and swings.

Strategies can keep using `from src.indicators import RSI, ATR, ...`; direct legacy paths remain aliased.
