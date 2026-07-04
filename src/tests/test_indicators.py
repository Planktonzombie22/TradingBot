import pandas as pd

from src.indicators import ADX, ATR, BollingerBands, DEMA, DonchianChannel, EMA, KeltnerChannel, MACD, OBV, ROC, RSI, SMA, StochasticOscillator, SuperTrend


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


def test_research_indicators_return_expected_shapes():
    data = pd.DataFrame(
        {
            "Open": range(100, 160),
            "High": range(101, 161),
            "Low": range(99, 159),
            "Close": range(100, 160),
            "Volume": [100 + i for i in range(60)],
        },
        index=pd.date_range("2024-01-01", periods=60),
    )

    assert EMA(data, period=10).calculate().name == "EMA_10"
    assert ROC(data, period=10).calculate().name == "ROC"
    assert OBV(data).calculate().iloc[-1] > 0
    assert {"MACD", "MACDSignal", "MACDHistogram"}.issubset(MACD(data).calculate_all().columns)
    assert {"MiddleBand", "UpperBand", "LowerBand", "PercentB"}.issubset(BollingerBands(data).calculate_all().columns)
    assert {"DonchianUpper", "DonchianLower", "DonchianMiddle"}.issubset(DonchianChannel(data).calculate_all().columns)
    assert {"StochK", "StochD"}.issubset(StochasticOscillator(data).calculate_all().columns)
    assert {"KeltnerUpper", "KeltnerLower", "KeltnerMiddle"}.issubset(KeltnerChannel(data).calculate_all().columns)
