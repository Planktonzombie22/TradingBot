import pandas as pd

from src.indicators import (
    ADX,
    ATR,
    Aroon,
    AnchoredVWAP,
    BollingerBands,
    ChaikinMoneyFlow,
    ChoppinessIndex,
    DEMA,
    DonchianChannel,
    EMA,
    EfficiencyRatio,
    ElderRayIndex,
    FairValueGap,
    IchimokuCloud,
    KeltnerChannel,
    LiquiditySweep,
    MACD,
    MarketStructureBreak,
    MoneyFlowIndex,
    OBV,
    PivotPoints,
    ROC,
    RSI,
    RelativeVolume,
    SMA,
    StochasticOscillator,
    SwingPoints,
    SuperTrend,
    UlcerIndex,
    VWAP,
    VortexIndicator,
)


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


def test_price_action_indicators_detect_structure_and_gaps():
    data = pd.DataFrame(
        {
            "Open": [10, 10.5, 13, 12, 11, 14, 13, 12],
            "High": [11, 11.2, 14, 13, 12, 15, 14, 13],
            "Low": [9, 10, 12.5, 11, 10, 13.5, 12, 11],
            "Close": [10.5, 11, 13.5, 11.5, 11, 14.5, 12.5, 12],
            "Volume": [100, 110, 200, 150, 140, 250, 120, 130],
        },
        index=pd.date_range("2024-01-01", periods=8),
    )

    fvg = FairValueGap(data).calculate_all()
    swings = SwingPoints(data, left_bars=1, right_bars=1).calculate_all()
    sweeps = LiquiditySweep(data, lookback=3).calculate_all()
    structure = MarketStructureBreak(data, lookback=3).calculate_all()
    pivots = PivotPoints(data).calculate_all()

    assert fvg["BullishFVG"].any()
    assert {"FVGTop", "FVGBottom", "FVGMidpoint"}.issubset(fvg.columns)
    assert {"SwingHigh", "SwingLow"}.issubset(swings.columns)
    assert {"BullishLiquiditySweep", "BearishLiquiditySweep"}.issubset(sweeps.columns)
    assert {"BullishStructureBreak", "BearishStructureBreak"}.issubset(structure.columns)
    assert {"Pivot", "R1", "S1", "R2", "S2"}.issubset(pivots.columns)


def test_volume_flow_indicators_return_expected_outputs():
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

    assert VWAP(data).calculate().name == "VWAP"
    assert AnchoredVWAP(data, anchor_index=10).calculate().iloc[:10].isna().all()
    assert MoneyFlowIndex(data, period=14).calculate().name == "MFI"
    assert ChaikinMoneyFlow(data, period=20).calculate().name == "CMF"
    assert RelativeVolume(data, period=20).calculate().name == "RelativeVolume"


def test_regime_and_risk_shape_indicators_return_expected_outputs():
    data = pd.DataFrame(
        {
            "Open": range(100, 180),
            "High": range(102, 182),
            "Low": range(98, 178),
            "Close": range(100, 180),
            "Volume": [100 + i for i in range(80)],
        },
        index=pd.date_range("2024-01-01", periods=80),
    )

    assert {"AroonUp", "AroonDown", "AroonOscillator"}.issubset(Aroon(data).calculate_all().columns)
    assert {"VIPlus", "VIMinus", "VIDiff"}.issubset(VortexIndicator(data).calculate_all().columns)
    assert ChoppinessIndex(data).calculate().name == "ChoppinessIndex"
    assert EfficiencyRatio(data).calculate().dropna().between(0, 1).all()
    assert UlcerIndex(data).calculate().name == "UlcerIndex"
    assert {"BullPower", "BearPower", "ElderRay"}.issubset(ElderRayIndex(data).calculate_all().columns)
    assert {"TenkanSen", "KijunSen", "SenkouSpanA", "SenkouSpanB", "CloudBias"}.issubset(IchimokuCloud(data).calculate_all().columns)
