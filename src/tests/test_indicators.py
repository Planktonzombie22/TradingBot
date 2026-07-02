import pandas as pd

from src.indicators import ADX, ATR, DEMA, RSI, SMA, SuperTrend


def sample_ohlcv():
    return pd.DataFrame(
        {
            "Open": [10, 11, 12, 13, 14, 15],
            "High": [11, 12, 13, 14, 15, 16],
            "Low": [9, 10, 11, 12, 13, 14],
            "Close": [10, 11, 12, 13, 14, 15],
            "Volume": [100] * 6,
        },
        index=pd.date_range("2024-01-01", periods=6),
    )


def test_moving_average_outputs_are_named_and_warmed_up():
    data = sample_ohlcv()

    sma = SMA(data, period=3).calculate()
    dema = DEMA(data, period=3).calculate()

    assert sma.name == "Close"
    assert dema.name == "DEMA"
    assert sma.iloc[-1] == 14
    assert pd.isna(dema.iloc[0])


def test_rsi_handles_one_directional_market():
    data = sample_ohlcv()

    rsi = RSI(data, period=3).calculate()

    assert rsi.name == "RSI"
    assert rsi.dropna().iloc[-1] == 100


def test_volatility_and_trend_indicators_return_expected_columns():
    data = sample_ohlcv()

    atr = ATR(data, period=3).calculate()
    adx = ADX(data, period=3).calculate_all()
    supertrend = SuperTrend(data, period=3, multiplier=2).calculate_all()

    assert atr.name == "ATR"
    assert {"+DI", "-DI", "DX", "ADX"}.issubset(adx.columns)
    assert {"SuperTrend", "UpperBand", "LowerBand", "Direction", "Flip"}.issubset(supertrend.columns)
