import pytest
import pandas as pd

from src.backtesting import (
    BatchBacktestJob,
    BatchBacktestRunner,
    BulkBacktestRecord,
    ResearchFilterConfig,
    EnsembleAllocationPolicy,
    StrategySelectionPolicy,
    activate_strategies_for_regime,
    benchmark_relative_report,
    build_ensemble_allocation,
    build_symbol_scorecards,
    classify_market_regime,
    classify_regime_universe,
    evaluate_research_filters,
    expand_research_matrix,
    load_research_matrix,
    research_matrix_from_dict,
    run_bulk_backtests,
    grid_search,
    overfitting_report,
    rank_optimization_results,
    run_research_matrix,
    run_walk_forward,
    select_strategies_against_benchmark,
)
from src.data import sample_ohlcv
from src.storage import JsonlStore
from src.strategies import validate_strategy_params
from src.strategies.buy_hold import BuyAndHoldStrategy


def test_strategy_parameter_validation_rejects_unknown_params():
    with pytest.raises(ValueError):
        validate_strategy_params("buyHold", {"unknown": 1})


def test_walk_forward_runs_multiple_test_windows():
    data = sample_ohlcv(periods=80)

    windows = run_walk_forward(
        data=data,
        strategy_factory=lambda: BuyAndHoldStrategy("SPY"),
        train_size=20,
        test_size=20,
    )

    assert len(windows) == 3
    assert all(window.result.metrics["ending_equity"] > 0 for window in windows)


def test_grid_search_returns_sorted_results():
    data = sample_ohlcv(periods=40)

    results = grid_search(
        strategy_name="buyHold",
        symbol="SPY",
        data=data,
        param_grid={"stop_percent": [0.03, 0.05]},
    )

    assert len(results) == 2
    assert results[0].score >= results[1].score


def test_optimization_ranking_and_overfitting_report():
    data = sample_ohlcv(periods=60)
    results = grid_search(
        strategy_name="buyHold",
        symbol="SPY",
        data=data,
        param_grid={"stop_percent": [0.03, 0.05]},
    )

    ranked = rank_optimization_results(results)
    report = overfitting_report(results[0].result, results[-1].result, min_trades=1)

    assert len(ranked) == 2
    assert "sharpe" in ranked[0].rank_metrics()
    assert report.minimum_trade_count_met


def test_batch_backtest_runner_skips_completed_jobs_and_writes_artifacts(tmp_path):
    data = {"SPY": sample_ohlcv("SPY", periods=40), "QQQ": sample_ohlcv("QQQ", periods=40)}
    jobs = [
        BatchBacktestJob("SPY", "buyHold", {"stop_percent": 0.05}),
        BatchBacktestJob("QQQ", "buyHold", {"stop_percent": 0.05}),
    ]
    runner = BatchBacktestRunner(JsonlStore(tmp_path))

    summary = runner.run(
        jobs,
        data=data,
        strategy_factory=lambda symbol, params: BuyAndHoldStrategy(symbol, **params),
        completed_keys=[jobs[0].key],
    )

    assert summary.completed == 1
    assert summary.skipped == 1
    assert (tmp_path / "batch-results.jsonl").exists()


def test_bulk_backtests_summarize_multiple_strategies(tmp_path):
    data = {
        "SPY": sample_ohlcv("SPY", periods=80),
        "QQQ": sample_ohlcv("QQQ", periods=80),
    }

    report = run_bulk_backtests(
        symbols=["SPY", "QQQ"],
        strategies=["buyHold", "meanReversion"],
        data_loader=lambda symbol: data[symbol],
        strategy_params={"buyHold": {"stop_percent": 0.05}},
        store=JsonlStore(tmp_path),
    )

    assert report.completed == 4
    assert report.failed == 0
    assert len(report.strategy_summary()) == 2
    assert (tmp_path / "bulk-results.jsonl").exists()


def test_strategy_selection_chooses_only_benchmark_relative_edges():
    records = [
        _bulk_record("SPY", "buyHold", 0.10, -0.20, trades=1),
        _bulk_record("SPY", "meanReversion", 0.18, -0.18, trades=5),
        _bulk_record("QQQ", "buyHold", 0.25, -0.22, trades=1),
        _bulk_record("QQQ", "meanReversion", 0.12, -0.10, trades=4),
    ]

    report = select_strategies_against_benchmark(records)
    selections = {selection.symbol: selection for selection in report.selections}

    assert selections["SPY"].selected_strategy == "meanReversion"
    assert selections["SPY"].action == "trade_strategy"
    assert selections["QQQ"].selected_strategy == "buyHold"
    assert selections["QQQ"].action == "use_benchmark"
    assert report.summary()["selected_strategy_counts"]["buyHold"] == 1


def test_strategy_selection_rejects_deep_drawdown_even_with_high_return():
    records = [
        _bulk_record("UNG", "buyHold", 0.20, -0.25, trades=1),
        _bulk_record("UNG", "vwapValueReversion", 0.80, -0.85, trades=3),
    ]

    report = select_strategies_against_benchmark(
        records,
        StrategySelectionPolicy(max_strategy_drawdown=-0.60),
    )

    assert report.selections[0].selected_strategy == "buyHold"
    comparison = report.comparisons[0]
    assert comparison.decision == "reject"
    assert comparison.reason == "strategy_drawdown_too_deep"


def test_benchmark_relative_report_summarizes_excess_return_and_capture():
    records = [
        _bulk_record("SPY", "buyHold", 0.10, -0.20, trades=1),
        _bulk_record("SPY", "meanReversion", 0.18, -0.18, trades=5),
        _bulk_record("QQQ", "buyHold", 0.20, -0.25, trades=1),
        _bulk_record("QQQ", "meanReversion", 0.16, -0.12, trades=4),
        _bulk_record("TLT", "buyHold", -0.05, -0.15, trades=1),
        _bulk_record("TLT", "meanReversion", 0.02, -0.08, trades=2),
    ]

    report = benchmark_relative_report(records)
    summary = report.strategy_summary()[0]
    payload = report.to_dict()

    assert summary.strategy == "meanReversion"
    assert round(summary.average_excess_return, 4) == round((0.08 - 0.04 + 0.07) / 3, 4)
    assert summary.upside_capture is not None
    assert summary.downside_capture is not None
    assert summary.tail_risk == -0.18
    assert payload["strategy_summary"][0]["average_trade_efficiency"] > 0
    assert payload["selection"]["summary"]["comparisons"] == 3


def test_market_regime_classifier_identifies_trend_and_macro_sensitivity():
    data = _ohlcv_from_closes([100 + i for i in range(90)], volume=1_000_000)

    profile = classify_market_regime(data, "TLT")

    assert profile.trend_state == "trending"
    assert profile.trend_direction == "up"
    assert profile.macro_sensitivity == "high"
    assert "trend_following" in profile.eligible_modes
    assert profile.to_dict()["symbol"] == "TLT"


def test_market_regime_classifier_identifies_range_bound_markets():
    closes = [100 + (1 if i % 2 == 0 else -1) for i in range(90)]
    data = _ohlcv_from_closes(closes, volume=500_000)

    profile = classify_market_regime(data, "SPY")
    universe = classify_regime_universe({"spy": data})

    assert profile.trend_state == "range_bound"
    assert profile.trend_direction == "flat"
    assert "mean_reversion" in profile.eligible_modes
    assert universe["SPY"].trend_state == "range_bound"


def test_strategy_activation_gates_systems_by_regime_modes():
    trending = classify_market_regime(_ohlcv_from_closes([100 + i for i in range(90)], volume=1_000_000), "SPY")
    ranged = classify_market_regime(
        _ohlcv_from_closes([100 + (1 if i % 2 == 0 else -1) for i in range(90)], volume=1_000_000),
        "SPY",
    )

    trend_report = activate_strategies_for_regime(["buyHold", "trendPullback", "meanReversion"], trending)
    range_report = activate_strategies_for_regime(["buyHold", "trendPullback", "meanReversion"], ranged)

    assert trend_report.active_strategies == ("buyHold", "trendPullback")
    assert range_report.active_strategies == ("buyHold", "meanReversion")
    assert range_report.to_dict()["decisions"][1]["reason"] == "regime_not_eligible"


def test_research_filters_detect_reusable_contexts():
    ranged_data = _ohlcv_from_closes([100 + (1 if i % 2 == 0 else -1) for i in range(30)], volume=1_000_000)
    stretched_data = _ohlcv_from_closes([100] * 29 + [115], volume=1_000_000)

    range_snapshot = evaluate_research_filters(
        ranged_data,
        "SPY",
        ResearchFilterConfig(choppiness_threshold=1.0, vwap_stretch_threshold=0.20),
    )
    stretch_snapshot = evaluate_research_filters(
        stretched_data,
        "SPY",
        ResearchFilterConfig(choppiness_threshold=99.0, vwap_stretch_threshold=0.03),
    )

    assert range_snapshot.result("choppiness_range").passed
    assert range_snapshot.result("choppiness_range").direction == "range"
    assert stretch_snapshot.result("vwap_stretch").passed
    assert stretch_snapshot.result("vwap_stretch").direction == "short_mean_reversion"
    assert "vwap_stretch" in stretch_snapshot.passed_filters
    assert stretch_snapshot.to_dict()["symbol"] == "SPY"


def test_research_filters_detect_price_action_contexts():
    structure_data = _ohlcv_from_closes([100] * 24 + [110], volume=1_000_000)
    structure_data.loc[structure_data.index[-1], "Volume"] = 3_000_000
    fvg_data = _ohlcv_from_closes([100] * 18 + [101, 130], volume=1_000_000)
    fvg_data.loc[fvg_data.index[-1], ["Open", "High", "Low", "Close"]] = [131, 134, 130, 133]
    sweep_data = _ohlcv_from_closes([100] * 24 + [101], volume=1_000_000)
    sweep_data.loc[sweep_data.index[-1], ["High", "Low", "Close"]] = [102, 95, 100.5]

    structure_snapshot = evaluate_research_filters(
        structure_data,
        "SPY",
        ResearchFilterConfig(structure_lookback=5, min_relative_volume=1.2),
    )
    fvg_snapshot = evaluate_research_filters(
        fvg_data,
        "SPY",
        ResearchFilterConfig(fvg_min_atr_multiple=0.01),
    )
    sweep_snapshot = evaluate_research_filters(
        sweep_data,
        "SPY",
        ResearchFilterConfig(liquidity_sweep_lookback=5),
    )

    assert structure_snapshot.result("structure_confirmation").passed
    assert structure_snapshot.result("structure_confirmation").direction == "long_breakout"
    assert fvg_snapshot.result("fair_value_gap").passed
    assert fvg_snapshot.result("fair_value_gap").direction == "bullish_imbalance"
    assert sweep_snapshot.result("liquidity_sweep").passed
    assert sweep_snapshot.result("liquidity_sweep").direction == "long_reversal"


def test_symbol_scorecards_separate_edge_regime_filters_and_sensitivity():
    records = [
        _bulk_record("SPY", "buyHold", 0.10, -0.20, trades=1),
        _bulk_record("SPY", "meanReversion", 0.22, -0.12, trades=6),
        _bulk_record("SPY", "meanReversion", 0.15, -0.10, trades=5),
        _bulk_record("SPY", "trendPullback", 0.08, -0.08, trades=3),
    ]
    ranged_data = _ohlcv_from_closes([100 + (1 if i % 2 == 0 else -1) for i in range(90)], volume=1_000_000)

    report = build_symbol_scorecards(records, data_by_symbol={"SPY": ranged_data})
    scorecard = report.scorecards[0]
    mean_reversion = next(entry for entry in scorecard.strategy_entries if entry.strategy == "meanReversion")

    assert scorecard.benchmark_return == 0.10
    assert scorecard.selected_strategy == "meanReversion"
    assert scorecard.best_edge_strategy == "meanReversion"
    assert "meanReversion" in scorecard.active_strategies
    assert scorecard.regime.trend_state == "range_bound"
    assert scorecard.filters.result("choppiness_range") is not None
    assert round(mean_reversion.parameter_sensitivity, 2) == 0.07
    assert report.summary()["selected_strategy_counts"]["meanReversion"] == 1
    assert report.to_dict()["scorecards"][0]["strategy_entries"]


def test_ensemble_allocation_chooses_strategy_benchmark_or_cash():
    records = [
        _bulk_record("SPY", "buyHold", 0.10, -0.20, trades=1),
        _bulk_record("SPY", "meanReversion", 0.22, -0.12, trades=6),
        _bulk_record("QQQ", "buyHold", 0.12, -0.18, trades=1),
        _bulk_record("QQQ", "meanReversion", 0.02, -0.08, trades=4),
        _bulk_record("TLT", "buyHold", -0.04, -0.16, trades=1),
        _bulk_record("TLT", "meanReversion", -0.02, -0.10, trades=4),
    ]
    ranged_data = _ohlcv_from_closes([100 + (1 if i % 2 == 0 else -1) for i in range(90)], volume=1_000_000)

    scorecards = build_symbol_scorecards(records, data_by_symbol={"SPY": ranged_data})
    plan = build_ensemble_allocation(scorecards, EnsembleAllocationPolicy(max_symbol_weight=0.25, cash_reserve=0.25))
    decisions = {decision.symbol: decision for decision in plan.decisions}

    assert decisions["SPY"].action == "strategy"
    assert decisions["SPY"].strategy == "meanReversion"
    assert decisions["QQQ"].action == "benchmark"
    assert decisions["QQQ"].strategy == "buyHold"
    assert decisions["TLT"].action == "cash"
    assert decisions["SPY"].weight <= 0.25
    assert plan.cash_weight >= 0.25
    assert plan.to_dict()["decisions"]


def test_research_matrix_expands_cross_asset_jobs_and_runs(tmp_path):
    matrix = research_matrix_from_dict(
        {
            "name": "test_cross_asset",
            "groups": [
                {
                    "name": "stocks",
                    "asset_class": "stocks",
                    "provider": "sample",
                    "symbols": ["SPY", "AAPL"],
                    "intervals": ["1d", "1h"],
                    "windows": [{"name": "recent", "period": "1y"}],
                },
                {
                    "name": "crypto",
                    "asset_class": "crypto",
                    "provider": "sample",
                    "symbols": ["BTC-USD"],
                    "intervals": ["1d"],
                    "windows": [{"name": "cycle", "start": "2020-01-01", "end": "2024-01-01"}],
                },
            ],
        }
    )

    jobs = expand_research_matrix(matrix)
    report = run_research_matrix(
        matrix,
        strategies=["buyHold"],
        data_loader_factory=lambda job: lambda symbol: sample_ohlcv(symbol, periods=40),
        store=JsonlStore(tmp_path),
        max_symbols_per_group=1,
    )

    assert len(jobs) == 3
    assert report.completed == 3
    assert report.failed == 0
    assert {row["asset_class"] for row in report.asset_class_summary()} == {"stocks", "crypto"}
    assert (tmp_path / "matrix-results.jsonl").exists()
    assert report.to_dict()["jobs"][0]["job"]["provider"] == "sample"


def test_cross_asset_matrix_keeps_intraday_crypto_inside_provider_limits():
    matrix = load_research_matrix("configs/research/cross_asset_matrix.json")
    jobs = expand_research_matrix(matrix)

    old_intraday_crypto = [
        job
        for job in jobs
        if job.asset_class == "crypto"
        and job.interval != "1d"
        and (job.window.start is not None or job.window.period not in {"60d", "730d"})
    ]

    assert not old_intraday_crypto
    assert any(job.group_name == "crypto_yfinance_intraday_recent" and job.interval == "1h" for job in jobs)


def _bulk_record(strategy_symbol: str, strategy: str, total_return: float, max_drawdown: float, trades: int) -> BulkBacktestRecord:
    return BulkBacktestRecord(
        symbol=strategy_symbol,
        strategy=strategy,
        params={},
        total_pnl=total_return * 10000,
        total_pnl_pct=total_return,
        metrics={"total_return": total_return, "max_drawdown": max_drawdown},
        trades=trades,
        fills=trades * 2,
        rejections=0,
    )


def _ohlcv_from_closes(closes: list[float], volume: int) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=index, dtype="float64")
    return pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close.iloc[0]),
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [volume] * len(close),
        },
        index=index,
    )
