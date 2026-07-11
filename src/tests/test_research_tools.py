import pytest
import pandas as pd
import json
import math

from src.backtesting import (
    BatchBacktestJob,
    BatchBacktestRunner,
    BulkBacktestRecord,
    BacktestValidationReport,
    CapacityAnalysisConfig,
    CryptoAdaptiveSelectionConfig,
    DynamicAllocationConfig,
    FactorSpreadDefinition,
    FactorTrendConfig,
    MarketClusterDefinition,
    MarketClusterValidationPolicy,
    REQUIRED_OPTIONS_CAPABILITIES,
    OptionContract,
    OptionPosition,
    OptionTailStressScenario,
    PairsResearchConfig,
    ParameterStabilityReport,
    PaperTradingExpectation,
    PaperTradingObservation,
    PaperTradingScorecardPolicy,
    PromotionPipelinePolicy,
    ResearchFilterConfig,
    ResearchCandidateEvidence,
    StrategyCapacityProfile,
    StylePremiaConfig,
    TradeCommitteeContext,
    TradeCommitteePolicy,
    EnsembleAllocationPolicy,
    StrategySelectionPolicy,
    StrategyFamilyEnsemblePolicy,
    WalkForwardGovernanceConfig,
    WalkForwardGovernanceReport,
    activate_strategies_for_regime,
    analyze_capacity,
    benchmark_relative_report,
    build_ensemble_allocation,
    build_dynamic_allocation,
    build_factor_trend_report,
    build_paper_trading_scorecard,
    build_strategy_family_ensemble,
    build_symbol_scorecards,
    build_style_premia_ranking,
    classify_market_regime,
    classify_regime_universe,
    decide_trade_action,
    discover_stat_arb_pairs,
    evaluate_options_promotion_gate,
    evaluate_promotion_candidate,
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
    run_walk_forward_governance,
    select_crypto_adaptive_universe,
    select_strategies_against_benchmark,
    stress_option_position,
    validate_market_clusters,
)
from src.data import DataDriftIssue, DataDriftReport, sample_ohlcv
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


def test_walk_forward_governance_optimizes_windows_and_freezes_holdout_params():
    data = sample_ohlcv(periods=120)

    report = run_walk_forward_governance(
        data=data,
        strategy_name="buyHold",
        symbol="SPY",
        param_grid={"target_fraction": [0.5, 1.0], "use_stop_loss": [False]},
        governance_config=WalkForwardGovernanceConfig(
            train_size=30,
            test_size=20,
            holdout_size=20,
            min_windows=3,
            min_parameter_stability_score=1.0,
            max_false_discovery_rate=0.5,
        ),
    )

    assert report.passed
    assert report.reason == "governance_passed"
    assert len(report.windows) == 3
    assert report.parameter_stability.champion_params["target_fraction"] == 1.0
    assert report.holdout_score is not None
    assert report.to_dict()["parameter_stability"]["stability_score"] == 1.0


def test_walk_forward_governance_supports_anchored_training_windows():
    data = sample_ohlcv(periods=120)

    report = run_walk_forward_governance(
        data=data,
        strategy_name="buyHold",
        symbol="SPY",
        param_grid={"target_fraction": [1.0], "use_stop_loss": [False]},
        governance_config=WalkForwardGovernanceConfig(
            split_mode="anchored",
            train_size=30,
            test_size=20,
            holdout_size=20,
            min_windows=3,
            min_parameter_stability_score=1.0,
        ),
    )

    assert report.windows[0].train_start == report.windows[1].train_start
    assert report.windows[1].train_end > report.windows[0].train_end
    assert report.parameter_stability.stability_score == 1.0


def test_walk_forward_governance_rejects_bad_no_retune_holdout():
    closes = [100 + offset for offset in range(100)] + [220 - offset * 4 for offset in range(20)]
    data = _ohlcv_from_closes(closes, volume=1_000_000)

    report = run_walk_forward_governance(
        data=data,
        strategy_name="buyHold",
        symbol="SPY",
        param_grid={"target_fraction": [1.0], "use_stop_loss": [False]},
        governance_config=WalkForwardGovernanceConfig(
            train_size=30,
            test_size=20,
            holdout_size=20,
            min_windows=3,
            min_holdout_score=0.0,
        ),
    )

    assert not report.passed
    assert report.reason == "holdout_score_below_threshold"
    assert report.holdout_score is not None and report.holdout_score < 0


def test_promotion_pipeline_creates_paper_manifest_when_all_gates_pass():
    governance = _governance_report(passed=True, champion_params={"target_fraction": 0.5})
    capacity = analyze_capacity(
        StrategyCapacityProfile("buyHold", 0.12, 100_000, 1_000, 1_000_000, 2.0, 0.0, 4),
        CapacityAnalysisConfig(capital_levels=(10_000, 50_000), max_volume_participation=0.10),
    )
    evidence = ResearchCandidateEvidence(
        strategy_name="buyHold",
        symbol="SPY",
        params={"target_fraction": 1.0},
        source_rules_captured=True,
        data_validation_passed=True,
        benchmark_passed=True,
        risk_gates_passed=True,
        validation_report=BacktestValidationReport(),
        governance_report=governance,
        capacity_report=capacity,
        benchmark_summary={"excess_return": 0.03},
    )

    report = evaluate_promotion_candidate(evidence, PromotionPipelinePolicy(minimum_estimated_capacity=10_000))

    assert report.passed
    assert report.reason == "promotion_ready"
    assert report.manifest is not None
    assert report.manifest.params["target_fraction"] == 0.5
    assert report.to_dict()["manifest"]["broker_mode"] == "alpaca_paper"


def test_promotion_pipeline_blocks_candidate_when_capacity_fails():
    capacity = analyze_capacity(
        StrategyCapacityProfile("crowded", 0.20, 100_000, 10_000, 20_000, 10.0, 0.0, 20),
        CapacityAnalysisConfig(capital_levels=(10_000,), max_volume_participation=0.10),
    )
    evidence = ResearchCandidateEvidence(
        strategy_name="crowded",
        symbol="SMALL",
        source_rules_captured=True,
        data_validation_passed=True,
        benchmark_passed=True,
        risk_gates_passed=True,
        validation_report=BacktestValidationReport(),
        governance_report=_governance_report(passed=True),
        capacity_report=capacity,
    )

    report = evaluate_promotion_candidate(evidence)

    assert not report.passed
    assert report.reason == "no_capacity_level_passed"
    assert report.manifest is None
    assert any(gate.name == "capacity" and not gate.passed for gate in report.gates)


def test_trade_committee_approves_promoted_strategy_when_inputs_are_clean():
    decision = decide_trade_action(
        TradeCommitteeContext(
            symbol="SPY",
            promotion_report=_promotion_report(),
            paper_scorecard=_paper_scorecard(passed=True),
            data_drift_reports=(_data_drift_report(passed=True),),
            regime=classify_market_regime(_ohlcv_from_closes([100 + i for i in range(90)], 1_000_000), "SPY"),
            strategy_edge=0.04,
            benchmark_edge=0.01,
        ),
        TradeCommitteePolicy(max_position_weight=0.30),
    )

    assert decision.action == "trade_strategy"
    assert decision.strategy_name == "buyHold"
    assert decision.target_weight == 0.30
    assert decision.reason == "committee_approved_strategy"
    assert decision.to_dict()["metadata"]["regime_quality"] >= 0.55


def test_trade_committee_blocks_trading_when_data_drift_fails():
    decision = decide_trade_action(
        TradeCommitteeContext(
            symbol="SPY",
            promotion_report=_promotion_report(),
            paper_scorecard=_paper_scorecard(passed=True),
            data_drift_reports=(_data_drift_report(passed=False),),
            strategy_edge=0.04,
            benchmark_edge=0.03,
        )
    )

    assert decision.action == "cash"
    assert decision.target_weight == 0
    assert decision.reason == "data_drift_failed"
    assert not next(gate for gate in decision.gates if gate.name == "data_health").passed


def test_trade_committee_hedges_existing_exposure_when_paper_behavior_fails():
    decision = decide_trade_action(
        TradeCommitteeContext(
            symbol="SPY",
            promotion_report=_promotion_report(),
            paper_scorecard=_paper_scorecard(passed=False),
            data_drift_reports=(_data_drift_report(passed=True),),
            strategy_edge=0.04,
            current_exposure=0.25,
        ),
        TradeCommitteePolicy(hedge_weight=0.08),
    )

    assert decision.action == "hedge"
    assert decision.target_weight == 0.25
    assert decision.hedge_weight == 0.08
    assert decision.reason == "missed_fill_rate_too_high"


def test_trade_committee_reduces_exposure_when_regime_quality_degrades():
    thin_unknown_regime = classify_market_regime(_ohlcv_from_closes([100, 101], 1_000_000), "SPY")

    decision = decide_trade_action(
        TradeCommitteeContext(
            symbol="SPY",
            promotion_report=_promotion_report(),
            paper_scorecard=_paper_scorecard(passed=True),
            data_drift_reports=(_data_drift_report(passed=True),),
            regime=thin_unknown_regime,
            strategy_edge=0.04,
            current_exposure=0.30,
        ),
        TradeCommitteePolicy(exposure_reduction_multiplier=0.40),
    )

    assert decision.action == "reduce_exposure"
    assert round(decision.target_weight, 2) == 0.12
    assert decision.reason == "regime_quality_below_threshold"


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


def test_strategy_research_catalog_tracks_core_candidate_families():
    payload = json.loads(open("configs/research/strategy_research_catalog.json", encoding="utf-8").read())
    candidates = {candidate["id"]: candidate for candidate in payload["candidates"]}

    assert "diversified_time_series_momentum" in candidates
    assert "graph_cluster_stat_arb" in candidates
    assert "volatility_risk_premium" in candidates
    assert candidates["volatility_risk_premium"]["status"] == "promotion_gate_mvp"
    assert all(candidate["sources"] for candidate in candidates.values())


def test_style_premia_ranking_scores_cross_section_and_allocates_sides():
    data = {
        "MOMO": _ohlcv_from_closes([100 + offset for offset in range(160)], volume=1_000_000),
        "DEF": _ohlcv_from_closes([100 + offset * 0.1 for offset in range(160)], volume=1_000_000),
        "LOSER": _ohlcv_from_closes([260 - offset for offset in range(160)], volume=1_000_000),
        "CARRY": _ohlcv_from_closes([100 + (offset % 2) * 0.1 for offset in range(160)], volume=1_000_000),
        "SHORT": _ohlcv_from_closes([100, 101, 102], volume=1_000_000),
    }
    data["CARRY"]["Carry"] = 0.08

    report = build_style_premia_ranking(
        data,
        config=StylePremiaConfig(
            momentum_lookback=20,
            long_momentum_lookback=60,
            volatility_lookback=20,
            value_lookback=60,
            quality_lookback=30,
            min_history=70,
            top_n=2,
            bottom_n=1,
            long_gross_exposure=0.8,
            short_gross_exposure=0.2,
            momentum_weight=0.70,
            value_weight=0.05,
            quality_weight=0.10,
            low_volatility_weight=0.10,
            carry_weight=0.05,
        ),
    )

    scores = report.scores
    score_by_symbol = {score.symbol: score for score in scores}

    assert report.long_symbols
    assert "MOMO" in report.long_symbols
    assert report.short_symbols == ("LOSER",)
    assert report.skipped_symbols["SHORT"] == "insufficient_history"
    assert score_by_symbol["CARRY"].raw_metrics["carry_proxy"] == 0.08
    assert round(sum(score.target_weight for score in scores if score.target_weight > 0), 2) == 0.8
    assert round(abs(sum(score.target_weight for score in scores if score.target_weight < 0)), 2) == 0.2
    assert [score.composite_score for score in scores] == sorted((score.composite_score for score in scores), reverse=True)
    assert report.to_dict()["scores"][0]["component_scores"]["momentum"] is not None


def test_stat_arb_pair_discovery_finds_mean_reverting_dislocation():
    pair_data = _stat_arb_pair_data()
    outsider = _ohlcv_from_closes([80 + ((offset * 7) % 19) for offset in range(180)], volume=1_000_000)

    report = discover_stat_arb_pairs(
        {"AAA": pair_data["AAA"], "BBB": pair_data["BBB"], "NOISE": outsider},
        PairsResearchConfig(
            min_history=120,
            correlation_lookback=90,
            hedge_lookback=120,
            zscore_lookback=60,
            min_abs_correlation=0.70,
            min_abs_zscore=1.25,
            max_half_life=40,
            gross_exposure_per_pair=0.30,
        ),
    )

    candidate = next(candidate for candidate in report.candidates if candidate.pair == "AAA/BBB")
    payload = report.to_dict()

    assert candidate.action == "short_spread"
    assert candidate.correlation > 0.70
    assert candidate.spread_zscore > 1.25
    assert candidate.half_life is not None and candidate.half_life < 40
    assert candidate.cointegration_proxy > 0
    assert candidate.legs[0].symbol == "AAA"
    assert candidate.legs[0].side == "SELL"
    assert candidate.legs[0].weight < 0
    assert round(sum(abs(leg.weight) for leg in candidate.legs), 2) == 0.30
    assert payload["active_count"] >= 1
    assert any(reason == "correlation_below_threshold" for reason in report.skipped_pairs.values())


def test_options_promotion_gate_blocks_until_full_options_stack_exists():
    partial = {
        "option_chains": True,
        "greeks": "mock greeks available",
        "tail_stress": True,
        "not_a_real_capability": True,
    }

    blocked = evaluate_options_promotion_gate(partial)
    complete = evaluate_options_promotion_gate({capability: True for capability in REQUIRED_OPTIONS_CAPABILITIES})

    assert not blocked.passed
    assert blocked.decision == "block"
    assert "option_margin" in blocked.missing_capabilities
    assert blocked.warnings
    assert complete.passed
    assert complete.decision == "promote"
    assert complete.to_dict()["missing_capabilities"] == []


def test_option_tail_stress_models_short_put_crash_loss_direction():
    contract = OptionContract(
        symbol="SPY260116P00400000",
        underlying="SPY",
        expiration="2026-01-16",
        strike=400,
        option_type="put",
    )
    position = OptionPosition(
        contract=contract,
        quantity=-1,
        average_price=2.0,
        underlying_price=420,
    )
    results = stress_option_position(
        position,
        [
            OptionTailStressScenario("flat", 0.0),
            OptionTailStressScenario("crash", -0.20),
        ],
    )
    flat, crash = results

    assert flat.estimated_pnl == 200.0
    assert crash.stressed_underlying_price == 336.0
    assert crash.stressed_intrinsic_value == 64.0
    assert crash.estimated_pnl == -6200.0
    assert crash.to_dict()["scenario"]["name"] == "crash"


def test_crypto_adaptive_selection_picks_liquid_high_sharpe_assets():
    data = {
        "BTC-USD": _ohlcv_from_closes([100 * (1.01**offset) for offset in range(140)], volume=2_000_000),
        "ETH-USD": _ohlcv_from_closes([80 * (1.006**offset) for offset in range(140)], volume=1_500_000),
        "DOGE-USD": _ohlcv_from_closes([20 * (0.98**offset) for offset in range(140)], volume=2_000_000),
        "ILLQ-USD": _ohlcv_from_closes([50 * (1.012**offset) for offset in range(140)], volume=1),
        "NEW-USD": _ohlcv_from_closes([10 + offset for offset in range(20)], volume=1_000_000),
    }

    report = select_crypto_adaptive_universe(
        data,
        config=CryptoAdaptiveSelectionConfig(
            momentum_lookback=10,
            sharpe_lookback=10,
            volatility_lookback=10,
            drawdown_lookback=30,
            liquidity_lookback=10,
            top_n=2,
            min_rolling_sharpe=0.0,
            min_average_dollar_volume=10_000,
            max_symbol_weight=0.40,
            cash_reserve=0.20,
        ),
    )
    assets = {asset.symbol: asset for asset in report.assets}

    assert "BTC-USD" in report.selected_symbols
    assert "ETH-USD" in report.selected_symbols
    assert "DOGE-USD" not in report.selected_symbols
    assert assets["ILLQ-USD"].reason == "liquidity_below_threshold"
    assert report.skipped_symbols["NEW-USD"] == "insufficient_history"
    assert report.invested_weight <= 0.80
    assert all(asset.target_weight <= 0.40 for asset in report.assets)
    assert report.to_dict()["selected_symbols"]


def test_dynamic_allocation_overlay_stays_growth_heavy_in_risk_on_tape():
    data = {
        "SPY": _ohlcv_from_closes([100 + offset for offset in range(160)], volume=2_000_000),
        "QQQ": _ohlcv_from_closes([120 + offset * 1.2 for offset in range(160)], volume=1_500_000),
        "XLU": _ohlcv_from_closes([50 + offset * 0.1 for offset in range(160)], volume=800_000),
        "TLT": _ohlcv_from_closes([90 + offset * 0.05 for offset in range(160)], volume=900_000),
        "GLD": _ohlcv_from_closes([180 + offset * 0.02 for offset in range(160)], volume=700_000),
        "VIXY": _ohlcv_from_closes([30 - offset * 0.05 for offset in range(160)], volume=700_000),
    }

    report = build_dynamic_allocation(data, config=DynamicAllocationConfig(min_history=80, max_symbol_weight=0.40))
    sleeve_weights = _sleeve_weights(report)

    assert report.stress.regime == "risk_on"
    assert sleeve_weights["growth"] > sleeve_weights["defensive"]
    assert sleeve_weights["growth"] > sleeve_weights["cash"]
    assert report.cash_weight < 0.25
    assert round(sum(report.weights_by_symbol.values()), 6) == 1.0
    assert report.to_dict()["stress"]["aggregate_stress"] < 0.25


def test_dynamic_allocation_overlay_raises_cash_and_hedges_in_stress_tape():
    calm_up = [100 + offset * 0.7 for offset in range(100)]
    selloff = [170 - offset * 2.2 + (8 if offset % 2 == 0 else -8) for offset in range(60)]
    spy = calm_up + selloff
    data = {
        "SPY": _ohlcv_from_closes(spy, volume=2_000_000),
        "QQQ": _ohlcv_from_closes([value * 1.2 for value in spy], volume=1_500_000),
        "XLU": _ohlcv_from_closes([50 + offset * 0.05 for offset in range(160)], volume=800_000),
        "TLT": _ohlcv_from_closes([120 - offset * 0.3 for offset in range(160)], volume=900_000),
        "GLD": _ohlcv_from_closes([180 + offset * 0.4 for offset in range(160)], volume=700_000),
        "VIXY": _ohlcv_from_closes([20 + max(0, offset - 100) * 1.5 for offset in range(160)], volume=700_000),
    }

    report = build_dynamic_allocation(data, config=DynamicAllocationConfig(min_history=80, max_symbol_weight=0.40))
    sleeve_weights = _sleeve_weights(report)

    assert report.stress.regime in {"risk_off", "crisis"}
    assert report.stress.drawdown_stress > 0.5
    assert report.stress.rates_stress > 0.5
    assert sleeve_weights["cash"] > sleeve_weights["growth"]
    assert sleeve_weights["hedge"] > 0
    assert sleeve_weights["commodities"] > 0
    assert report.weights_by_symbol["CASH"] >= 0.30


def test_factor_trend_report_builds_relative_style_and_sector_spreads():
    data = {
        "VLUE": _ohlcv_from_closes([100 + offset * 1.0 for offset in range(180)], volume=1_000_000),
        "IWF": _ohlcv_from_closes([100 + offset * 0.2 for offset in range(180)], volume=1_000_000),
        "XLK": _ohlcv_from_closes([150 - offset * 0.4 for offset in range(180)], volume=1_000_000),
        "SPY": _ohlcv_from_closes([100 + offset * 0.3 for offset in range(180)], volume=1_000_000),
        "SHORT": _ohlcv_from_closes([100 + offset for offset in range(20)], volume=1_000_000),
    }
    config = FactorTrendConfig(
        spreads=(
            FactorSpreadDefinition("value_vs_growth", ("VLUE",), ("IWF",), "style"),
            FactorSpreadDefinition("tech_vs_market", ("XLK",), ("SPY",), "sector"),
            FactorSpreadDefinition("missing_quality", ("QUAL",), ("SPY",), "style"),
            FactorSpreadDefinition("short_history", ("SHORT",), ("SPY",), "quality"),
        ),
        momentum_lookback=20,
        trend_lookback=60,
        volatility_lookback=20,
        min_history=60,
        min_abs_trend_score=0.10,
        gross_exposure_per_spread=0.30,
        max_active_spreads=2,
    )

    report = build_factor_trend_report(data, config=config)
    signals = {signal.name: signal for signal in report.signals}
    value = signals["value_vs_growth"]
    tech = signals["tech_vs_market"]

    assert value.action == "long_spread"
    assert value.legs[0].symbol == "VLUE"
    assert value.legs[0].side == "BUY"
    assert value.legs[1].symbol == "IWF"
    assert value.legs[1].side == "SELL"
    assert round(sum(abs(leg.weight) for leg in value.legs), 2) == 0.30
    assert tech.action == "short_spread"
    assert tech.legs[0].side == "SELL"
    assert report.skipped_spreads["missing_quality"] == "missing_symbols:QUAL"
    assert report.skipped_spreads["short_history"] == "SHORT:insufficient_history"
    assert report.to_dict()["active_count"] == 2


def test_strategy_family_ensemble_allocates_by_edge_and_diversification():
    records = [
        _bulk_record("SPY", "buyHold", 0.10, -0.20, trades=1),
        _bulk_record("QQQ", "buyHold", 0.12, -0.22, trades=1),
        _bulk_record("TLT", "buyHold", 0.02, -0.12, trades=1),
        _bulk_record("SPY", "managedFuturesMomentum", 0.22, -0.14, trades=8),
        _bulk_record("QQQ", "managedFuturesMomentum", 0.24, -0.16, trades=7),
        _bulk_record("TLT", "managedFuturesMomentum", 0.10, -0.08, trades=5),
        _bulk_record("SPY", "momentumRegime", 0.21, -0.15, trades=8),
        _bulk_record("QQQ", "momentumRegime", 0.22, -0.16, trades=7),
        _bulk_record("TLT", "momentumRegime", 0.08, -0.09, trades=5),
        _bulk_record("SPY", "meanReversion", 0.14, -0.09, trades=12),
        _bulk_record("QQQ", "meanReversion", 0.15, -0.10, trades=11),
        _bulk_record("TLT", "meanReversion", 0.07, -0.06, trades=7),
        _bulk_record("SPY", "weakSystem", 0.05, -0.12, trades=2),
        _bulk_record("QQQ", "weakSystem", 0.06, -0.13, trades=2),
        _bulk_record("TLT", "weakSystem", 0.01, -0.08, trades=2),
    ]
    returns = {
        "managedFuturesMomentum": pd.Series([0.01, -0.01, 0.02, 0.00, 0.015, -0.005]),
        "momentumRegime": pd.Series([0.011, -0.009, 0.019, 0.001, 0.014, -0.004]),
        "meanReversion": pd.Series([-0.002, 0.006, -0.001, 0.005, -0.002, 0.004]),
        "weakSystem": pd.Series([0.002, -0.004, 0.001, -0.003, 0.000, -0.002]),
    }

    report = build_strategy_family_ensemble(
        records,
        returns_by_strategy=returns,
        policy=StrategyFamilyEnsemblePolicy(
            min_markets=3,
            cash_reserve=0.20,
            max_strategy_weight=0.35,
            max_family_weight=0.40,
            family_map={
                "managedFuturesMomentum": "trend",
                "momentumRegime": "trend",
                "meanReversion": "mean_reversion",
                "weakSystem": "experimental",
            },
        ),
    )
    candidates = {candidate.strategy: candidate for candidate in report.candidates}

    assert candidates["managedFuturesMomentum"].action == "allocate"
    assert candidates["meanReversion"].action == "allocate"
    assert candidates["weakSystem"].action == "reject"
    assert candidates["momentumRegime"].correlation_penalty > 0.90
    assert report.weights_by_family["trend"] <= 0.40
    assert all(weight <= 0.35 for weight in report.weights_by_strategy.values())
    assert report.invested_weight <= 0.80
    assert report.cash_weight >= 0.20
    assert report.to_dict()["weights_by_strategy"]


def test_market_cluster_validation_promotes_only_cluster_robust_systems():
    records = [
        _bulk_record("SPY", "buyHold", 0.10, -0.20, trades=1),
        _bulk_record("QQQ", "buyHold", 0.12, -0.22, trades=1),
        _bulk_record("GLD", "buyHold", 0.04, -0.12, trades=1),
        _bulk_record("DBC", "buyHold", 0.03, -0.13, trades=1),
        _bulk_record("BTC-USD", "buyHold", 0.30, -0.55, trades=1),
        _bulk_record("SPY", "trendSystem", 0.18, -0.16, trades=5),
        _bulk_record("QQQ", "trendSystem", 0.20, -0.18, trades=5),
        _bulk_record("GLD", "trendSystem", 0.10, -0.10, trades=4),
        _bulk_record("DBC", "trendSystem", 0.09, -0.11, trades=4),
        _bulk_record("BTC-USD", "trendSystem", 0.10, -0.40, trades=4),
        _bulk_record("SPY", "nicheSystem", 0.08, -0.12, trades=3),
        _bulk_record("QQQ", "nicheSystem", 0.07, -0.13, trades=3),
        _bulk_record("GLD", "nicheSystem", 0.12, -0.08, trades=3),
        _bulk_record("DBC", "nicheSystem", 0.11, -0.09, trades=3),
        _bulk_record("MISSING", "trendSystem", 0.20, -0.10, trades=3),
    ]
    policy = MarketClusterValidationPolicy(
        min_pass_rate=0.50,
        clusters=(
            MarketClusterDefinition("equity_bull", ("SPY", "QQQ"), min_markets=2),
            MarketClusterDefinition("inflation_commodities", ("GLD", "DBC"), min_markets=2),
            MarketClusterDefinition("crypto_cycle", ("BTC-USD", "ETH-USD"), min_markets=1, min_win_rate=1.0),
        ),
    )

    report = validate_market_clusters(records, policy)
    summaries = {summary.strategy: summary for summary in report.summaries}
    results = {(result.strategy, result.cluster): result for result in report.results}

    assert summaries["trendSystem"].promoted
    assert summaries["trendSystem"].clusters_passed == 2
    assert not summaries["nicheSystem"].promoted
    assert results[("trendSystem", "equity_bull")].passed
    assert results[("trendSystem", "crypto_cycle")].reason == "insufficient_cluster_edge"
    assert results[("nicheSystem", "inflation_commodities")].passed
    assert "MISSING" in report.missing_benchmarks
    assert report.to_dict()["summaries"]


def _promotion_report():
    capacity = analyze_capacity(
        StrategyCapacityProfile("buyHold", 0.12, 100_000, 1_000, 1_000_000, 2.0, 0.0, 4),
        CapacityAnalysisConfig(capital_levels=(10_000, 50_000), max_volume_participation=0.10),
    )
    return evaluate_promotion_candidate(
        ResearchCandidateEvidence(
            strategy_name="buyHold",
            symbol="SPY",
            params={"target_fraction": 1.0},
            source_rules_captured=True,
            data_validation_passed=True,
            benchmark_passed=True,
            risk_gates_passed=True,
            validation_report=BacktestValidationReport(),
            governance_report=_governance_report(passed=True),
            capacity_report=capacity,
        ),
        PromotionPipelinePolicy(minimum_estimated_capacity=10_000),
    )


def _paper_scorecard(passed: bool):
    expected_fills = 0 if passed else 1
    return build_paper_trading_scorecard(
        PaperTradingExpectation(
            strategy_name="buyHold",
            symbol="SPY",
            expected_fills=expected_fills,
            expected_trades=expected_fills,
            expected_return=0.04,
            expected_ending_equity=10400.0,
        ),
        PaperTradingObservation(),
        PaperTradingScorecardPolicy(max_missed_fill_rate=0.0, require_clean_reconciliation=False),
    )


def _data_drift_report(passed: bool):
    issues = ()
    if not passed:
        issues = (DataDriftIssue("ERROR", "CLOSE_DRIFT", "Provider prices differ too much."),)
    return DataDriftReport(
        symbol="SPY",
        primary_provider="alpaca",
        comparison_provider="yfinance",
        overlap_count=5,
        max_close_drift_bps=0.0 if passed else 100.0,
        max_ohlc_drift_bps=0.0 if passed else 100.0,
        issues=issues,
    )


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


def _governance_report(passed: bool, champion_params: dict | None = None) -> WalkForwardGovernanceReport:
    return WalkForwardGovernanceReport(
        strategy_name="buyHold",
        symbol="SPY",
        config=WalkForwardGovernanceConfig(train_size=20, test_size=10, holdout_size=10),
        windows=(),
        parameter_stability=ParameterStabilityReport(
            champion_params=champion_params or {"target_fraction": 1.0},
            parameter_modes=champion_params or {"target_fraction": 1.0},
            parameter_stability={"target_fraction": 1.0},
            stability_score=1.0,
        ),
        holdout_result=None,
        holdout_score=0.05 if passed else -0.05,
        average_train_score=0.08,
        average_oos_score=0.04 if passed else -0.02,
        false_discovery_rate=0.0 if passed else 1.0,
        passed=passed,
        reason="governance_passed" if passed else "holdout_score_below_threshold",
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


def _stat_arb_pair_data() -> dict[str, pd.DataFrame]:
    base = []
    spread = []
    current_spread = 0.0
    for offset in range(180):
        base.append(100 + offset * 0.35)
        shock = 0.025 if offset % 12 == 0 else -0.003
        current_spread = 0.82 * current_spread + shock
        spread.append(current_spread)
    spread[-1] += 0.09

    aaa = [base_price * math.exp(spread_value) for base_price, spread_value in zip(base, spread)]
    bbb = base
    return {
        "AAA": _ohlcv_from_closes(aaa, volume=1_000_000),
        "BBB": _ohlcv_from_closes(bbb, volume=1_000_000),
    }


def _sleeve_weights(report) -> dict[str, float]:
    weights = {sleeve: 0.0 for sleeve in ("growth", "defensive", "bonds", "commodities", "hedge", "cash")}
    for target in report.targets:
        weights[target.sleeve] = weights.get(target.sleeve, 0.0) + target.weight
    return weights
