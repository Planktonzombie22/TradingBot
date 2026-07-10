import argparse
import json

from main import build_config, load_json_options, load_symbol_list, run_optimize_app, run_replication_app, run_research_matrix_app, run_stream_app
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
        start="2024-01-01T00:00:00Z",
        end="2024-12-31T00:00:00Z",
        strategy="buyHold",
        strategy_params='{"stop_percent":0.03}',
        strategy_params_file=None,
    )

    config = build_config(args)

    assert config.data.provider == "sample"
    assert config.data.start == "2024-01-01T00:00:00Z"
    assert config.data.end == "2024-12-31T00:00:00Z"
    assert config.strategy.name == "buyHold"
    assert config.strategy.params == {"stop_percent": 0.03}


def test_optimize_app_writes_ranked_artifacts(tmp_path):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )

    run_optimize_app(app, json.dumps({"stop_percent": [0.03, 0.05]}), "total_return", store_dir=str(tmp_path))

    path = tmp_path / "optimization-results.jsonl"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["rank"] == 1


def test_load_json_options_from_file(tmp_path):
    path = tmp_path / "grid.json"
    path.write_text(json.dumps({"adx_minimum": [20, 25]}), encoding="utf-8")

    grid = load_json_options(path=str(path))

    assert grid == {"adx_minimum": [20, 25]}


def test_stream_app_can_flatten_on_stop(tmp_path):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )

    engine = run_stream_app(app, store_dir=str(tmp_path), label="Paper", flatten_on_stop=True)

    assert engine.account_state.quantity("SPY") == 0


def test_load_symbol_list_dedupes_and_limits(tmp_path):
    path = tmp_path / "symbols.json"
    path.write_text(json.dumps({"symbols": ["SPY", "qqq", "SPY", "IWM"]}), encoding="utf-8")

    symbols = load_symbol_list("DIA,spy", str(path), max_symbols=3)

    assert symbols == ["DIA", "SPY", "QQQ"]


def test_research_matrix_app_writes_summary(tmp_path):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "name": "cli_matrix",
                "groups": [
                    {
                        "name": "sample_stocks",
                        "asset_class": "stocks",
                        "provider": "sample",
                        "symbols": ["SPY", "QQQ"],
                        "intervals": ["1d"],
                        "windows": [{"name": "sample", "period": "1y"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "matrix-summary.json"
    args = argparse.Namespace(
        research_matrix_file=str(matrix_path),
        strategies="buyHold",
        strategy="buyHold",
        strategy_params="{}",
        strategy_params_file=None,
        strategy_param_dir="configs/strategies",
        period="2y",
        store_dir=str(tmp_path / "runs"),
        matrix_output=str(output),
        max_symbols=1,
    )

    run_research_matrix_app(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["matrix_name"] == "cli_matrix"
    assert payload["completed"] == 1


def test_replication_app_writes_published_comparison(tmp_path):
    data_path = tmp_path / "goog.csv"
    data_path.write_text(
        "\n".join(
            [
                ",Open,High,Low,Close,Volume",
                "2024-01-01,10,11,9,10,1000",
                "2024-01-02,11,12,10,11,1000",
                "2024-01-03,12,13,11,12,1000",
                "2024-01-04,11,12,10,11,1000",
                "2024-01-05,10,11,9,10,1000",
                "2024-01-06,9,10,8,9,1000",
                "2024-01-07,10,11,9,10,1000",
                "2024-01-08,11,12,10,11,1000",
            ]
        ),
        encoding="utf-8",
    )
    suite_path = tmp_path / "replication.json"
    suite_path.write_text(
        json.dumps(
            {
                "name": "test_replication",
                "symbol": "GOOG",
                "data_source": str(data_path),
                "profiles": [{"name": "test_profile", "margin_ratio": 2}],
                "references": [
                    {
                        "name": "tiny_sma_cross",
                        "strategy": "publishedSmaCross",
                        "params": {"fast_period": 2, "slow_period": 3, "signal_delay_bars": 1},
                        "published_return_pct": 0.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "replication-output.json"
    args = argparse.Namespace(replication_file=str(suite_path), replication_output=str(output))

    run_replication_app(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["name"] == "test_replication"
    assert payload["rows"][0]["name"] == "tiny_sma_cross"
    assert payload["rows"][0]["ours"]["valid"]
