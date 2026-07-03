from datetime import date, datetime, timedelta, timezone

import pandas as pd

from src.data import (
    CorporateActionPolicy,
    CorporateActionSet,
    DataQualityValidator,
    DividendAction,
    PriceAdjustmentMode,
    SplitAction,
    SymbolChangeAction,
    events_from_ohlcv,
    normalize_bar,
    normalize_ohlcv_frame,
    sample_ohlcv,
)


def test_corporate_action_policy_split_adjusts_prices_and_volume():
    data = pd.DataFrame(
        {
            "Open": [100.0, 50.0],
            "High": [110.0, 55.0],
            "Low": [90.0, 45.0],
            "Close": [100.0, 50.0],
            "Volume": [1000.0, 2000.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    actions = CorporateActionSet(splits=[SplitAction("SPY", date(2024, 1, 2), ratio=2.0)])

    adjusted = CorporateActionPolicy(PriceAdjustmentMode.SPLIT_ADJUSTED).apply("SPY", data, actions)

    assert adjusted.iloc[0]["Close"] == 50.0
    assert adjusted.iloc[0]["Volume"] == 2000.0
    assert adjusted.iloc[1]["Close"] == 50.0


def test_corporate_action_policy_resolves_symbol_changes():
    actions = CorporateActionSet(symbol_changes=[SymbolChangeAction("OLD", "NEW", date(2024, 1, 2))])

    policy = CorporateActionPolicy()

    assert policy.resolve_symbol("OLD", date(2024, 1, 1), actions) == "OLD"
    assert policy.resolve_symbol("OLD", date(2024, 1, 2), actions) == "NEW"


def test_total_return_policy_adjusts_for_dividends():
    data = pd.DataFrame(
        {
            "Open": [100.0, 100.0],
            "High": [100.0, 100.0],
            "Low": [100.0, 100.0],
            "Close": [100.0, 100.0],
            "Volume": [1000.0, 1000.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    actions = CorporateActionSet(dividends=[DividendAction("SPY", date(2024, 1, 2), amount=1.0)])

    adjusted = CorporateActionPolicy(PriceAdjustmentMode.TOTAL_RETURN).apply("SPY", data, actions)

    assert adjusted.iloc[0]["Close"] == 99.0
    assert adjusted.iloc[1]["Close"] == 100.0


def test_quality_validator_flags_negative_volume_non_positive_prices_and_stale_events():
    data = sample_ohlcv(periods=3)
    data.loc[data.index[0], "Close"] = 0
    data.loc[data.index[1], "Volume"] = -1

    report = DataQualityValidator(stale_seconds=1).validate_ohlcv(data)

    assert any(issue.code == "NON_POSITIVE_PRICE" for issue in report.issues)
    assert any(issue.code == "NEGATIVE_VOLUME" for issue in report.issues)

    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    event = normalize_bar("SPY", {"timestamp": old, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1})
    event_report = DataQualityValidator(stale_seconds=1).validate_events([event])

    assert any(issue.code == "STALE_EVENT" for issue in event_report.issues)


def test_quality_validator_flags_out_of_order_live_events():
    first = normalize_bar("SPY", {"timestamp": "2024-01-02T14:31:00Z", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1})
    second = normalize_bar("SPY", {"timestamp": "2024-01-02T14:30:00Z", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1})

    report = DataQualityValidator().validate_events([first, second])

    assert any(issue.code == "OUT_OF_ORDER_EVENT" for issue in report.issues)


def test_historical_and_live_bar_normalization_share_schema():
    raw = pd.DataFrame(
        {"open": [1], "high": [2], "low": [1], "close": [2]},
        index=["2024-01-02T14:30:00Z"],
    )

    historical = normalize_ohlcv_frame(raw)
    live_event = next(iter(events_from_ohlcv("SPY", historical)))

    assert list(historical.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert live_event.bar.open == historical.iloc[0]["Open"]
    assert live_event.timestamp.tzinfo is not None
