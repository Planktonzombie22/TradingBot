import argparse

from main import build_config
from src.data import DataQualityValidator, sample_ohlcv
from src.reporting import render_backtest_html
from src.app import TradingApplication
from src.config import MarketDataConfig, RuntimeConfig, StrategyConfig


def test_data_quality_detects_invalid_ohlc():
    data = sample_ohlcv(periods=5)
    data.loc[data.index[0], "High"] = 1

    report = DataQualityValidator().validate_ohlcv(data)

    assert not report.passed
    assert any(issue.code == "INVALID_OHLC" for issue in report.issues)


def test_html_report_contains_summary():
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )
    result = app.run_backtest()

    html = render_backtest_html(result)

    assert "TradingBot Backtest Report" in html
    assert "Total PnL" in html


def test_cli_config_accepts_new_modes_indirectly():
    args = argparse.Namespace(
        symbol="SPY",
        provider="sample",
        period="2y",
        interval="1d",
        strategy="buyHold",
    )

    config = build_config(args)

    assert config.data.provider == "sample"
    assert config.strategy.name == "buyHold"
