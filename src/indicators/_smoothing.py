import pandas as pd


def wilder_rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (RMA) used by ATR, RSI, and ADX."""
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
