import pandas as pd


def wilder_rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (RMA) used by ATR, RSI, and ADX."""
    if period <= 0:
        raise ValueError("Indicator period must be positive.")
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Standard exponential moving average with consistent validation."""
    if period <= 0:
        raise ValueError("Indicator period must be positive.")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()
