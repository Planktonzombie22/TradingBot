import argparse
import json
import time

from main import RuntimeTimeoutPolicy, RuntimeWatchdog, _paper_daemon_options, build_config, default_timeout_seconds, load_json_options, load_symbol_list, run_optimize_app, run_paper_broker_schedule_app, run_paper_session_app, run_replication_app, run_research_matrix_app, run_stream_app
from src.data import DataQualityValidator, sample_ohlcv
from src.reporting import render_backtest_html
from src.app import TradingApplication
from src.config import ExecutionConfig, MarketDataConfig, RuntimeConfig, StrategyConfig


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


def test_cli_timeout_defaults_are_shorter_for_runtime_than_research():
    assert default_timeout_seconds("paper-session") == 300.0
    assert default_timeout_seconds("paper-session-schedule") == 300.0
    assert default_timeout_seconds("paper-monitor") == 300.0
    assert default_timeout_seconds("paper-pilot") == 300.0
    assert default_timeout_seconds("optimize") == 900.0
    assert default_timeout_seconds("backtest") == 180.0


def test_runtime_watchdog_interrupts_then_forces_exit_when_job_stalls():
    events = []

    def interrupt_main():
        events.append("interrupt")

    def hard_exit(code):
        events.append(("exit", code))

    watchdog = RuntimeWatchdog(
        RuntimeTimeoutPolicy(seconds=0.01, grace_seconds=0.01),
        interrupt_main=interrupt_main,
        hard_exit=hard_exit,
    )
    watchdog.__enter__()
    try:
        deadline = time.time() + 0.50
        while len(events) < 2 and time.time() < deadline:
            time.sleep(0.005)
    finally:
        watchdog.cancel()

    assert watchdog.triggered
    assert events == ["interrupt", ("exit", 124)]


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


def test_paper_broker_schedule_app_can_score_existing_artifact_without_broker(tmp_path):
    proof = tmp_path / "proof.json"
    schedule = tmp_path / "schedule.json"
    proof.write_text(
        json.dumps(
            {
                "passed": True,
                "generated_at": "2026-01-05T15:00:00+00:00",
                "session": "REGULAR",
                "submitted": True,
                "reason": "passed",
            }
        ),
        encoding="utf-8",
    )
    app = TradingApplication(RuntimeConfig(data=MarketDataConfig(provider="sample", symbol="SPY")))
    args = argparse.Namespace(
        paper_proof_existing_artifact=str(proof),
        paper_proof_schedule_output=str(schedule),
    )

    run_paper_broker_schedule_app(
        app,
        args,
        broker_factory=lambda: (_ for _ in ()).throw(AssertionError("broker should not be touched")),
    )

    payload = json.loads(schedule.read_text(encoding="utf-8"))
    assert payload["passed"]
    assert payload["records"][0]["window_name"] == "market_open"


def test_paper_session_app_can_preview_micro_profile_without_broker_requirements(tmp_path, capsys):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            execution=ExecutionConfig(mode="paper"),
            strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
        )
    )
    args = argparse.Namespace(
        paper_profile="micro-notional",
        paper_profile_preview=True,
        submit_orders=False,
        store_dir=str(tmp_path),
        comparison_provider=None,
        recover_state=False,
        state_db_path=None,
        paper_proof_prior_dir=None,
        paper_proof_symbol_allowlist=None,
        max_daily_proof_submissions=None,
        paper_proof_kill_switch=False,
        repeated_reject_lockout_threshold=None,
    )

    run_paper_session_app(app, args)

    output = capsys.readouterr().out
    payload = json.loads(output[: output.rfind("}") + 1])
    assert payload["submitted"] is False
    assert payload["ready_for_submission"] is True
    assert payload["risk_budget"]["passed"] is True
    assert payload["risk_budget"]["session_notional"] <= 25.0
    assert 0.0 < payload["planned_orders"][0]["quantity"] < 1.0


def test_paper_daemon_profile_applies_bounded_monitoring_defaults(tmp_path):
    base_args = argparse.Namespace(
        paper_profile=None,
        paper_daemon_profile="micro-notional",
        paper_profile_preview=False,
        submit_orders=False,
        paper_daemon_interval_seconds=300.0,
        paper_daemon_max_iterations=None,
        paper_daemon_kill_switch=str(tmp_path / "daemon.kill"),
        paper_daemon_state_output=str(tmp_path / "state.json"),
        paper_daemon_heartbeat_output=str(tmp_path / "heartbeat.json"),
        paper_daemon_lock_path=str(tmp_path / "daemon.lock"),
        paper_daemon_lock_stale_seconds=1800.0,
        paper_daemon_artifact_root=str(tmp_path / "daemon"),
        paper_daemon_schedule_output=str(tmp_path / "schedule.json"),
        paper_daemon_report_output=str(tmp_path / "report.json"),
        paper_daemon_cleanup_each_iteration=False,
        paper_daemon_cleanup_submit=False,
        paper_daemon_cleanup_output=str(tmp_path / "cleanup.json"),
        paper_daemon_monitor_each_iteration=False,
        paper_daemon_monitor_output=str(tmp_path / "monitor.json"),
        paper_daemon_monitor_open_order_timeout_minutes=15.0,
        paper_daemon_data_parity_each_iteration=False,
        paper_daemon_data_parity_output=str(tmp_path / "parity.json"),
        paper_daemon_data_parity_max_close_drift_bps=5.0,
    )

    micro = _paper_daemon_options(base_args)
    sample = _paper_daemon_options(
        argparse.Namespace(
            **{
                **vars(base_args),
                "paper_daemon_profile": "sample-data",
                "paper_profile_preview": True,
            }
        )
    )

    assert micro.max_iterations == 3
    assert micro.submit_orders
    assert micro.cleanup_each_iteration
    assert micro.monitor_each_iteration
    assert micro.data_parity_each_iteration
    assert sample.interval_seconds == 0.0
    assert sample.max_iterations == 3
    assert not sample.submit_orders


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
