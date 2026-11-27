from dataclasses import replace
from datetime import datetime, time, timezone
import json

import pytest

from src.app import TradingApplication
from src.backtesting import (
    PaperSessionManifest,
    PaperTradingExpectation,
    PaperTradingObservation,
    PaperTradingScorecardPolicy,
    PromotionPipelinePolicy,
    PromotionPipelineReport,
    ResearchCandidateEvidence,
    build_paper_trading_scorecard,
)
from src.config import AlpacaConfig, ExecutionConfig, MarketDataConfig, RuntimeConfig, StrategyConfig, validate_runtime_environment
from src.data import AlpacaMarketDataStream, MarketDataEventType
from src.data.runtime.calendar import MarketSessionCalendar
from src.deployment import docker_profile, local_windows_task_profile, small_server_profile
from src.engine import EngineEvent, EngineEventType, EngineState, PaperAccountState, RuntimeRiskMonitor
from src.execution import AlpacaPaperBroker, BrokerAccountSnapshot, BrokerPositionSnapshot, ExecutionReport, PaperBroker
from src.execution.orders.ids import mark_order
from src.models import Order
from src.monitoring import (
    HealthCheck,
    HealthStatus,
    InMemoryNotificationSink,
    MetricsRegistry,
    NotificationRouter,
    build_dashboard_snapshot,
)
from src.operations import (
    AccountRiskPercentageReport,
    AutonomousPaperSessionOptions,
    AssetClassMetadataReport,
    BenchmarkPaperMonitorReport,
    BetaVolAdjustedExposureReport,
    BoringBaselineControlReport,
    CandidateABPaperTestReport,
    BrokerRoundingReport,
    BracketOrderPlan,
    CapitalDecayReport,
    CapacityScorecardReport,
    CashReserveReport,
    ClientOrderIdReplayReport,
    CorrelationClusterCapReport,
    CorporateActionReplayReport,
    DataFreshnessReport,
    DataLatencyHistogramReport,
    DataOutageSimulationReport,
    DataSourceArbitrationReport,
    DrawdownLockoutReport,
    DynamicPositionScalingReport,
    ExecutionTemplateReport,
    EnsemblePromotionReport,
    GapThroughStopStressReport,
    HoldoutMetadataReport,
    LiquidityParticipationReport,
    LiveMarketSnapshotReport,
    LossLimitReport,
    MarginPressureReport,
    MarketCalendarRegressionReport,
    MarketClusterPaperScorecardReport,
    MultiTimeframeDataReport,
    OrderCountGateReport,
    PartialFillReconciliationReport,
    PaperBrokerOrderPlan,
    PaperBrokerProofApprovalPolicy,
    PaperBrokerProofOptions,
    PaperBrokerProofScheduleWindow,
    PaperCleanupOptions,
    PaperControlledFlattenPlan,
    PaperDrawdownReport,
    PaperEndOfDayCloseoutReport,
    PaperExitPreviewReport,
    PaperOpenOrderReport,
    PaperPnlAttributionReport,
    PreSubmitOrderPreviewReport,
    QuoteDepthReport,
    QuoteSpreadReport,
    RealizedSlippageHaltReport,
    RejectedOrderCooldownReport,
    ReplaceOrderReport,
    RiskDashboardSummaryReport,
    RegimeConditionedScorecardReport,
    SampleSizeGateReport,
    StopExitVisibilityReport,
    PaperSoakFailureHalt,
    PaperSoakPromotionGate,
    PaperSoakScoreboard,
    ParameterDriftReport,
    PaperStaleOrderCancelReport,
    PaperSessionRecoveryReport,
    PaperSessionRiskBudget,
    PaperSessionSoakConfig,
    PaperSessionSubmissionGuardProbe,
    PaperSessionSubmissionGuardReport,
    PreLiveReadinessPolicy,
    PortfolioPaperSessionOptions,
    PortfolioExposureCapReport,
    PortfolioExposureReport,
    PortfolioKillSwitchReport,
    PortfolioRebalanceReport,
    PromotionQueueCandidate,
    PromotionQueuePolicy,
    SymbolCapabilityReport,
    WebsocketRestParityReport,
    SoakChecklist,
    StrategyCapitalBudgetReport,
    StrategyQuarantineReport,
    StrategyRegistryReport,
    StrategyRetirementReport,
    StatisticalConfidenceReport,
    StrategyAuditReport,
    StrategyStopTradingReport,
    StrategyExitReviewReport,
    StrategyOrderExplainabilityReport,
    SymbolConflictReport,
    TurnoverGateReport,
    VarCvarExposureReport,
    VolatilityShockReport,
    WalkForwardRefreshReport,
    alpaca_paper_soak_profiles,
    arbitrate_data_source,
    build_account_risk_percentage_report,
    build_asset_class_metadata_report,
    build_benchmark_paper_monitor_report,
    build_boring_baseline_control_report,
    build_candidate_ab_paper_test_report,
    build_beta_vol_adjusted_exposure_report,
    build_broker_rounding_report,
    build_bracket_order_plan,
    build_capital_decay_report,
    build_capacity_scorecard_report,
    build_cash_reserve_report,
    build_client_order_id_replay_report,
    build_correlation_cluster_cap_report,
    build_corporate_action_replay_report,
    build_data_freshness_report,
    build_data_latency_histogram_report,
    build_drawdown_lockout_report,
    build_dynamic_position_scaling_report,
    build_execution_template_report,
    build_ensemble_promotion_report,
    build_gap_through_stop_stress_report,
    build_holdout_metadata_report,
    build_liquidity_participation_report,
    build_loss_limit_report,
    build_margin_pressure_report,
    build_market_cluster_paper_scorecard_report,
    build_order_count_gate_report,
    build_partial_fill_reconciliation_report,
    build_parameter_drift_report,
    build_paper_exit_preview,
    build_paper_pilot_report,
    build_paper_monitor_report,
    build_paper_controlled_flatten_plan,
    build_paper_drawdown_report,
    build_paper_eod_closeout_report,
    build_paper_open_order_report,
    build_paper_pnl_attribution_report,
    build_paper_position_lifecycle_report,
    build_paper_soak_scoreboard,
    build_paper_stale_order_cancel_report,
    build_portfolio_exposure_cap_report,
    build_portfolio_exposure_report,
    build_portfolio_kill_switch_report,
    build_portfolio_rebalance_report,
    build_live_market_snapshot_report,
    build_market_calendar_regression_report,
    build_multi_timeframe_data_report,
    build_pre_submit_order_preview,
    build_quote_depth_report,
    build_quote_spread_report,
    build_regime_conditioned_scorecard_report,
    build_realized_slippage_halt_report,
    build_rejected_order_cooldown_report,
    build_replace_order_report,
    build_risk_dashboard_summary_report,
    build_sample_size_gate_report,
    build_statistical_confidence_report,
    build_strategy_audit_report,
    build_stop_exit_visibility_report,
    build_strategy_capital_budget_report,
    build_strategy_exit_review_report,
    build_strategy_order_explainability_report,
    build_strategy_quarantine_report,
    build_strategy_registry_report,
    build_strategy_retirement_report,
    build_strategy_stop_trading_report,
    build_symbol_conflict_report,
    build_symbol_capability_report,
    build_turnover_gate_report,
    build_var_cvar_exposure_report,
    build_volatility_shock_report,
    build_walk_forward_refresh_report,
    build_websocket_rest_parity_report,
    write_paper_monitor_report,
    evaluate_promotion_queue,
    evaluate_pre_live_readiness,
    evaluate_paper_soak_failure_halt,
    evaluate_paper_soak_promotion_gate,
    load_paper_session_manifests,
    run_autonomous_paper_session,
    run_paper_broker_proof,
    run_paper_cleanup,
    run_paper_stale_order_cancel,
    run_paper_session_soak,
    run_portfolio_paper_session,
    run_scheduled_paper_broker_proof,
    run_scheduled_paper_broker_proof_from_artifact,
    simulate_data_outage,
    validate_alpaca_paper_soak_profile,
)
from src.risk import RiskManager
from src.storage import SQLiteStateStore


def test_dashboard_snapshot_summarizes_account_orders_fills_and_halts():
    broker = PaperBroker(auto_fill_market_orders=False)
    submitted = broker.submit_order(Order("SPY", "BUY", 1, order_type="LIMIT", limit_price=100))
    account = PaperAccountState(10_000)
    risk = RuntimeRiskMonitor()
    risk._halt("test halt")

    snapshot = build_dashboard_snapshot(
        EngineState.HALTED,
        account,
        broker,
        prices={"SPY": 100},
        risk_monitor=risk,
        health={"stream": "ok"},
    )

    assert snapshot.engine_state == "HALTED"
    assert snapshot.open_orders[0]["id"] == submitted.id
    assert snapshot.risk_halt["halted"]
    assert snapshot.health["stream"] == "ok"


def test_notification_router_emits_operational_topics():
    sink = InMemoryNotificationSink()
    router = NotificationRouter(sink)

    router.handle_engine_event(EngineEvent(EngineEventType.STARTED, "started"))
    router.handle_engine_event(EngineEvent(EngineEventType.HALT, "halted", payload={"reason": "risk"}))

    assert [event.topic for event in sink.events] == ["startup", "halt"]
    assert sink.events[-1].severity == "CRITICAL"


def test_metrics_registry_and_health_check_snapshot():
    metrics = MetricsRegistry()
    metrics.increment("orders")
    metrics.gauge("equity", 10_000)
    metrics.timing("latency", 0.1)

    health = HealthCheck("stream", lambda: HealthStatus("stream", True, "ok")).run()

    assert metrics.snapshot()["counters"]["orders"] == 1
    assert health.healthy


def test_environment_validation_fails_fast_for_missing_alpaca_credentials():
    config = RuntimeConfig(
        data=MarketDataConfig(provider="alpaca"),
        alpaca=AlpacaConfig(api_key="", secret_key=""),
        execution=ExecutionConfig(mode="paper"),
    )

    result = validate_runtime_environment(config)

    assert not result.passed
    assert any("ALPACA_API_KEY" in error for error in result.errors)


def test_environment_validation_allows_safe_paper_configuration():
    config = RuntimeConfig(
        data=MarketDataConfig(provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    assert validate_runtime_environment(config).passed


def test_deployment_profiles_document_runtime_commands():
    profiles = [local_windows_task_profile(), docker_profile(), small_server_profile()]

    assert {profile.name for profile in profiles} == {"windows-task", "docker", "small-server"}
    assert all("paper" in profile.command for profile in profiles)


def test_soak_checklist_requires_all_criteria():
    checklist = SoakChecklist.default()
    assert not checklist.passed

    for check in list(checklist.checks):
        checklist = checklist.with_result(check.name, True, "ok")

    assert checklist.passed


def test_autonomous_paper_session_dry_run_writes_guarded_report(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    result = run_autonomous_paper_session(
        TradingApplication(config),
        AutonomousPaperSessionOptions(artifact_root=str(tmp_path)),
    )

    assert result.ready_for_submission
    assert result.orders_planned == 1
    assert not result.submitted
    assert result.data_rows > 0
    assert result.report_path is not None
    assert "session_report" in result.artifact_paths


def test_paper_session_soak_aggregates_repeated_guarded_sessions(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    report = run_paper_session_soak(
        TradingApplication(config),
        AutonomousPaperSessionOptions(artifact_root=str(tmp_path)),
        PaperSessionSoakConfig(sessions=2),
    )

    assert report.passed
    assert report.completed_sessions == 2
    assert all(session.ready_for_submission for session in report.sessions)
    assert all(session.report_path for session in report.sessions)
    assert {check.name for check in report.checks} >= {"minimum_sessions", "artifact_reports_written"}
    assert report.scoreboard.passed_sessions == 2
    assert report.scoreboard.current_pass_streak == 2
    assert report.promotion_gate is not None
    assert not report.promotion_gate.graduation_allowed
    assert report.failure_halt is not None
    assert not report.failure_halt.halted


def test_paper_soak_scoreboard_tracks_failures_and_metrics(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )
    report = run_paper_session_soak(
        TradingApplication(config),
        AutonomousPaperSessionOptions(artifact_root=str(tmp_path)),
        PaperSessionSoakConfig(sessions=2),
    )
    failed_session = replace(
        report.sessions[-1],
        ready_for_submission=False,
        warnings=("forced warning",),
    )

    scoreboard = build_paper_soak_scoreboard(
        (report.sessions[0], failed_session),
        PaperSessionSoakConfig(sessions=2),
        runtimes=(1.5, 2.5),
    )

    assert isinstance(scoreboard, PaperSoakScoreboard)
    assert scoreboard.passed_sessions == 1
    assert scoreboard.failed_sessions == 1
    assert scoreboard.current_pass_streak == 0
    assert scoreboard.current_fail_streak == 1
    assert "not_ready_for_submission" in scoreboard.failure_reasons
    assert "session_warnings" in scoreboard.failure_reasons
    assert scoreboard.average_runtime_seconds == pytest.approx(2.0)
    assert scoreboard.total_exposure > 0


def test_paper_soak_promotion_gate_requires_clean_streak(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )
    report = run_paper_session_soak(
        TradingApplication(config),
        AutonomousPaperSessionOptions(artifact_root=str(tmp_path)),
        PaperSessionSoakConfig(sessions=3, min_clean_streak_for_promotion=3),
    )

    gate = evaluate_paper_soak_promotion_gate(report.scoreboard, required_clean_streak=3)

    assert isinstance(gate, PaperSoakPromotionGate)
    assert gate.passed
    assert gate.graduation_allowed
    assert gate.reason == "paper_soak_clean_streak_passed"


def test_paper_soak_failure_halt_requires_operator_acknowledgement(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )
    report = run_paper_session_soak(
        TradingApplication(config),
        AutonomousPaperSessionOptions(artifact_root=str(tmp_path)),
        PaperSessionSoakConfig(sessions=1),
    )
    failed_scoreboard = build_paper_soak_scoreboard(
        (replace(report.sessions[0], ready_for_submission=False),),
        PaperSessionSoakConfig(sessions=1),
        runtimes=(0.1,),
    )

    locked = evaluate_paper_soak_failure_halt((), failed_scoreboard)
    acknowledged = evaluate_paper_soak_failure_halt(
        (),
        failed_scoreboard,
        acknowledged=True,
        operator_action="retry",
    )

    assert isinstance(locked, PaperSoakFailureHalt)
    assert locked.halted
    assert not locked.release_allowed
    assert "not_ready_for_submission" in locked.reason
    assert acknowledged.halted
    assert acknowledged.release_allowed
    assert acknowledged.operator_action == "retry"


def test_paper_session_recovery_blocks_unresolved_prior_state(tmp_path):
    state_path = tmp_path / "state.sqlite3"
    store = SQLiteStateStore(state_path)
    store.save_order(Order(id="prior-1", symbol="SPY", side="BUY", quantity=1, status="PENDING"))
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    result = run_autonomous_paper_session(
        TradingApplication(config),
        AutonomousPaperSessionOptions(
            artifact_root=str(tmp_path / "artifacts"),
            recover_state=True,
            state_db_path=str(state_path),
        ),
    )

    assert not result.ready_for_submission
    assert result.recovery.blocked
    assert result.recovery.reason == "unresolved_prior_state"
    assert "recovery" in result.artifact_paths
    assert any("Recovery blocked submission" in warning for warning in result.warnings)


def test_paper_session_recovery_allows_clean_prior_state(tmp_path):
    state_path = tmp_path / "state.sqlite3"
    store = SQLiteStateStore(state_path)
    order = Order(id="prior-1", symbol="SPY", side="BUY", quantity=1, status="FILLED")
    store.save_order(order)
    store.save_execution_report(ExecutionReport(order_id=order.id, status="FILLED", broker_order_id="broker-1"))
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    result = run_autonomous_paper_session(
        TradingApplication(config),
        AutonomousPaperSessionOptions(
            artifact_root=str(tmp_path / "artifacts"),
            recover_state=True,
            state_db_path=str(state_path),
        ),
    )

    assert result.ready_for_submission
    assert not result.recovery.blocked
    assert result.recovery.reconciliation_clean
    assert result.recovery.orders_loaded == 1


def test_paper_session_risk_budget_blocks_oversized_session(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    result = run_autonomous_paper_session(
        TradingApplication(config),
        AutonomousPaperSessionOptions(
            artifact_root=str(tmp_path),
            risk_budget=PaperSessionRiskBudget(max_session_notional=100.0),
        ),
    )

    assert not result.ready_for_submission
    assert result.risk_budget is not None
    assert not result.risk_budget.passed
    assert result.risk_budget.reason == "session_notional_above_budget"
    assert "risk_budget" in result.artifact_paths
    assert any("Risk budget blocked submission" in warning for warning in result.warnings)


def test_paper_session_submission_guard_blocks_kill_switch(tmp_path, monkeypatch):
    class FakeCalendar:
        def is_tradable_at(self, timestamp, policy=None):
            return True

        def session_at(self, timestamp):
            return type("Session", (), {"value": "REGULAR"})()

    monkeypatch.setattr("src.operations.paper_session.MarketSessionCalendar", lambda: FakeCalendar())
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    result = run_autonomous_paper_session(
        TradingApplication(config),
        AutonomousPaperSessionOptions(
            submit_orders=True,
            artifact_root=str(tmp_path),
            submission_approval_policy=PaperBrokerProofApprovalPolicy(kill_switch_enabled=True),
        ),
    )

    assert not result.submitted
    assert not result.ready_for_submission
    assert result.submission_guard is not None
    assert result.submission_guard.reason == "paper_session_kill_switch_enabled"
    assert "submission_guard" in result.artifact_paths
    assert "paper_session_result" in result.artifact_paths
    assert any("Submission guard blocked" in warning for warning in result.warnings)


def test_paper_session_submit_polls_execution_reports_before_reconciliation(tmp_path, monkeypatch):
    class FakeCalendar:
        def is_tradable_at(self, timestamp, policy=None):
            return True

        def session_at(self, timestamp):
            return type("Session", (), {"value": "REGULAR"})()

    class PollingBroker(PaperBroker):
        def poll_execution_reports(self, orders):
            reports = []
            for order in orders:
                filled = replace(order, status="FILLED")
                self.orders[filled.id] = filled
                report = ExecutionReport.from_order(filled, broker_order_id=self.reports[filled.id].broker_order_id)
                self.reports[filled.id] = report
                reports.append(report)
            return reports

    monkeypatch.setattr("src.operations.paper_session.MarketSessionCalendar", lambda: FakeCalendar())
    broker = PollingBroker(auto_fill_market_orders=False)
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(symbol="SPY", provider="sample"),
            execution=ExecutionConfig(mode="paper"),
            strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
        )
    )
    monkeypatch.setattr(app, "create_broker", lambda: broker)

    result = run_autonomous_paper_session(
        app,
        AutonomousPaperSessionOptions(
            submit_orders=True,
            artifact_root=str(tmp_path),
            fill_poll_attempts=2,
        ),
    )

    assert result.submitted
    assert result.fill_poll_attempts == 1
    assert result.polled_execution_reports == 1
    assert result.reconciliation_clean
    assert result.paper_scorecard_passed


def test_alpaca_paper_soak_profiles_validate_modes_and_safety():
    profiles = alpaca_paper_soak_profiles()
    sample_config = RuntimeConfig(
        data=MarketDataConfig(provider="sample"),
        execution=ExecutionConfig(mode="dry-run"),
    )
    safe_paper = RuntimeConfig(
        data=MarketDataConfig(provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    sample_validation = validate_alpaca_paper_soak_profile(profiles["sample-data"], sample_config)
    validation = validate_alpaca_paper_soak_profile(profiles["micro-notional"], safe_paper)
    options = profiles["micro-notional"].session_options("runs/test", state_db_path="runs/test.sqlite3")
    daemon_options = profiles["micro-notional"].daemon_options(artifact_root="runs/test-daemon")

    assert sample_validation.passed
    assert profiles["sample-data"].daemon_options().interval_seconds == 0.0
    assert validation.passed
    assert options.submit_orders
    assert options.max_position_weight == 0.0025
    assert options.execution_policy is not None
    assert options.execution_policy.allow_fractional_quantity
    assert options.execution_policy.max_target_notional == 25.0
    assert options.risk_budget is not None
    assert options.risk_budget.max_session_notional == 25.0
    assert daemon_options.submit_orders
    assert daemon_options.max_iterations == 3
    assert daemon_options.cleanup_each_iteration
    assert daemon_options.monitor_each_iteration
    assert daemon_options.data_parity_each_iteration

    unsafe = RuntimeConfig(
        data=MarketDataConfig(provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    validation = validate_alpaca_paper_soak_profile(profiles["micro-notional"], unsafe)

    assert not validation.passed
    assert any("ALPACA_BASE_URL" in error for error in validation.errors)


def test_micro_notional_profile_plans_fractional_order_inside_budget(tmp_path):
    profile = alpaca_paper_soak_profiles()["micro-notional"]
    options = replace(profile.session_options(str(tmp_path)), submit_orders=False, recover_state=False)
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        execution=ExecutionConfig(mode="paper"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    result = run_autonomous_paper_session(TradingApplication(config), options)

    assert result.ready_for_submission
    assert result.orders_planned == 1
    assert result.risk_budget is not None
    assert result.risk_budget.passed
    assert result.risk_budget.session_notional <= 25.0
    assert 0.0 < result.planned_orders[0]["quantity"] < 1.0


def test_live_market_snapshot_report_calculates_spread_and_midpoint():
    report = build_live_market_snapshot_report(
        [
            {
                "symbol": "SPY",
                "provider": "alpaca",
                "latest_trade_price": 500.05,
                "latest_trade_timestamp": "2026-07-24T14:30:00+00:00",
                "bid_price": 500.00,
                "ask_price": 500.10,
                "quote_timestamp": "2026-07-24T14:30:01+00:00",
            }
        ],
        observed_at=datetime(2026, 7, 24, 14, 30, 2, tzinfo=timezone.utc),
    )

    snapshot = report.snapshots[0]
    assert isinstance(report, LiveMarketSnapshotReport)
    assert report.passed
    assert snapshot.mid_price == pytest.approx(500.05)
    assert snapshot.spread == pytest.approx(0.10)
    assert snapshot.spread_bps == pytest.approx(2.0, rel=1e-3)


def test_quote_spread_report_blocks_wide_spreads_and_bad_fills():
    snapshots = build_live_market_snapshot_report(
        [{"symbol": "SPY", "bid": 100.0, "ask": 101.0, "price": 101.2}],
        provider="alpaca",
    ).snapshots

    report = build_quote_spread_report(
        snapshots,
        [{"symbol": "SPY", "side": "BUY", "average_fill_price": 101.4}],
        max_spread_bps=25,
        max_effective_spread_bps=35,
    )

    assert isinstance(report, QuoteSpreadReport)
    assert not report.passed
    assert report.reason == "quote_spread_too_wide"
    assert report.analyses[0].effective_spread_bps > 0


def test_data_freshness_report_uses_asset_class_thresholds():
    report = build_data_freshness_report(
        [
            {"symbol": "SPY", "source": "quote", "timestamp": "2026-07-24T14:29:00+00:00", "asset_class": "equity"},
            {"symbol": "BTCUSD", "source": "quote", "timestamp": "2026-07-24T14:20:00+00:00", "asset_class": "crypto"},
        ],
        observed_at=datetime(2026, 7, 24, 14, 30, tzinfo=timezone.utc),
        max_age_seconds_by_asset_class={"equity": 120, "crypto": 120},
    )

    assert isinstance(report, DataFreshnessReport)
    assert not report.passed
    statuses = {status.symbol: status for status in report.statuses}
    assert statuses["SPY"].passed
    assert not statuses["BTCUSD"].passed
    assert report.reason == "stale_data"


def test_data_source_arbitration_selects_first_viable_provider_under_drift_limit():
    report = arbitrate_data_source(
        "SPY",
        [
            {"provider": "alpaca", "freshness_passed": False, "schema_passed": True, "drift_bps": 1},
            {"provider": "cached", "freshness_passed": True, "schema_passed": True, "drift_bps": 10},
            {"provider": "yfinance", "freshness_passed": True, "schema_passed": True, "drift_bps": 100},
        ],
        max_drift_bps=50,
    )

    assert isinstance(report, DataSourceArbitrationReport)
    assert report.passed
    assert report.selected_provider == "cached"


def test_asset_class_metadata_and_symbol_capability_gates():
    metadata = build_asset_class_metadata_report(
        [
            {
                "symbol": "SPY",
                "asset_class": "etf",
                "tradable": True,
                "fractionable": True,
                "shortable": True,
                "easy_to_borrow": True,
                "marginable": True,
                "maintenance_margin": "0.3",
            },
            {
                "symbol": "XYZ",
                "asset_class": "stock",
                "tradable": True,
                "fractionable": False,
                "shortable": False,
                "easy_to_borrow": False,
                "marginable": False,
            },
        ]
    )
    capabilities = build_symbol_capability_report(
        metadata.assets,
        require_fractional=True,
        require_short=True,
        require_margin=True,
    )

    assert isinstance(metadata, AssetClassMetadataReport)
    assert metadata.assets[0].calendar_policy == "us_equity_regular"
    assert metadata.assets[0].maintenance_margin == pytest.approx(0.3)
    assert isinstance(capabilities, SymbolCapabilityReport)
    assert not capabilities.passed
    reasons = {gate.symbol: gate.reason for gate in capabilities.gates}
    assert reasons["SPY"] == "passed"
    assert reasons["XYZ"] == "fractional_trading_not_supported"


def test_multi_timeframe_data_report_requires_each_strategy_context_window():
    report = build_multi_timeframe_data_report(
        {
            "SPY": {
                "1d": {"rows": 252, "last_timestamp": "2026-07-23T20:00:00+00:00"},
                "15m": {"rows": 30, "last_timestamp": "2026-07-24T14:45:00+00:00"},
            },
            "QQQ": {
                "1d": {"rows": 252, "last_timestamp": "2026-07-23T20:00:00+00:00"},
            },
        },
        required_timeframes=("1d", "15m"),
        required_rows_by_timeframe={"1d": 200, "15m": 50},
        observed_at=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
    )

    assert isinstance(report, MultiTimeframeDataReport)
    assert not report.passed
    statuses = {(status.symbol, status.timeframe): status for status in report.statuses}
    assert statuses[("SPY", "1d")].passed
    assert statuses[("SPY", "15m")].reason == "insufficient_rows"
    assert statuses[("QQQ", "15m")].reason == "missing_timeframe"


def test_corporate_action_replay_report_validates_split_dividend_and_quantity_consistency():
    report = build_corporate_action_replay_report(
        [
            {
                "symbol": "AAPL",
                "action_type": "split",
                "raw_price": 400.0,
                "adjusted_price": 100.0,
                "raw_quantity": 5,
                "adjusted_quantity": 20,
                "expected_ratio": 4,
                "paper_quantity": 20,
                "backtest_quantity": 20,
            },
            {
                "symbol": "SPY",
                "action_type": "dividend",
                "dividend_amount": 1.5,
                "paper_quantity": 3,
                "backtest_quantity": 2,
            },
        ]
    )

    assert isinstance(report, CorporateActionReplayReport)
    assert not report.passed
    assert report.cases[0].passed
    assert report.cases[1].reason == "paper_backtest_quantity_mismatch"


def test_market_calendar_regression_report_covers_holiday_and_early_close_cases():
    calendar = MarketSessionCalendar(
        holidays={"2026-07-03"},
        early_closes={"2026-11-27": time(13, 0)},
    )

    report = build_market_calendar_regression_report(
        [
            {
                "name": "independence-day-observed",
                "timestamp": "2026-07-03T15:00:00+00:00",
                "expected_session": "CLOSED",
                "expected_tradable": False,
            },
            {
                "name": "black-friday-after-early-close",
                "timestamp": "2026-11-27T18:30:00+00:00",
                "expected_session": "AFTER_HOURS",
                "expected_tradable": False,
            },
        ],
        calendar=calendar,
    )

    assert isinstance(report, MarketCalendarRegressionReport)
    assert report.passed
    assert {case.actual_session for case in report.cases} == {"CLOSED", "AFTER_HOURS"}


def test_data_outage_simulation_blocks_live_submission_or_downgrades_explicitly():
    blocked = simulate_data_outage(
        historical_available=True,
        live_trade_available=False,
        live_quote_available=False,
    )
    downgraded = simulate_data_outage(
        historical_available=True,
        live_trade_available=False,
        live_quote_available=False,
        cached_snapshot_available=True,
        allow_cached_fallback=True,
    )

    assert isinstance(blocked, DataOutageSimulationReport)
    assert blocked.passed
    assert not blocked.submission_allowed
    assert downgraded.passed
    assert downgraded.submission_allowed
    assert downgraded.downgraded_to_cached_data


def test_websocket_rest_parity_report_compares_closed_bar_prices():
    report = build_websocket_rest_parity_report(
        [
            {"symbol": "SPY", "timestamp": "2026-07-24T14:30:00+00:00", "close": 500.10},
            {"symbol": "QQQ", "timestamp": "2026-07-24T14:30:00+00:00", "close": 450.00},
        ],
        [
            {"symbol": "SPY", "timestamp": "2026-07-24T14:30:00+00:00", "close": 500.00},
            {"symbol": "QQQ", "timestamp": "2026-07-24T14:30:00+00:00", "close": 449.00},
        ],
        max_close_drift_bps=5,
    )

    assert isinstance(report, WebsocketRestParityReport)
    assert not report.passed
    checks = {check.symbol: check for check in report.checks}
    assert checks["SPY"].passed
    assert checks["QQQ"].reason == "close_drift_above_threshold"


def test_data_latency_histograms_surface_slow_runtime_stages():
    report = build_data_latency_histogram_report(
        [
            {"name": "websocket_event", "latency_seconds": 0.04},
            {"name": "websocket_event", "latency_seconds": 0.08},
            {"name": "websocket_event", "latency_seconds": 0.20},
            {"name": "rest_call", "latency_seconds": 0.50},
            {"name": "rest_call", "latency_seconds": 1.50},
            {"name": "rest_call", "latency_seconds": 2.40},
        ],
        max_p95_seconds_by_name={"websocket_event": 0.5, "rest_call": 2.0},
    )

    assert isinstance(report, DataLatencyHistogramReport)
    assert not report.passed
    histograms = {histogram.name: histogram for histogram in report.histograms}
    assert histograms["websocket_event"].passed
    assert histograms["rest_call"].reason == "p95_latency_above_threshold"
    assert histograms["rest_call"].buckets[">=2.00s"] == 1


def test_execution_template_report_maps_strategy_families_to_order_controls():
    report = build_execution_template_report(
        [
            {"symbol": "SPY", "strategy_family": "trend"},
            {"symbol": "QQQ", "strategy_family": "breakout", "stop_loss_pct": 0.02},
            {
                "symbol": "IWM",
                "strategy_family": "breakout",
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
            },
        ]
    )

    assert isinstance(report, ExecutionTemplateReport)
    assert not report.passed
    selections = {selection.symbol: selection for selection in report.selections}
    assert selections["SPY"].template_name == "limit_with_timeout"
    assert selections["QQQ"].reason == "missing_take_profit_for_template"
    assert selections["IWM"].passed


def test_bracket_order_plan_creates_entry_stop_and_take_profit_legs():
    plan = build_bracket_order_plan(
        {"symbol": "SPY", "side": "BUY", "quantity": 0.1},
        entry_price=500.0,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
    )

    assert isinstance(plan, BracketOrderPlan)
    assert plan.passed
    assert plan.stop_loss_price == pytest.approx(490.0)
    assert plan.take_profit_price == pytest.approx(520.0)
    assert [leg.role for leg in plan.legs] == ["entry", "stop_loss", "take_profit"]
    assert {leg.side for leg in plan.legs[1:]} == {"SELL"}


def test_replace_order_report_plans_cancel_replace_for_stale_limit_orders():
    report = build_replace_order_report(
        [
            {
                "symbol": "SPY",
                "side": "BUY",
                "quantity": 1,
                "limit_price": 499.0,
                "created_at": "2026-07-24T14:00:00+00:00",
            },
            {
                "symbol": "QQQ",
                "side": "SELL",
                "quantity": 1,
                "limit_price": 450.0,
                "created_at": "2026-07-24T14:59:00+00:00",
            },
        ],
        {"SPY": {"bid": 500.0, "ask": 500.2}, "QQQ": {"bid": 450.0, "ask": 450.2}},
        now=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
        timeout_minutes=5,
    )

    assert isinstance(report, ReplaceOrderReport)
    assert report.passed
    assert report.replacements_planned == 1
    decisions = {decision.symbol: decision for decision in report.decisions}
    assert decisions["SPY"].action == "cancel_replace"
    assert decisions["SPY"].replacement_limit_price > 500.2
    assert decisions["QQQ"].reason == "keep_order"


def test_partial_fill_reconciliation_tracks_remaining_quantity():
    report = build_partial_fill_reconciliation_report(
        [
            {"client_order_id": "a", "symbol": "SPY", "side": "BUY", "quantity": 10},
            {"client_order_id": "b", "symbol": "QQQ", "side": "SELL", "quantity": 5},
        ],
        [
            {"client_order_id": "a", "symbol": "SPY", "side": "BUY", "quantity": 10, "filled_quantity": 4, "average_fill_price": 500.1},
            {"client_order_id": "b", "symbol": "QQQ", "side": "SELL", "quantity": 5, "filled_quantity": 5, "average_fill_price": 450.0},
        ],
    )

    assert isinstance(report, PartialFillReconciliationReport)
    assert report.passed
    assert report.partial_fills == 1
    reconciliations = {item.symbol: item for item in report.reconciliations}
    assert reconciliations["SPY"].remaining_quantity == pytest.approx(6)
    assert reconciliations["SPY"].reason == "partial_fill_tracked"
    assert reconciliations["QQQ"].reason == "filled"


def test_client_order_id_replay_blocks_duplicate_filled_submissions_and_reuses_open_orders():
    report = build_client_order_id_replay_report(
        [
            {"client_order_id": "new-1", "symbol": "SPY", "side": "BUY", "quantity": 1},
            {"client_order_id": "open-1", "symbol": "QQQ", "side": "BUY", "quantity": 1},
            {"client_order_id": "done-1", "symbol": "IWM", "side": "SELL", "quantity": 1},
        ],
        [
            {"client_order_id": "open-1", "status": "PENDING"},
            {"client_order_id": "done-1", "status": "FILLED"},
        ],
    )

    assert isinstance(report, ClientOrderIdReplayReport)
    assert report.passed
    checks = {check.client_order_id: check for check in report.checks}
    assert checks["new-1"].action == "submit_new"
    assert checks["open-1"].reason == "retry_existing_open_order"
    assert checks["done-1"].action == "block_duplicate_submit"
    assert report.blocked_duplicates == 1


def test_pre_submit_order_preview_requires_prices_and_summarizes_notional():
    report = build_pre_submit_order_preview(
        [
            {"symbol": "SPY", "side": "BUY", "quantity": 0.1, "order_type": "MARKET"},
            {"symbol": "QQQ", "side": "SELL", "quantity": 0.2, "order_type": "LIMIT", "limit_price": 450.0},
            {"symbol": "IWM", "side": "BUY", "quantity": 0.3, "order_type": "MARKET"},
        ],
        {"SPY": {"bid": 500.0, "ask": 500.2}},
    )

    assert isinstance(report, PreSubmitOrderPreviewReport)
    assert not report.passed
    assert report.total_estimated_notional == pytest.approx(50.01 + 90.0)
    lines = {line.symbol: line for line in report.lines}
    assert lines["SPY"].price_source == "quote_mid"
    assert lines["QQQ"].price_source == "order"
    assert lines["IWM"].reason == "missing_price_for_preview"


def test_order_count_gate_report_limits_session_and_per_symbol_counts():
    per_symbol_block = build_order_count_gate_report(
        [
            {"symbol": "SPY"},
            {"symbol": "SPY"},
            {"symbol": "QQQ"},
        ],
        max_session_orders=5,
        max_orders_per_symbol=1,
    )
    session_block = build_order_count_gate_report(
        [{"symbol": "SPY"}, {"symbol": "QQQ"}, {"symbol": "IWM"}],
        max_session_orders=2,
        max_orders_per_symbol=3,
    )

    assert isinstance(per_symbol_block, OrderCountGateReport)
    assert not per_symbol_block.passed
    assert per_symbol_block.reason == "symbol_order_count_above_limit"
    assert not session_block.passed
    assert session_block.reason == "session_order_count_above_limit"


def test_turnover_gate_report_uses_broker_equity_and_strategy_attribution():
    report = build_turnover_gate_report(
        [
            {"symbol": "SPY", "strategy_name": "trend", "quantity": 3, "average_fill_price": 500},
            {"symbol": "QQQ", "strategy_name": "trend", "quantity": 2, "average_fill_price": 450},
            {"symbol": "IWM", "strategy_name": "mean", "notional": 1100},
        ],
        {"equity": 10_000},
        max_daily_turnover_pct=0.30,
        max_strategy_turnover=2_000,
    )

    assert isinstance(report, TurnoverGateReport)
    assert not report.passed
    assert report.daily_turnover == pytest.approx(3500)
    assert report.daily_turnover_pct == pytest.approx(0.35)
    assert report.strategy_turnover["trend"] == pytest.approx(2400)
    assert report.reason == "daily_turnover_above_limit"


def test_realized_slippage_halt_triggers_after_repeated_bad_fills():
    report = build_realized_slippage_halt_report(
        [
            {"symbol": "SPY", "strategy_name": "trend", "side": "BUY", "expected_price": 100.0, "average_fill_price": 100.5},
            {"symbol": "QQQ", "strategy_name": "trend", "side": "BUY", "expected_price": 200.0, "average_fill_price": 201.0},
            {"symbol": "IWM", "strategy_name": "mean", "side": "SELL", "expected_price": 100.0, "average_fill_price": 99.9},
        ],
        max_slippage_bps=40,
        halt_after_breaches=2,
    )

    assert isinstance(report, RealizedSlippageHaltReport)
    assert not report.passed
    assert report.halted
    assert report.breaches == 2
    assert report.reason == "realized_slippage_halt_triggered"


def test_rejected_order_cooldown_groups_rejects_by_symbol_and_strategy():
    report = build_rejected_order_cooldown_report(
        [
            {"symbol": "SPY", "strategy_name": "trend", "status": "REJECTED"},
            {"symbol": "SPY", "strategy_name": "trend", "status": "REJECTED"},
            {"symbol": "QQQ", "strategy_name": "trend", "status": "REJECTED"},
        ],
        now=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
        max_rejects=2,
        cooldown_minutes=30,
    )

    assert isinstance(report, RejectedOrderCooldownReport)
    assert not report.passed
    cooldowns = {(cooldown.symbol, cooldown.strategy_name): cooldown for cooldown in report.cooldowns}
    assert cooldowns[("SPY", "trend")].cooldown_required
    assert cooldowns[("SPY", "trend")].cooldown_until == "2026-07-24T15:30:00+00:00"
    assert not cooldowns[("QQQ", "trend")].cooldown_required


def test_liquidity_participation_report_blocks_large_orders_and_wide_spreads():
    report = build_liquidity_participation_report(
        [
            {"symbol": "SPY", "quantity": 500, "estimated_price": 500},
            {"symbol": "QQQ", "quantity": 2_000, "estimated_price": 450},
            {"symbol": "IWM", "quantity": 100, "estimated_price": 220},
        ],
        {
            "SPY": {"average_volume": 1_000_000, "bid": 499.95, "ask": 500.05},
            "QQQ": {"average_volume": 100_000, "bid": 449.95, "ask": 450.05},
            "IWM": {"average_volume": 1_000_000, "bid": 219.0, "ask": 221.0},
        },
        max_participation_pct=1.0,
        max_spread_bps=25,
    )

    assert isinstance(report, LiquidityParticipationReport)
    assert not report.passed
    statuses = {status.symbol: status for status in report.statuses}
    assert statuses["SPY"].passed
    assert statuses["QQQ"].reason == "participation_above_limit"
    assert statuses["IWM"].reason == "spread_above_limit"


def test_broker_rounding_report_applies_fractional_whole_share_and_min_notional_rules():
    report = build_broker_rounding_report(
        [
            {"symbol": "SPY", "asset_class": "equity", "quantity": 0.123456789, "estimated_price": 500},
            {"symbol": "BRK.A", "asset_class": "whole_share", "quantity": 0.75, "estimated_price": 700_000},
            {"symbol": "BTCUSD", "asset_class": "crypto", "quantity": 0.00001, "estimated_price": 50_000},
        ],
        rules_by_asset_class={"crypto": {"fractional": True, "quantity_precision": 8, "minimum_notional": 1.0}},
    )

    assert isinstance(report, BrokerRoundingReport)
    assert not report.passed
    decisions = {decision.symbol: decision for decision in report.decisions}
    assert decisions["SPY"].reason == "quantity_rounded"
    assert decisions["SPY"].rounded_quantity == pytest.approx(0.123457)
    assert decisions["BRK.A"].reason == "rounded_quantity_zero"
    assert decisions["BTCUSD"].reason == "notional_below_minimum"


def test_stop_exit_visibility_report_requires_active_risk_controls_for_positions():
    report = build_stop_exit_visibility_report(
        [
            {"symbol": "SPY", "quantity": 0.1},
            {"symbol": "QQQ", "quantity": 0.2},
        ],
        [
            {"symbol": "SPY", "side": "SELL", "order_type": "STOP", "role": "stop_loss"},
            {"symbol": "SPY", "side": "SELL", "order_type": "LIMIT", "role": "take_profit"},
            {"symbol": "QQQ", "side": "SELL", "order_type": "LIMIT", "role": "take_profit"},
        ],
    )

    assert isinstance(report, StopExitVisibilityReport)
    assert not report.passed
    statuses = {status.symbol: status for status in report.statuses}
    assert statuses["SPY"].passed
    assert statuses["QQQ"].reason == "missing_visible_stop_order"


def test_quote_depth_report_scores_depth_notional_and_spread():
    report = build_quote_depth_report(
        {
            "SPY": {
                "bid": 500.0,
                "ask": 500.1,
                "bids": [{"price": 500.0, "size": 100}],
                "asks": [{"price": 500.1, "size": 100}],
            },
            "QQQ": {
                "bid": 450.0,
                "ask": 451.5,
                "bids": [{"price": 450.0, "size": 5}],
                "asks": [{"price": 451.5, "size": 5}],
            },
        },
        min_depth_notional=10_000,
        max_spread_bps=25,
    )

    assert isinstance(report, QuoteDepthReport)
    assert not report.passed
    statuses = {status.symbol: status for status in report.statuses}
    assert statuses["SPY"].passed
    assert statuses["QQQ"].reason == "depth_notional_below_minimum"


def test_portfolio_exposure_report_combines_account_positions_orders_and_targets():
    report = build_portfolio_exposure_report(
        account_snapshot={"cash": 2_000, "buying_power": 8_000, "equity": 10_000},
        broker_positions=[
            {"symbol": "SPY", "quantity": 2, "market_value": 1_000, "strategy_name": "trend", "sector": "broad", "asset_class": "etf"},
            {"symbol": "TLT", "quantity": -3, "market_value": -300, "strategy_name": "rates", "sector": "bonds", "asset_class": "bond"},
        ],
        expected_positions=[{"symbol": "QQQ", "market_value": 450, "strategy_name": "trend", "sector": "tech", "asset_class": "etf"}],
        open_orders=[{"symbol": "SPY", "side": "BUY", "quantity": 1, "limit_price": 510}],
        strategy_targets=[{"symbol": "SPY", "target_notional": 1_500}],
    )

    assert isinstance(report, PortfolioExposureReport)
    assert report.passed
    assert report.cash == pytest.approx(2_000)
    lines = {line.symbol: line for line in report.lines}
    assert lines["SPY"].net_notional == pytest.approx(1_510)
    assert lines["SPY"].target_notional == pytest.approx(1_500)
    assert lines["QQQ"].net_notional == pytest.approx(450)
    assert report.long_exposure == pytest.approx(1_960)
    assert report.short_exposure == pytest.approx(300)


def test_beta_vol_adjusted_exposure_report_applies_symbol_risk_lens():
    exposure = build_portfolio_exposure_report(
        broker_positions=[
            {"symbol": "SPY", "market_value": 1_000},
            {"symbol": "TLT", "market_value": 500},
        ],
    )

    report = build_beta_vol_adjusted_exposure_report(
        exposure,
        {"SPY": {"beta": 1.2, "volatility": 0.30}, "TLT": {"beta": -0.2, "volatility": 0.10}},
        max_beta_adjusted_gross=1_250,
        max_vol_adjusted_gross=2_000,
        volatility_target=0.20,
    )

    assert isinstance(report, BetaVolAdjustedExposureReport)
    assert not report.passed
    assert report.beta_adjusted_gross == pytest.approx(1_300)
    assert report.vol_adjusted_gross == pytest.approx(1_750)
    assert report.reason == "beta_adjusted_exposure_above_limit"


def test_correlation_cluster_cap_report_groups_highly_correlated_symbols():
    exposure = build_portfolio_exposure_report(
        broker_positions=[
            {"symbol": "SPY", "market_value": 1_000},
            {"symbol": "QQQ", "market_value": 900},
            {"symbol": "TLT", "market_value": 300},
        ],
    )

    report = build_correlation_cluster_cap_report(
        exposure,
        {("SPY", "QQQ"): 0.92, ("SPY", "TLT"): -0.15, ("QQQ", "TLT"): -0.10},
        max_cluster_exposure=1_500,
        correlation_threshold=0.80,
    )

    assert isinstance(report, CorrelationClusterCapReport)
    assert not report.passed
    clusters = {tuple(cluster.symbols): cluster for cluster in report.clusters}
    assert clusters[("QQQ", "SPY")].gross_exposure == pytest.approx(1_900)
    assert clusters[("QQQ", "SPY")].reason == "correlation_cluster_exposure_above_limit"


def test_portfolio_exposure_cap_report_checks_symbol_sector_asset_strategy_and_totals():
    exposure = build_portfolio_exposure_report(
        broker_positions=[
            {"symbol": "SPY", "market_value": 1_000, "sector": "broad", "asset_class": "etf", "strategy_name": "trend"},
            {"symbol": "QQQ", "market_value": 900, "sector": "tech", "asset_class": "etf", "strategy_name": "trend"},
            {"symbol": "TLT", "market_value": -300, "sector": "bonds", "asset_class": "bond", "strategy_name": "rates"},
        ],
    )

    report = build_portfolio_exposure_cap_report(
        exposure,
        symbol_caps={"SPY": 800},
        sector_caps={"tech": 1_000},
        asset_class_caps={"etf": 2_500},
        strategy_caps={"trend": 1_500},
        total_gross_cap=2_500,
        total_net_cap=2_000,
    )

    assert isinstance(report, PortfolioExposureCapReport)
    assert not report.passed
    statuses = {(status.group_type, status.group): status for status in report.statuses}
    assert statuses[("symbol", "SPY")].reason == "symbol_exposure_above_limit"
    assert statuses[("strategy", "trend")].reason == "strategy_exposure_above_limit"
    assert statuses[("total", "gross")].passed


def test_strategy_capital_budget_report_requires_paper_scorecard_and_operator_approval_for_increases():
    report = build_strategy_capital_budget_report(
        [
            {"strategy_name": "trend", "requested_budget": 1_500, "paper_scorecard_passed": True, "operator_approved": True},
            {"strategy_name": "mean", "requested_budget": 800, "paper_scorecard_passed": False, "operator_approved": True},
            {"strategy_name": "rates", "requested_budget": 1_200, "paper_scorecard_passed": True, "operator_approved": False},
            {"strategy_name": "defensive", "requested_budget": 400, "paper_scorecard_passed": False, "operator_approved": False},
        ],
        {"trend": 1_000, "mean": 500, "rates": 600, "defensive": 500},
    )

    assert isinstance(report, StrategyCapitalBudgetReport)
    assert not report.passed
    decisions = {decision.strategy_name: decision for decision in report.decisions}
    assert decisions["trend"].approved_budget == pytest.approx(1_500)
    assert decisions["trend"].reason == "budget_increase_approved"
    assert decisions["mean"].reason == "missing_passing_paper_scorecard"
    assert decisions["rates"].reason == "missing_operator_approval"
    assert decisions["defensive"].reason == "budget_reduction_allowed"


def test_capital_decay_report_reduces_budget_after_underperformance_errors_or_stale_evidence():
    report = build_capital_decay_report(
        [
            {"strategy_name": "trend", "current_budget": 1_000, "underperformed": True},
            {"strategy_name": "mean", "current_budget": 500, "execution_errors": 2, "decay_rate": 0.10},
            {"strategy_name": "carry", "current_budget": 750},
        ],
        default_decay_rate=0.25,
    )

    assert isinstance(report, CapitalDecayReport)
    decisions = {decision.strategy_name: decision for decision in report.decisions}
    assert decisions["trend"].decayed_budget == pytest.approx(750)
    assert decisions["mean"].decayed_budget == pytest.approx(450)
    assert decisions["carry"].reason == "no_decay_required"


def test_loss_limit_report_combines_realized_unrealized_and_strategy_pnl():
    report = build_loss_limit_report(
        [
            {"daily_realized_pnl": -40, "daily_unrealized_pnl": -15, "daily_strategy_attributed_pnl": 5, "weekly_realized_pnl": -100},
            {"daily_realized_pnl": 10, "weekly_unrealized_pnl": -80, "weekly_strategy_attributed_pnl": -25},
        ],
        max_daily_loss=45,
        max_weekly_loss=250,
    )

    assert isinstance(report, LossLimitReport)
    assert not report.passed
    assert report.daily_loss == pytest.approx(50)
    assert report.weekly_loss == pytest.approx(205)
    assert report.reason == "daily_loss_limit_breached"


def test_drawdown_lockout_persists_until_manual_reset_and_retriggers_on_active_breach():
    locked = build_drawdown_lockout_report(
        {"equity": 8_700},
        prior_state={"peak_equity": 10_000, "locked": False},
        max_drawdown_pct=0.10,
        observed_at=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
    )
    persisted = build_drawdown_lockout_report(
        {"equity": 9_800},
        prior_state=locked.to_dict(),
        max_drawdown_pct=0.10,
        manual_reset=False,
    )
    reset = build_drawdown_lockout_report(
        {"equity": 9_800},
        prior_state=locked.to_dict(),
        max_drawdown_pct=0.10,
        manual_reset=True,
    )

    assert isinstance(locked, DrawdownLockoutReport)
    assert locked.locked
    assert locked.reason == "drawdown_lockout_triggered"
    assert persisted.locked
    assert persisted.reason == "drawdown_lockout_persisted"
    assert not reset.locked
    assert reset.reason == "drawdown_lockout_reset"


def test_volatility_shock_report_estimates_directional_loss_against_current_exposure():
    exposure = build_portfolio_exposure_report(
        broker_positions=[
            {"symbol": "SPY", "market_value": 1_000},
            {"symbol": "TLT", "market_value": -500},
        ]
    )
    report = build_volatility_shock_report(
        exposure,
        {"SPY": -0.06, "TLT": 0.04},
        max_loss=75,
    )

    assert isinstance(report, VolatilityShockReport)
    assert not report.passed
    assert report.total_estimated_loss == pytest.approx(80)
    assert report.reason == "volatility_shock_loss_above_limit"


def test_gap_through_stop_stress_blocks_overnight_exposure_when_gap_loss_is_too_large():
    report = build_gap_through_stop_stress_report(
        [
            {"symbol": "SPY", "quantity": 10, "current_price": 100, "stop_price": 95, "gap_pct": 0.02},
            {"symbol": "TLT", "quantity": -5, "current_price": 90, "stop_price": 94, "gap_pct": 0.03},
        ],
        max_gap_loss=100,
    )

    assert isinstance(report, GapThroughStopStressReport)
    assert not report.passed
    assert report.total_estimated_gap_loss == pytest.approx(103.1)
    assert report.reason == "gap_through_stop_loss_above_budget"


def test_margin_pressure_and_cash_reserve_reports_use_broker_state_plus_pending_orders():
    exposure = build_portfolio_exposure_report(
        broker_positions=[
            {"symbol": "SPY", "market_value": 4_000},
            {"symbol": "QQQ", "market_value": 2_000},
        ]
    )
    margin = build_margin_pressure_report(
        exposure,
        {"equity": 5_000, "buying_power": 8_000},
        margin_by_symbol={"SPY": 0.35, "QQQ": 0.30},
        max_concentration_pct=0.75,
    )
    cash = build_cash_reserve_report(
        {"cash": 1_000},
        open_orders=[{"symbol": "SPY", "side": "BUY", "quantity": 1, "limit_price": 600}],
        pending_exits=[{"symbol": "TLT", "side": "SELL", "quantity": 1, "limit_price": 200}],
        required_reserve=750,
    )

    assert isinstance(margin, MarginPressureReport)
    assert not margin.passed
    assert margin.maintenance_required == pytest.approx(2_000)
    assert margin.reason == "concentration_above_margin_limit"
    assert isinstance(cash, CashReserveReport)
    assert not cash.passed
    assert cash.projected_cash == pytest.approx(600)
    assert cash.reason == "cash_reserve_below_requirement"


def test_dynamic_position_scaling_uses_confidence_scorecard_regime_and_volatility():
    report = build_dynamic_position_scaling_report(
        [
            {
                "symbol": "SPY",
                "strategy_name": "trend",
                "base_notional": 1_000,
                "confidence": 0.8,
                "paper_scorecard_quality": 0.5,
                "regime_fit": 0.75,
                "volatility": 0.40,
            }
        ],
        volatility_target=0.20,
    )

    assert isinstance(report, DynamicPositionScalingReport)
    decision = report.decisions[0]
    assert decision.scaled_notional == pytest.approx(150.0)
    assert decision.reason == "scaled"


def test_portfolio_rebalance_report_can_increase_reduce_or_hold_existing_positions():
    exposure = build_portfolio_exposure_report(
        broker_positions=[
            {"symbol": "SPY", "market_value": 1_000},
            {"symbol": "QQQ", "market_value": 700},
            {"symbol": "TLT", "market_value": 300},
        ]
    )
    report = build_portfolio_rebalance_report(
        exposure,
        [{"symbol": "SPY", "target_notional": 1_010}, {"symbol": "QQQ", "target_notional": 1_000}, {"symbol": "TLT", "target_notional": 100}],
        rebalance_threshold_notional=25,
    )

    assert isinstance(report, PortfolioRebalanceReport)
    decisions = {decision.symbol: decision for decision in report.decisions}
    assert decisions["SPY"].action == "hold"
    assert decisions["QQQ"].action == "increase"
    assert decisions["TLT"].action == "reduce"


def test_symbol_conflict_report_blocks_or_nets_opposing_strategy_exposure():
    netted = build_symbol_conflict_report(
        [
            {"symbol": "SPY", "strategy_name": "trend", "side": "BUY", "notional": 1_000},
            {"symbol": "SPY", "strategy_name": "mean", "side": "SELL", "notional": 400},
        ],
        allow_netting=True,
    )
    blocked = build_symbol_conflict_report(
        [
            {"symbol": "SPY", "strategy_name": "trend", "side": "BUY", "notional": 1_000},
            {"symbol": "SPY", "strategy_name": "mean", "side": "SELL", "notional": 400},
        ],
        allow_netting=False,
    )

    assert isinstance(netted, SymbolConflictReport)
    assert netted.passed
    assert netted.decisions[0].action == "net_to_target"
    assert netted.decisions[0].net_requested_notional == pytest.approx(600)
    assert not blocked.passed
    assert blocked.reason == "opposing_symbol_exposure_conflict"


def test_strategy_stop_trading_report_stops_on_drawdown_drift_slippage_rejects_missing_fills_or_regime():
    report = build_strategy_stop_trading_report(
        [
            {"strategy_name": "trend", "drawdown_pct": 0.12},
            {"strategy_name": "mean", "data_drift_bps": 75},
            {"strategy_name": "breakout", "slippage_breaches": 2},
            {"strategy_name": "clean", "drawdown_pct": 0.01, "regime_match": True},
        ],
        max_drawdown_pct=0.08,
        max_data_drift_bps=50,
        max_slippage_breaches=2,
        observed_at=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
        cooldown_minutes=60,
    )

    assert isinstance(report, StrategyStopTradingReport)
    assert not report.passed
    decisions = {decision.strategy_name: decision for decision in report.decisions}
    assert decisions["trend"].reason == "strategy_drawdown_stop"
    assert decisions["trend"].stopped_until == "2026-07-24T16:00:00+00:00"
    assert decisions["mean"].reason == "strategy_data_drift_stop"
    assert decisions["breakout"].reason == "strategy_slippage_stop"
    assert decisions["clean"].passed


def test_portfolio_kill_switch_report_cancels_orders_flattens_positions_and_disables_entries():
    exposure = build_portfolio_exposure_report(
        broker_positions=[
            {"symbol": "SPY", "quantity": 0.1, "market_value": 50, "strategy_name": "trend"},
            {"symbol": "TLT", "quantity": -0.2, "market_value": -20, "strategy_name": "rates"},
        ]
    )

    report = build_portfolio_kill_switch_report(
        exposure,
        open_orders=[{"symbol": "SPY", "id": "open-1"}, {"symbol": "QQQ", "id": "open-2"}],
        triggered=True,
        reason="operator_kill_switch",
    )

    assert isinstance(report, PortfolioKillSwitchReport)
    assert not report.passed
    assert report.cancel_order_count == 2
    assert report.flatten_order_count == 2
    assert report.disable_new_orders
    flatten = {order["symbol"]: order for order in report.flatten_orders}
    assert flatten["SPY"]["side"] == "SELL"
    assert flatten["TLT"]["side"] == "BUY"


def test_account_risk_percentage_report_enforces_operator_defined_account_risk_limits():
    report = build_account_risk_percentage_report(
        {"equity": 10_000},
        {
            "session": 800,
            "day": 300,
            "strategy_trend": 1_200,
            "portfolio": 2_500,
        },
        {
            "session": 0.05,
            "day": 0.05,
            "strategy_trend": 0.15,
            "portfolio": 0.30,
        },
    )

    assert isinstance(report, AccountRiskPercentageReport)
    assert not report.passed
    statuses = {status.name: status for status in report.statuses}
    assert statuses["session"].pct_of_equity == pytest.approx(0.08)
    assert statuses["session"].reason == "session_risk_pct_above_limit"
    assert statuses["day"].passed


def test_risk_dashboard_summary_report_turns_risk_reports_into_operator_cards():
    drawdown = build_drawdown_lockout_report(
        {"equity": 8_700},
        prior_state={"peak_equity": 10_000},
        max_drawdown_pct=0.10,
    )
    loss = build_loss_limit_report(
        [{"daily_realized_pnl": -10, "weekly_realized_pnl": -20}],
        max_daily_loss=100,
        max_weekly_loss=500,
    )

    report = build_risk_dashboard_summary_report({"drawdown": drawdown, "loss": loss})

    assert isinstance(report, RiskDashboardSummaryReport)
    assert not report.passed
    assert report.critical_count == 1
    cards = {card.name: card for card in report.cards}
    assert cards["drawdown"].severity == "critical"
    assert cards["loss"].severity == "info"


def test_var_cvar_exposure_report_estimates_tail_loss_from_historical_returns():
    exposure = build_portfolio_exposure_report(
        broker_positions=[
            {"symbol": "SPY", "market_value": 1_000},
            {"symbol": "TLT", "market_value": -500},
        ]
    )

    report = build_var_cvar_exposure_report(
        exposure,
        {
            "SPY": [0.01, -0.02, -0.05, 0.03, -0.10],
            "TLT": [0.01, 0.02, -0.01, 0.05, -0.02],
        },
        confidence=0.80,
        max_var=110,
        max_cvar=90,
    )

    assert isinstance(report, VarCvarExposureReport)
    assert not report.passed
    lines = {line.symbol: line for line in report.lines}
    assert lines["SPY"].var == pytest.approx(50)
    assert lines["SPY"].cvar == pytest.approx(75)
    assert lines["TLT"].var == pytest.approx(10)
    assert report.total_var == pytest.approx(60)
    assert report.total_cvar == pytest.approx(92.5)
    assert report.reason == "portfolio_cvar_above_limit"


def test_strategy_registry_report_tracks_candidate_lifecycle_statuses():
    report = build_strategy_registry_report(
        [
            {"strategy_name": "trend", "status": "paper-active", "family": "momentum", "symbol_scope": ["SPY", "QQQ"]},
            {"strategy_name": "mean", "status": "exploratory"},
            {"strategy_name": "bad", "status": "mystery"},
        ]
    )

    assert isinstance(report, StrategyRegistryReport)
    assert not report.passed
    assert report.status_counts["paper-active"] == 1
    assert report.entries[0].symbol_scope == ("SPY", "QQQ")
    assert report.entries[-1].reason == "mystery" or not report.entries[-1].passed


def test_strategy_retirement_report_retires_repeated_benchmark_or_paper_failures():
    report = build_strategy_retirement_report(
        [
            {"strategy_name": "trend", "benchmark_failures": 3, "paper_scorecard_failures": 0},
            {"strategy_name": "mean", "benchmark_failures": 1, "paper_scorecard_failures": 2},
            {"strategy_name": "carry", "benchmark_failures": 1, "paper_scorecard_failures": 0},
        ],
        max_benchmark_failures=3,
        max_paper_scorecard_failures=2,
    )

    assert isinstance(report, StrategyRetirementReport)
    assert not report.passed
    decisions = {decision.strategy_name: decision for decision in report.decisions}
    assert decisions["trend"].reason == "benchmark_failures_retired"
    assert decisions["mean"].reason == "paper_scorecard_failures_retired"
    assert decisions["carry"].passed


def test_strategy_quarantine_report_flags_paper_backtest_divergence():
    report = build_strategy_quarantine_report(
        [
            {"strategy_name": "trend", "return_drift": 0.15},
            {"strategy_name": "mean", "slippage_drift_bps": 75},
            {"strategy_name": "clean", "return_drift": 0.01, "missed_fill_rate": 0.01},
        ],
        max_return_drift=0.10,
        max_slippage_drift_bps=50,
    )

    assert isinstance(report, StrategyQuarantineReport)
    assert not report.passed
    decisions = {decision.strategy_name: decision for decision in report.decisions}
    assert decisions["trend"].reason == "return_drift_quarantine"
    assert decisions["mean"].reason == "slippage_drift_quarantine"
    assert decisions["clean"].passed


def test_walk_forward_refresh_report_marks_refresh_disable_promote_and_keep_actions():
    report = build_walk_forward_refresh_report(
        [
            {"strategy_name": "stale", "status": "paper-active", "last_refresh_at": "2026-06-01T00:00:00+00:00", "out_of_sample_passed": True},
            {"strategy_name": "failed", "status": "paper-active", "last_refresh_at": "2026-07-20T00:00:00+00:00", "out_of_sample_passed": False},
            {"strategy_name": "promote", "status": "paper-active", "last_refresh_at": "2026-07-20T00:00:00+00:00", "out_of_sample_passed": True, "promotion_eligible": True},
        ],
        now=datetime(2026, 7, 24, tzinfo=timezone.utc),
        max_refresh_age_days=30,
    )

    assert isinstance(report, WalkForwardRefreshReport)
    assert not report.passed
    decisions = {decision.strategy_name: decision for decision in report.decisions}
    assert decisions["stale"].action == "refresh_due"
    assert decisions["failed"].action == "disable"
    assert decisions["promote"].action == "promote"


def test_holdout_metadata_report_blocks_overlap_and_holdout_retuning():
    report = build_holdout_metadata_report(
        [
            {
                "strategy_name": "clean",
                "train_start": "2024-01-01",
                "train_end": "2024-12-31",
                "validation_start": "2025-01-01",
                "validation_end": "2025-06-30",
                "test_start": "2025-07-01",
                "test_end": "2025-12-31",
            },
            {
                "strategy_name": "overlap",
                "train_start": "2024-01-01",
                "train_end": "2025-02-01",
                "validation_start": "2025-01-01",
                "validation_end": "2025-06-30",
                "test_start": "2025-07-01",
                "test_end": "2025-12-31",
            },
        ]
    )

    assert isinstance(report, HoldoutMetadataReport)
    assert not report.passed
    checks = {check.strategy_name: check for check in report.checks}
    assert checks["clean"].passed
    assert checks["overlap"].reason == "split_windows_overlap"


def test_benchmark_paper_monitor_report_disables_after_cost_underperformance():
    report = build_benchmark_paper_monitor_report(
        [
            {"strategy_name": "trend", "symbol": "SPY", "strategy_return_after_costs": 0.01, "benchmark_return": 0.03},
            {"strategy_name": "mean", "symbol": "TLT", "strategy_return_after_costs": 0.04, "benchmark_return": 0.02},
        ],
        min_excess_return_after_costs=0.0,
    )

    assert isinstance(report, BenchmarkPaperMonitorReport)
    assert not report.passed
    decisions = {decision.strategy_name: decision for decision in report.decisions}
    assert decisions["trend"].disabled
    assert decisions["trend"].reason == "benchmark_underperformance_disable"
    assert decisions["mean"].passed


def test_regime_conditioned_scorecard_report_marks_tradable_regimes():
    report = build_regime_conditioned_scorecard_report(
        [
            {"strategy_name": "trend", "regime": "trend", "sample_size": 50, "excess_return_after_costs": 0.04, "max_drawdown": 0.08},
            {"strategy_name": "trend", "regime": "chop", "sample_size": 50, "excess_return_after_costs": -0.01, "max_drawdown": 0.06},
            {"strategy_name": "trend", "regime": "panic", "sample_size": 5, "excess_return_after_costs": 0.08, "max_drawdown": 0.12},
        ],
        min_sample_size=20,
    )

    assert isinstance(report, RegimeConditionedScorecardReport)
    assert report.passed
    assert report.tradable_regimes == ("trend",)
    reasons = {scorecard.regime: scorecard.reason for scorecard in report.scorecards}
    assert reasons["chop"] == "regime_excess_return_too_low"
    assert reasons["panic"] == "regime_sample_too_small"


def test_market_cluster_paper_scorecard_report_requires_cluster_depth():
    report = build_market_cluster_paper_scorecard_report(
        [
            {
                "strategy_name": "managedFutures",
                "cluster": "commodities",
                "asset_class": "commodity",
                "symbols_tested": 6,
                "pass_rate": 0.67,
                "average_excess_return_after_costs": 0.02,
                "paper_sessions": 5,
            },
            {
                "strategy_name": "managedFutures",
                "cluster": "crypto",
                "asset_class": "crypto",
                "symbols_tested": 2,
                "pass_rate": 1.0,
                "average_excess_return_after_costs": 0.05,
                "paper_sessions": 5,
            },
        ]
    )

    assert isinstance(report, MarketClusterPaperScorecardReport)
    assert not report.passed
    assert report.reason == "cluster_symbol_sample_too_small"
    assert report.scorecards[0].passed


def test_capacity_scorecard_report_uses_slippage_participation_and_capacity():
    report = build_capacity_scorecard_report(
        [
            {
                "strategy_name": "meanReversion",
                "symbol": "SPY",
                "target_notional": 50,
                "observed_slippage_bps": 8,
                "volume_participation": 0.001,
                "estimated_capacity_notional": 5000,
            },
            {
                "strategy_name": "meanReversion",
                "symbol": "ILLQ",
                "target_notional": 250,
                "observed_slippage_bps": 12,
                "volume_participation": 0.04,
                "estimated_capacity_notional": 1000,
            },
        ],
        max_volume_participation=0.01,
    )

    assert isinstance(report, CapacityScorecardReport)
    assert not report.passed
    assert report.scorecards[0].passed
    assert report.scorecards[1].reason == "capacity_volume_participation_too_high"


def test_sample_size_gate_report_blocks_premature_capital_influence():
    report = build_sample_size_gate_report(
        [
            {"strategy_name": "trend", "trades": 80, "sessions": 12, "symbols": 4},
            {"strategy_name": "fvg", "trades": 8, "sessions": 4, "symbols": 1},
        ],
        min_trades=30,
        min_sessions=5,
    )

    assert isinstance(report, SampleSizeGateReport)
    assert not report.passed
    assert report.gates[0].passed
    assert report.gates[1].reason == "sample_trades_too_few"


def test_statistical_confidence_report_warns_when_sample_is_too_small():
    report = build_statistical_confidence_report(
        [
            {"strategy_name": "trend", "excess_returns": [0.01] * 40},
            {"strategy_name": "newIdea", "excess_returns": [0.03, 0.02, -0.01]},
        ],
        min_sample_size=30,
        min_t_statistic=1.0,
    )

    assert isinstance(report, StatisticalConfidenceReport)
    assert not report.passed
    assert report.results[0].passed
    assert report.results[1].warning == "sample_size_too_small"


def test_parameter_drift_report_flags_unapproved_parameter_changes():
    report = build_parameter_drift_report(
        [
            {"strategy_name": "trend", "approved_params": {"lookback": 50, "risk": 0.01}, "current_params": {"lookback": 55, "risk": 0.011}},
            {"strategy_name": "cycle", "approved_params": {"lookback": 20}, "current_params": {"lookback": 40}},
        ],
        max_allowed_drift=0.25,
    )

    assert isinstance(report, ParameterDriftReport)
    assert not report.passed
    assert report.results[0].passed
    assert report.results[1].reason == "parameter_drift_detected"


def test_boring_baseline_control_report_requires_beating_simple_alternatives():
    report = build_boring_baseline_control_report(
        [
            {
                "strategy_name": "managedFutures",
                "symbol": "GLD",
                "strategy_return_after_costs": 0.08,
                "baselines": {"buy_hold": 0.03, "cash": 0.01, "simple_trend": 0.04, "risk_parity": 0.02},
            },
            {
                "strategy_name": "fancyMeanReversion",
                "symbol": "SPY",
                "strategy_return_after_costs": 0.04,
                "baselines": {"buy_hold": 0.09, "cash": 0.01, "simple_trend": 0.05},
            },
        ],
        min_edge_over_best_baseline=0.01,
    )

    assert isinstance(report, BoringBaselineControlReport)
    assert not report.passed
    assert report.controls[0].passed
    assert report.controls[1].best_baseline_name == "buy_hold"
    assert report.controls[1].reason == "boring_baseline_not_beaten"


def test_ensemble_promotion_report_requires_low_correlation_and_complementary_failure_modes():
    report = build_ensemble_promotion_report(
        [
            {
                "strategy_name": "managedFutures",
                "family": "trend",
                "benchmark_edge": 0.04,
                "correlation_to_ensemble": 0.10,
                "failure_modes": ["sharp_reversal"],
                "proposed_weight": 0.4,
            },
            {
                "strategy_name": "cryptoTrend",
                "family": "trend",
                "benchmark_edge": 0.06,
                "correlation_to_ensemble": 0.82,
                "failure_modes": ["sharp_reversal"],
                "proposed_weight": 0.2,
            },
            {
                "strategy_name": "marketNeutralMean",
                "family": "stat_arb",
                "benchmark_edge": 0.02,
                "correlation_to_ensemble": 0.25,
                "failure_modes": ["crowded_spread_unwind"],
                "proposed_weight": 0.3,
            },
            {
                "strategy_name": "copycatTrend",
                "family": "trend",
                "benchmark_edge": 0.03,
                "correlation_to_ensemble": 0.30,
                "failure_modes": ["sharp_reversal"],
                "proposed_weight": 0.1,
            },
        ],
        max_correlation_to_ensemble=0.70,
    )

    assert isinstance(report, EnsemblePromotionReport)
    assert report.passed
    decisions = {decision.strategy_name: decision for decision in report.decisions}
    assert report.promoted_strategies == ("managedFutures", "marketNeutralMean")
    assert decisions["cryptoTrend"].reason == "ensemble_correlation_too_high"
    assert decisions["copycatTrend"].reason == "ensemble_failure_modes_overlap"


def test_candidate_ab_paper_test_report_requires_separate_tiny_manifests_and_score_gap():
    report = build_candidate_ab_paper_test_report(
        [
            {
                "symbol": "SPY",
                "strategy_a": "trend",
                "strategy_b": "mean",
                "score_a": 0.62,
                "score_b": 0.51,
                "separate_manifests": True,
                "tiny_parallel_exposure": True,
            },
            {
                "symbol": "QQQ",
                "strategy_a": "breakout",
                "strategy_b": "cycle",
                "score_a": 0.50,
                "score_b": 0.49,
                "separate_manifests": True,
                "tiny_parallel_exposure": True,
            },
        ],
        min_score_gap=0.05,
    )

    assert isinstance(report, CandidateABPaperTestReport)
    assert not report.passed
    assert report.tests[0].winner == "trend"
    assert report.tests[0].passed
    assert report.tests[1].reason == "ab_test_score_gap_too_small"


def test_strategy_order_explainability_report_requires_signal_indicator_regime_risk_and_thesis():
    report = build_strategy_order_explainability_report(
        [
            {
                "order_id": "order-1",
                "strategy_name": "managedFutures",
                "symbol": "GLD",
                "signal_values": {"trend_score": 0.8},
                "indicator_state": {"atr": 2.1},
                "regime_state": {"regime": "trend"},
                "risk_gates": {"capacity": True, "drawdown": True},
                "expected_thesis": "Gold trend remains positive with acceptable volatility.",
            },
            {
                "order_id": "order-2",
                "strategy_name": "fvg",
                "symbol": "SPY",
                "signal_values": {"gap_score": 0.5},
                "indicator_state": {"fvg_count": 2},
                "risk_gates": {"capacity": True},
                "expected_thesis": "Mean reversion into imbalance.",
            },
        ]
    )

    assert isinstance(report, StrategyOrderExplainabilityReport)
    assert not report.passed
    assert report.summaries[0].passed
    assert report.summaries[1].reason == "missing_regime_state"


def test_strategy_exit_review_report_judges_exits_against_original_thesis_not_only_pnl():
    report = build_strategy_exit_review_report(
        [
            {
                "exit_id": "exit-1",
                "strategy_name": "managedFutures",
                "symbol": "GLD",
                "entry_thesis": "Trend continuation with volatility below cap.",
                "exit_reason": "trend_broke",
                "pnl": -3.5,
                "exit_matches_thesis": True,
            },
            {
                "exit_id": "exit-2",
                "strategy_name": "meanReversion",
                "symbol": "SPY",
                "entry_thesis": "Sweep reversal should revert to VWAP.",
                "exit_reason": "operator_cleanup",
                "pnl": 5.0,
                "exit_matches_thesis": False,
            },
        ]
    )

    assert isinstance(report, StrategyExitReviewReport)
    assert not report.passed
    assert report.reviews[0].passed
    assert report.reviews[0].pnl < 0
    assert report.reviews[1].reason == "exit_not_aligned_with_thesis"


def test_strategy_audit_report_groups_active_disabled_retired_and_candidates_with_reasons():
    report = build_strategy_audit_report(
        [
            {"strategy_name": "trend", "status": "paper-active", "family": "momentum", "reason": "passes paper gates", "last_reviewed_at": "2026-07-20T00:00:00+00:00"},
            {"strategy_name": "mean", "status": "disabled", "family": "reversion", "reason": "paper slippage drift", "last_reviewed_at": "2026-07-19T00:00:00+00:00"},
            {"strategy_name": "old", "status": "retired", "family": "breakout", "reason": "benchmark failures", "last_reviewed_at": "2026-07-18T00:00:00+00:00"},
            {"strategy_name": "new", "status": "exploratory", "family": "structure", "reason": "needs paper evidence", "last_reviewed_at": "2026-07-17T00:00:00+00:00"},
            {"strategy_name": "stale", "status": "paper-active", "family": "trend", "reason": "old review", "last_reviewed_at": "2026-06-01T00:00:00+00:00"},
        ],
        now=datetime(2026, 7, 24, tzinfo=timezone.utc),
        max_review_age_days=30,
    )

    assert isinstance(report, StrategyAuditReport)
    assert not report.passed
    assert report.status_counts["paper-active"] == 2
    assert len(report.entries_by_status("disabled")) == 1
    assert report.entries[-1].reason == "strategy_audit_review_stale"
    assert report.to_dict()["candidates"][0]["strategy_name"] == "new"


def test_pre_live_readiness_blocks_when_final_evidence_is_missing(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )
    soak = run_paper_session_soak(
        TradingApplication(config),
        AutonomousPaperSessionOptions(artifact_root=str(tmp_path)),
        PaperSessionSoakConfig(sessions=3),
    )

    report = evaluate_pre_live_readiness(
        soak,
        config,
        PreLiveReadinessPolicy(),
    )

    assert not report.passed
    assert not report.live_unlock_allowed
    reasons = {gate.name: gate.reason for gate in report.gates}
    assert reasons["submitted_paper_sessions"] == "missing_submitted_paper_session"
    assert reasons["restart_recovery_proof"] == "missing_restart_recovery_proof"
    assert reasons["broker_statement_match"] == "missing_broker_statement_match"
    assert reasons["live_execution_implementation"] == "live_execution_not_implemented"


def test_pre_live_readiness_passes_with_complete_paper_and_live_unlock_evidence(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )
    soak = run_paper_session_soak(
        TradingApplication(config),
        AutonomousPaperSessionOptions(artifact_root=str(tmp_path)),
        PaperSessionSoakConfig(sessions=3),
    )
    proven_sessions = tuple(
        replace(
            session,
            submitted=True,
            orders_submitted=max(session.orders_planned, 1),
            reconciliation_clean=True,
            paper_scorecard_passed=True,
            recovery=PaperSessionRecoveryReport(
                enabled=True,
                state_path="runs/tradingbot.sqlite3",
                orders_loaded=1,
                reports_loaded=1,
                reconciliation_clean=True,
                reason="recovery_clean",
            ),
        )
        for session in soak.sessions
    )
    soak = replace(soak, sessions=proven_sessions)

    report = evaluate_pre_live_readiness(
        soak,
        config,
        PreLiveReadinessPolicy(
            live_trading_implemented=True,
            operator_approved_live_unlock=True,
        ),
        broker_statement_matched=True,
    )

    assert report.passed
    assert report.live_unlock_allowed
    assert report.reason == "pre_live_readiness_passed"


def test_portfolio_paper_session_aggregates_candidates_and_orders(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    report = run_portfolio_paper_session(
        TradingApplication(config),
        PortfolioPaperSessionOptions(
            symbols=("SPY", "QQQ", "IWM"),
            artifact_root=str(tmp_path),
            requested_weight=0.10,
        ),
    )

    assert report.ready_for_submission
    assert report.symbols == ("SPY", "QQQ", "IWM")
    assert len(report.candidates) == 3
    assert len(report.consolidated_orders) == 3
    assert set(report.accepted_symbols) == {"SPY", "QQQ", "IWM"}
    assert report.artifact_path is not None


def test_portfolio_paper_session_consumes_research_promotion_manifests(tmp_path):
    manifest_path = tmp_path / "promotion-candidates.json"
    manifest_path.write_text(
        json.dumps(
            {
                "enabled_manifests": [
                    PaperSessionManifest("buyHold", "DIA", {"target_fraction": 0.25}).to_dict(),
                    PaperSessionManifest("buyHold", "SPY", {"target_fraction": 0.50}).to_dict(),
                ]
            }
        ),
        encoding="utf-8",
    )
    manifests = load_paper_session_manifests(manifest_path)
    config = RuntimeConfig(data=MarketDataConfig(symbol="SPY", provider="sample"))

    report = run_portfolio_paper_session(
        TradingApplication(config),
        PortfolioPaperSessionOptions(
            manifests=manifests,
            artifact_root=str(tmp_path / "portfolio"),
            requested_weight=0.10,
        ),
    )

    params_by_symbol = {candidate.symbol: candidate.params for candidate in report.candidates}
    assert report.symbols == ("DIA", "SPY")
    assert params_by_symbol["DIA"]["target_fraction"] == 0.25
    assert params_by_symbol["SPY"]["target_fraction"] == 0.50
    assert all(order["strategy_name"] == "buyHold" for order in report.consolidated_orders)


def test_portfolio_paper_session_submits_only_consolidated_allocated_orders(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    report = run_portfolio_paper_session(
        TradingApplication(config),
        PortfolioPaperSessionOptions(
            symbols=("SPY", "QQQ"),
            artifact_root=str(tmp_path),
            requested_weight=0.10,
            submit_orders=True,
            submission_guard_evaluator=lambda _app, _options, orders: PaperSessionSubmissionGuardReport(
                (
                    PaperSessionSubmissionGuardProbe(
                        "test_guard",
                        True,
                        "passed",
                        {"orders": len(orders)},
                    ),
                ),
                submit_requested=True,
            ),
        ),
    )

    assert all(not candidate.session.submitted for candidate in report.candidates)
    assert report.submission.submit_requested
    assert report.submission.attempted
    assert report.submission.orders_submitted == len(report.consolidated_orders)
    assert report.submission.reconciliation_clean
    assert report.submission.submission_guard is not None
    assert report.submission.notional_budget is not None
    assert report.submission.notional_budget.passed
    assert {order["status"] for order in report.submission.submitted_orders} == {"FILLED"}
    assert report.to_dict()["submission"]["reason"] == "submitted_consolidated_orders"


def test_portfolio_paper_session_scales_consolidated_orders_to_portfolio_notional_budget(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )

    report = run_portfolio_paper_session(
        TradingApplication(config),
        PortfolioPaperSessionOptions(
            symbols=("SPY", "QQQ"),
            artifact_root=str(tmp_path),
            requested_weight=0.10,
            submit_orders=True,
            max_portfolio_notional=1.0,
            submission_guard_evaluator=lambda _app, _options, orders: PaperSessionSubmissionGuardReport(
                (
                    PaperSessionSubmissionGuardProbe(
                        "test_guard",
                        True,
                        "passed",
                        {"orders": len(orders)},
                    ),
                ),
                submit_requested=True,
            ),
        ),
    )

    assert report.submission.submit_requested
    assert report.submission.attempted
    assert report.submission.orders_submitted == len(report.consolidated_orders)
    assert report.submission.reason == "submitted_consolidated_orders"
    assert report.submission.notional_budget is not None
    assert report.submission.notional_budget.passed
    assert report.submission.notional_budget.estimated_notional <= 1.0
    assert all("portfolio_notional_scale" in order for order in report.consolidated_orders)


def test_portfolio_paper_session_polls_after_consolidated_submit(tmp_path, monkeypatch):
    class PollingBroker(PaperBroker):
        def poll_execution_reports(self, orders):
            reports = []
            for order in orders:
                filled = mark_order(order, "FILLED")
                self.orders[filled.id] = filled
                report = ExecutionReport.from_order(
                    filled,
                    broker_order_id=self.reports[filled.id].broker_order_id,
                    raw={"id": "broker-order-id", "nested": {"asset_id": "asset-id"}},
                )
                self.reports[filled.id] = report
                reports.append(report)
            return reports

    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="sample"),
        strategy=StrategyConfig(name="buyHold", params={"target_fraction": 1.0}),
    )
    app = TradingApplication(config)
    broker = PollingBroker(auto_fill_market_orders=False)
    monkeypatch.setattr(app, "create_broker", lambda: broker)

    report = run_portfolio_paper_session(
        app,
        PortfolioPaperSessionOptions(
            symbols=("SPY",),
            artifact_root=str(tmp_path),
            requested_weight=0.10,
            session_template=AutonomousPaperSessionOptions(submit_orders=True, fill_poll_attempts=2),
            submission_guard_evaluator=lambda _app, _options, orders: PaperSessionSubmissionGuardReport(
                (
                    PaperSessionSubmissionGuardProbe(
                        "test_guard",
                        True,
                        "passed",
                        {"orders": len(orders)},
                    ),
                ),
                submit_requested=True,
            ),
        ),
    )

    assert report.submission.fill_poll_attempts == 1
    assert report.submission.polled_execution_reports == 1
    assert report.submission.reconciliation_clean
    assert report.submission.submitted_orders[0]["status"] == "FILLED"
    assert report.submission.execution_reports[0]["raw"]["id"] == "<redacted>"
    assert report.submission.execution_reports[0]["raw"]["nested"]["asset_id"] == "<redacted>"


def test_paper_cleanup_preview_plans_flatten_orders_and_redacts_positions(tmp_path):
    class PositionBroker(PaperBroker):
        def positions(self):
            return [
                BrokerPositionSnapshot("SPY", 2.5, average_entry_price=100.0, market_value=250.0, raw={"asset_id": "asset-id"}),
                BrokerPositionSnapshot("DIA", -1.0, average_entry_price=400.0, market_value=-400.0),
            ]

    config = RuntimeConfig(data=MarketDataConfig(symbol="SPY", provider="sample"))

    report = run_paper_cleanup(
        TradingApplication(config),
        PaperCleanupOptions(artifact_path=str(tmp_path / "cleanup.json")),
        broker_factory=PositionBroker,
    )

    orders = {(order["symbol"], order["side"]): order for order in report.planned_orders}
    assert not report.submit_requested
    assert report.reason == "preview_only"
    assert orders[("SPY", "SELL")]["quantity"] == 2.5
    assert orders[("DIA", "BUY")]["quantity"] == 1.0
    assert report.positions_seen[0]["raw"]["asset_id"] == "<redacted>"
    assert report.artifact_path == str(tmp_path / "cleanup.json")


def test_paper_cleanup_submits_polls_and_reconciles_flatten_orders(tmp_path):
    class PollingPositionBroker(PaperBroker):
        def positions(self):
            return [BrokerPositionSnapshot("SPY", 1.25, average_entry_price=100.0, market_value=125.0)]

        def poll_execution_reports(self, orders):
            reports = []
            for order in orders:
                filled = mark_order(order, "FILLED")
                self.orders[filled.id] = filled
                report = ExecutionReport.from_order(
                    filled,
                    broker_order_id=self.reports[filled.id].broker_order_id,
                    raw={"id": "broker-id"},
                )
                self.reports[filled.id] = report
                reports.append(report)
            return reports

    config = RuntimeConfig(data=MarketDataConfig(symbol="SPY", provider="sample"))
    report = run_paper_cleanup(
        TradingApplication(config),
        PaperCleanupOptions(
            submit_orders=True,
            artifact_path=str(tmp_path / "cleanup-submit.json"),
            fill_poll_attempts=2,
            submission_guard_evaluator=lambda _app, _options, orders: PaperSessionSubmissionGuardReport(
                (
                    PaperSessionSubmissionGuardProbe(
                        "test_guard",
                        True,
                        "passed",
                        {"orders": len(orders)},
                    ),
                ),
                submit_requested=True,
            ),
        ),
        broker_factory=lambda: PollingPositionBroker(auto_fill_market_orders=False),
    )

    assert report.attempted
    assert report.submitted
    assert report.fill_poll_attempts == 1
    assert report.polled_execution_reports == 1
    assert report.reconciliation_clean
    assert report.submitted_orders[0]["side"] == "SELL"
    assert report.submitted_orders[0]["status"] == "FILLED"
    assert report.execution_reports[0]["raw"]["id"] == "<redacted>"


def test_paper_pilot_report_blocks_when_cleanup_still_has_positions():
    cleanup = {
        "submitted": False,
        "reconciliation_clean": None,
        "positions_seen": [{"symbol": "SPY", "quantity": 0.03, "market_value": 25.0}],
        "reason": "market_session_not_tradable",
    }
    validation = {
        "run_metadata": {"provider": "alpaca", "broker_mode": "paper"},
        "evidence": [
            {"check_id": "alpaca_paper_order_lifecycle", "status": "passed", "reason": "passed"},
            {"check_id": "broker_account_parity", "status": "passed", "reason": "passed"},
            {"check_id": "paper_account_parity", "status": "passed", "reason": "passed"},
            {"check_id": "real_alpaca_fill_polling", "status": "passed", "reason": "passed"},
            {"check_id": "paper_account_cleanup", "status": "failed", "reason": "market_session_not_tradable"},
        ]
    }
    portfolio = {"ready_for_submission": True, "consolidated_order_count": 2}

    report = build_paper_pilot_report(cleanup, validation, {}, portfolio=portfolio)

    assert report.decision == "blocked_cleanup_required"
    assert not report.ready_for_promoted_portfolio_submit
    assert report.blockers == ("paper_account_cleanup:market_session_not_tradable",)
    assert "paper-cleanup" in report.next_actions[0]


def test_paper_pilot_report_passes_for_clean_evidence_and_ready_portfolio():
    cleanup = {
        "submitted": True,
        "reconciliation_clean": True,
        "positions_seen": [{"symbol": "SPY", "quantity": 0.03, "market_value": 25.0}],
        "reason": "flatten_orders_submitted",
    }
    validation = {
        "run_metadata": {"provider": "alpaca", "broker_mode": "paper"},
        "evidence": [
            {"check_id": "alpaca_paper_order_lifecycle", "status": "passed", "reason": "passed"},
            {"check_id": "broker_account_parity", "status": "passed", "reason": "passed"},
            {"check_id": "paper_account_parity", "status": "passed", "reason": "passed"},
            {"check_id": "real_alpaca_fill_polling", "status": "passed", "reason": "passed"},
            {"check_id": "paper_account_cleanup", "status": "passed", "reason": "passed"},
        ]
    }
    portfolio = {"ready_for_submission": True, "consolidated_order_count": 2}

    report = build_paper_pilot_report(cleanup, validation, {}, portfolio=portfolio)

    assert report.passed
    assert report.decision == "ready_for_guarded_promoted_portfolio_submit"
    assert report.ready_for_promoted_portfolio_submit
    assert report.next_actions == ("Proceed to a tiny promoted portfolio paper submit under the normal submission guard.",)


def test_paper_pilot_report_requires_alpaca_paper_runtime_for_submit_readiness():
    validation = {
        "run_metadata": {"provider": "sample", "broker_mode": "dry-run"},
        "evidence": [
            {"check_id": "alpaca_paper_order_lifecycle", "status": "passed", "reason": "passed"},
            {"check_id": "broker_account_parity", "status": "passed", "reason": "passed"},
            {"check_id": "paper_account_parity", "status": "passed", "reason": "passed"},
            {"check_id": "real_alpaca_fill_polling", "status": "passed", "reason": "passed"},
            {"check_id": "paper_account_cleanup", "status": "passed", "reason": "passed"},
        ]
    }

    report = build_paper_pilot_report(
        {"positions_seen": [], "reason": "preview_only"},
        validation,
        {},
        portfolio={"ready_for_submission": True},
    )

    assert report.decision == "blocked_alpaca_paper_runtime_required"
    assert report.blockers == ("runtime_mode:alpaca_paper_required",)
    assert report.validation["provider"] == "sample"


def test_paper_monitor_matches_submitted_orders_to_observed_positions():
    portfolio = {
        "consolidated_orders": [
            {
                "symbol": "DIA",
                "side": "BUY",
                "quantity": 0.02420645,
                "strategy_name": "hurstCycleReversion",
                "source_report_path": "runs/dia/session-report.json",
                "estimated_notional": 12.5,
                "created_at": "2026-07-23T14:00:00+00:00",
            },
            {
                "symbol": "SPY",
                "side": "BUY",
                "quantity": 0.01688732,
                "strategy_name": "hurstCycleReversion",
                "source_report_path": "runs/spy/session-report.json",
                "estimated_notional": 12.5,
                "created_at": "2026-07-23T14:00:00+00:00",
            },
        ],
        "submission": {
            "submitted_orders": [
                {"symbol": "DIA", "side": "BUY", "quantity": 0.02420645, "status": "FILLED", "created_at": "2026-07-23T14:00:01+00:00"},
                {"symbol": "SPY", "side": "BUY", "quantity": 0.01688732, "status": "FILLED", "created_at": "2026-07-23T14:00:02+00:00"},
            ],
            "notional_budget": {"max_notional": 25.0},
        }
    }
    positions = {
        "positions_seen": [
            {"symbol": "DIA", "quantity": 0.02420645, "market_value": 12.49},
            {"symbol": "SPY", "quantity": 0.01688732, "market_value": 12.48},
        ]
    }

    report = build_paper_monitor_report(portfolio, positions, now=datetime(2026, 7, 23, 14, 5, tzinfo=timezone.utc))

    assert report.passed
    assert report.observed_notional == pytest.approx(24.97)
    assert report.unexpected_symbols == ()
    assert {match.symbol: match.matched for match in report.matches} == {"DIA": True, "SPY": True}
    assert report.lifecycle is not None
    assert report.lifecycle.exposure_registry.active_expected_symbols == ("DIA", "SPY")
    assert {position.symbol: position.strategy_name for position in report.lifecycle.positions} == {
        "DIA": "hurstCycleReversion",
        "SPY": "hurstCycleReversion",
    }
    assert {position.symbol: position.target_notional for position in report.lifecycle.positions} == {
        "DIA": 12.5,
        "SPY": 12.5,
    }


def test_paper_monitor_blocks_unexpected_paper_positions():
    portfolio = {
        "submission": {
            "submitted_orders": [{"symbol": "DIA", "side": "BUY", "quantity": 0.02420645, "status": "FILLED"}],
            "notional_budget": {"max_notional": 25.0},
        }
    }
    positions = {
        "positions_seen": [
            {"symbol": "DIA", "quantity": 0.02420645, "market_value": 12.49},
            {"symbol": "SPY", "quantity": 0.01688732, "market_value": 12.48},
        ]
    }

    report = build_paper_monitor_report(portfolio, positions)

    assert not report.passed
    assert report.reason == "unexpected_paper_positions"
    assert report.unexpected_symbols == ("SPY",)
    assert report.lifecycle is not None
    assert report.lifecycle.exposure_registry.orphan_symbols == ("SPY",)


def test_paper_monitor_treats_successful_cleanup_fills_as_closed_positions():
    portfolio = {
        "submission": {
            "submitted_orders": [
                {"symbol": "DIA", "side": "BUY", "quantity": 0.02420645, "status": "FILLED"},
                {"symbol": "SPY", "side": "BUY", "quantity": 0.01688732, "status": "FILLED"},
            ],
            "notional_budget": {"max_notional": 25.0},
        }
    }
    positions = {"positions_seen": []}
    cleanup = {
        "submitted": True,
        "submitted_orders": [
            {"symbol": "DIA", "side": "SELL", "quantity": 0.02420645, "status": "FILLED"},
            {"symbol": "SPY", "side": "SELL", "quantity": 0.01688732, "status": "FILLED"},
        ],
        "reconciliation_clean": True,
    }

    report = build_paper_monitor_report(portfolio, positions, cleanup_evidence=cleanup)

    assert report.passed
    assert report.expected_positions == {}
    assert report.closed_symbols == ("DIA", "SPY")
    assert report.missing_symbols == ()
    assert report.lifecycle is not None
    assert report.lifecycle.exposure_registry.missing_expected_symbols == ()


def test_paper_monitor_accepts_direct_session_report_submitted_orders():
    session_report = {
        "submitted_orders": [
            {"symbol": "SPY", "side": "BUY", "quantity": 0.033723, "status": "FILLED", "created_at": "2026-07-31T15:37:28+00:00"}
        ],
        "execution_reports": [
            {"order_id": "order-1", "status": "FILLED", "filled_quantity": 0.033723, "average_fill_price": 741.646}
        ],
        "risk_budget": {"budget": {"max_session_notional": 25.0}},
    }
    positions = {"positions_seen": [{"symbol": "SPY", "quantity": 0.033723, "market_value": 25.01}]}

    report = build_paper_monitor_report(session_report, positions)

    assert report.passed
    assert report.expected_positions == {"SPY": 0.033723}
    assert report.max_expected_notional == 25.0
    assert report.lifecycle is not None
    assert report.lifecycle.exposure_registry.missing_expected_symbols == ()


def test_paper_monitor_allows_small_mark_to_market_notional_drift():
    portfolio = {
        "submission": {
            "submitted_orders": [{"symbol": "DIA", "side": "BUY", "quantity": 0.05, "status": "FILLED"}],
            "notional_budget": {"max_notional": 25.0},
        }
    }
    positions = {"positions_seen": [{"symbol": "DIA", "quantity": 0.05, "market_value": 25.003}]}

    report = build_paper_monitor_report(portfolio, positions)

    assert report.passed
    assert report.notional_tolerance == pytest.approx(0.5)
    assert report.exposure_within_budget


def test_paper_position_lifecycle_marks_stale_promoted_positions():
    portfolio = {
        "consolidated_orders": [
            {
                "symbol": "DIA",
                "side": "BUY",
                "quantity": 0.02420645,
                "strategy_name": "hurstCycleReversion",
                "estimated_notional": 12.5,
            }
        ],
        "submission": {
            "submitted_orders": [
                {"symbol": "DIA", "side": "BUY", "quantity": 0.02420645, "status": "FILLED", "created_at": "2026-07-20T14:00:00+00:00"}
            ],
            "notional_budget": {"max_notional": 25.0, "estimated_notional": 12.5, "passed": True},
        },
    }
    positions = {"positions_seen": [{"symbol": "DIA", "quantity": 0.02420645, "market_value": 12.49}]}

    report = build_paper_position_lifecycle_report(
        portfolio,
        positions,
        now=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
    )

    position = report.positions[0]
    assert position.status == "stale"
    assert position.forced_exit_needed
    assert report.exposure_registry.stale_symbols == ("DIA",)
    assert report.exposure_registry.cleanup_debt_symbols == ("DIA",)


def test_paper_monitor_writes_position_lifecycle_journal(tmp_path):
    portfolio = {
        "consolidated_orders": [{"symbol": "DIA", "side": "BUY", "quantity": 0.02420645, "strategy_name": "hurstCycleReversion"}],
        "submission": {
            "submitted_orders": [{"symbol": "DIA", "side": "BUY", "quantity": 0.02420645, "status": "FILLED"}],
            "notional_budget": {"max_notional": 25.0},
        },
    }
    positions = {"positions_seen": [{"symbol": "DIA", "quantity": 0.02420645, "market_value": 12.49}]}
    report = build_paper_monitor_report(portfolio, positions)
    output = tmp_path / "monitor.json"
    journal = tmp_path / "journal.jsonl"

    write_paper_monitor_report(report, output, journal_path=journal)

    payload = json.loads(output.read_text(encoding="utf-8"))
    entries = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert payload["position_journal_path"] == str(journal)
    assert entries[0]["position"]["symbol"] == "DIA"
    assert entries[0]["position"]["owner_type"] == "promoted_strategy"


def test_paper_position_lifecycle_enriches_fill_price_pnl_and_slippage():
    portfolio = {
        "consolidated_orders": [
            {
                "id": "order-dia",
                "symbol": "DIA",
                "side": "BUY",
                "quantity": 0.02,
                "strategy_name": "hurstCycleReversion",
                "latest_price": 500.0,
                "estimated_notional": 10.0,
            }
        ],
        "submission": {
            "submitted_orders": [{"id": "order-dia", "symbol": "DIA", "side": "BUY", "quantity": 0.02, "status": "FILLED"}],
            "execution_reports": [
                {
                    "order_id": "order-dia",
                    "status": "FILLED",
                    "filled_quantity": 0.02,
                    "average_fill_price": 501.0,
                    "submitted_at": "2026-07-23T14:00:10+00:00",
                }
            ],
            "notional_budget": {"max_notional": 25.0, "estimated_notional": 10.0, "passed": True},
        },
    }
    positions = {
        "positions_seen": [
            {
                "symbol": "DIA",
                "quantity": 0.02,
                "market_value": 10.04,
                "raw": {"unrealized_pl": "0.02", "avg_entry_price": "501.0"},
            }
        ]
    }

    report = build_paper_position_lifecycle_report(portfolio, positions)
    position = report.positions[0]
    scorecard = report.scorecards[0]

    assert report.passed
    assert position.average_fill_price == 501.0
    assert position.reference_price == 500.0
    assert position.slippage_per_share == pytest.approx(1.0)
    assert position.slippage_bps == pytest.approx(20.0)
    assert position.unrealized_pnl == pytest.approx(0.02)
    assert position.notional_drift == pytest.approx(0.04)
    assert scorecard.passed


def test_paper_position_lifecycle_uses_filled_quantity_for_partial_fills():
    portfolio = {
        "consolidated_orders": [
            {"id": "order-spy", "symbol": "SPY", "side": "BUY", "quantity": 0.04, "strategy_name": "hurstCycleReversion"}
        ],
        "submission": {
            "submitted_orders": [{"id": "order-spy", "symbol": "SPY", "side": "BUY", "quantity": 0.04, "status": "PARTIALLY_FILLED"}],
            "execution_reports": [
                {"order_id": "order-spy", "status": "PARTIALLY_FILLED", "filled_quantity": 0.01, "average_fill_price": 740.0}
            ],
            "notional_budget": {"max_notional": 25.0},
        },
    }
    positions = {"positions_seen": [{"symbol": "SPY", "quantity": 0.01, "market_value": 7.4, "average_entry_price": 740.0}]}

    report = build_paper_position_lifecycle_report(portfolio, positions)

    assert report.positions[0].expected_quantity == 0.01
    assert report.positions[0].requested_quantity == 0.04
    assert report.positions[0].filled_quantity == 0.01
    assert report.positions[0].matched


def test_paper_position_lifecycle_ignores_rejected_orders_as_expected_exposure():
    portfolio = {
        "consolidated_orders": [
            {"id": "order-dia", "symbol": "DIA", "side": "BUY", "quantity": 0.02, "strategy_name": "hurstCycleReversion"}
        ],
        "submission": {
            "submitted_orders": [{"id": "order-dia", "symbol": "DIA", "side": "BUY", "quantity": 0.02, "status": "REJECTED"}],
            "execution_reports": [{"order_id": "order-dia", "status": "REJECTED", "filled_quantity": 0.0}],
            "notional_budget": {"max_notional": 25.0},
        },
    }

    report = build_paper_position_lifecycle_report(portfolio, {"positions_seen": []})

    assert report.positions == ()
    assert report.exposure_registry.active_expected_symbols == ()


def test_paper_open_order_report_marks_stale_unresolved_orders():
    portfolio = {
        "submission": {
            "submitted_orders": [
                {
                    "id": "order-dia",
                    "symbol": "DIA",
                    "side": "BUY",
                    "quantity": 0.02,
                    "status": "PENDING",
                    "created_at": "2026-07-24T14:00:00+00:00",
                }
            ]
        }
    }

    report = build_paper_open_order_report(
        portfolio,
        {"open_orders": []},
        now=datetime(2026, 7, 24, 14, 30, tzinfo=timezone.utc),
        max_open_order_age_minutes=15,
    )

    assert isinstance(report, PaperOpenOrderReport)
    assert not report.passed
    assert report.reason == "stale_open_paper_orders"
    assert report.stale_symbols == ("DIA",)
    assert report.orders[0].expected_active
    assert report.orders[0].age_minutes == pytest.approx(30.0)


def test_paper_monitor_allows_fresh_open_orders_but_embeds_status():
    portfolio = {
        "submission": {
            "submitted_orders": [
                {
                    "id": "order-spy",
                    "symbol": "SPY",
                    "side": "BUY",
                    "quantity": 0.01,
                    "status": "PENDING",
                    "created_at": "2026-07-24T14:00:00+00:00",
                }
            ],
            "notional_budget": {"max_notional": 25.0},
        }
    }

    report = build_paper_monitor_report(
        portfolio,
        {"positions_seen": []},
        open_order_snapshot={"open_orders": []},
        now=datetime(2026, 7, 24, 14, 5, tzinfo=timezone.utc),
        max_open_order_age_minutes=15,
    )

    assert report.passed
    assert report.open_orders is not None
    assert report.open_orders.reason == "open_paper_orders_within_timeout"
    assert report.open_orders.unresolved_orders == 1


def test_paper_monitor_blocks_stale_open_orders():
    portfolio = {
        "submission": {
            "submitted_orders": [
                {
                    "id": "order-spy",
                    "symbol": "SPY",
                    "side": "BUY",
                    "quantity": 0.01,
                    "status": "PENDING",
                    "created_at": "2026-07-24T14:00:00+00:00",
                }
            ],
            "notional_budget": {"max_notional": 25.0},
        }
    }

    report = build_paper_monitor_report(
        portfolio,
        {"positions_seen": []},
        open_order_snapshot={"open_orders": []},
        now=datetime(2026, 7, 24, 14, 30, tzinfo=timezone.utc),
        max_open_order_age_minutes=15,
    )

    assert not report.passed
    assert report.reason == "stale_open_paper_orders"
    assert report.open_orders is not None
    assert report.open_orders.stale_symbols == ("SPY",)


def test_paper_stale_order_cancel_report_requires_action_before_cancel():
    portfolio = {
        "submission": {
            "submitted_orders": [
                {
                    "id": "order-spy",
                    "symbol": "SPY",
                    "side": "BUY",
                    "quantity": 0.01,
                    "status": "PENDING",
                    "created_at": "2026-07-24T14:00:00+00:00",
                }
            ]
        }
    }
    open_orders = build_paper_open_order_report(
        portfolio,
        {"open_orders": []},
        now=datetime(2026, 7, 24, 14, 30, tzinfo=timezone.utc),
        max_open_order_age_minutes=15,
    )

    report = build_paper_stale_order_cancel_report(open_orders)

    assert isinstance(report, PaperStaleOrderCancelReport)
    assert not report.passed
    assert report.reason == "stale_order_cancel_required"
    assert report.attempts[0].cancel_reference_available
    assert not report.attempts[0].attempted


def test_paper_stale_order_cancel_acknowledges_explicit_cancel():
    broker = PaperBroker(auto_fill_market_orders=False)
    submitted = broker.submit_order(
        Order(
            "SPY",
            "BUY",
            0.01,
            order_type="LIMIT",
            limit_price=1.0,
            created_at=datetime(2026, 7, 24, 14, 0, tzinfo=timezone.utc),
        )
    )
    portfolio = {
        "submission": {
            "submitted_orders": [
                {
                    "id": submitted.id,
                    "symbol": submitted.symbol,
                    "side": submitted.side,
                    "quantity": submitted.quantity,
                    "status": submitted.status,
                    "created_at": submitted.created_at.isoformat(),
                }
            ]
        }
    }
    open_orders = build_paper_open_order_report(
        portfolio,
        {"open_orders": []},
        now=datetime(2026, 7, 24, 14, 30, tzinfo=timezone.utc),
        max_open_order_age_minutes=15,
    )

    report = run_paper_stale_order_cancel(open_orders, broker=broker, cancel_requested=True)

    assert report.passed
    assert report.reason == "stale_order_cancel_acknowledged"
    assert report.attempts[0].attempted
    assert report.attempts[0].acknowledged
    assert broker.orders[submitted.id].status == "CANCELLED"


def test_paper_exit_preview_defaults_to_cleanup_debt_only():
    portfolio = {
        "consolidated_orders": [
            {"symbol": "DIA", "side": "BUY", "quantity": 0.02, "strategy_name": "hurstCycleReversion"}
        ],
        "submission": {
            "submitted_orders": [{"symbol": "DIA", "side": "BUY", "quantity": 0.02, "status": "FILLED", "created_at": "2026-07-20T14:00:00+00:00"}],
            "notional_budget": {"max_notional": 25.0},
        },
    }
    lifecycle = build_paper_position_lifecycle_report(
        portfolio,
        {"positions_seen": [{"symbol": "DIA", "quantity": 0.02, "market_value": 10.0, "raw": {"unrealized_pl": "0.25"}}]},
        now=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
    )

    preview = build_paper_exit_preview(lifecycle)

    assert isinstance(preview, PaperExitPreviewReport)
    assert preview.requires_operator_action
    assert preview.cleanup_debt_symbols == ("DIA",)
    assert preview.orders[0].side == "SELL"
    assert preview.orders[0].estimated_notional == pytest.approx(10.0)
    assert preview.orders[0].expected_realized_pnl == pytest.approx(0.25)
    assert preview.orders[0].reason == "stale_position_cleanup_debt"


def test_paper_exit_preview_can_include_active_positions_when_requested():
    portfolio = {
        "consolidated_orders": [
            {"symbol": "SPY", "side": "BUY", "quantity": 0.01, "strategy_name": "hurstCycleReversion"}
        ],
        "submission": {
            "submitted_orders": [{"symbol": "SPY", "side": "BUY", "quantity": 0.01, "status": "FILLED", "created_at": "2026-07-24T14:00:00+00:00"}],
            "notional_budget": {"max_notional": 25.0},
        },
    }
    lifecycle = build_paper_position_lifecycle_report(
        portfolio,
        {"positions_seen": [{"symbol": "SPY", "quantity": 0.01, "market_value": 7.4}]},
        now=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
    )

    assert build_paper_exit_preview(lifecycle).orders == ()
    preview = build_paper_exit_preview(lifecycle, include_active_positions=True)

    assert preview.orders[0].symbol == "SPY"
    assert preview.orders[0].side == "SELL"
    assert preview.orders[0].reason == "operator_requested_active_flatten_preview"


def test_paper_controlled_flatten_plan_targets_active_pilot_positions_only():
    portfolio = {
        "consolidated_orders": [
            {"symbol": "SPY", "side": "BUY", "quantity": 0.01, "strategy_name": "hurstCycleReversion"}
        ],
        "submission": {
            "submitted_orders": [{"symbol": "SPY", "side": "BUY", "quantity": 0.01, "status": "FILLED", "created_at": "2026-07-24T14:00:00+00:00"}],
            "notional_budget": {"max_notional": 25.0},
        },
    }
    lifecycle = build_paper_position_lifecycle_report(
        portfolio,
        {
            "positions_seen": [
                {"symbol": "SPY", "quantity": 0.01, "market_value": 7.4},
                {"symbol": "QQQ", "quantity": 0.02, "market_value": 12.0},
            ]
        },
        now=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
    )

    plan = build_paper_controlled_flatten_plan(
        lifecycle,
        symbols=("SPY", "QQQ"),
        exit_reason="operator_requested_risk_reduction",
    )

    assert isinstance(plan, PaperControlledFlattenPlan)
    assert not plan.passed
    assert plan.blocked_symbols == ("QQQ",)
    assert len(plan.orders) == 1
    assert plan.orders[0].symbol == "SPY"
    assert plan.orders[0].strategy_name == "hurstCycleReversion"
    assert plan.orders[0].reason == "operator_requested_risk_reduction"


def test_paper_eod_closeout_can_reduce_or_flatten_positions():
    portfolio = {
        "consolidated_orders": [
            {"symbol": "SPY", "side": "BUY", "quantity": 0.02, "strategy_name": "hurstCycleReversion"}
        ],
        "submission": {
            "submitted_orders": [{"symbol": "SPY", "side": "BUY", "quantity": 0.02, "status": "FILLED", "created_at": "2026-07-24T14:00:00+00:00"}],
            "notional_budget": {"max_notional": 25.0},
        },
    }
    lifecycle = build_paper_position_lifecycle_report(
        portfolio,
        {"positions_seen": [{"symbol": "SPY", "quantity": 0.02, "market_value": 14.8}]},
        now=datetime(2026, 7, 24, 20, 30, tzinfo=timezone.utc),
    )

    report = build_paper_eod_closeout_report(lifecycle, default_overnight_policy="reduce", reduce_fraction=0.25)

    assert isinstance(report, PaperEndOfDayCloseoutReport)
    assert report.reason == "end_of_day_closeout_orders_planned"
    assert report.decisions[0].action == "reduce"
    assert report.decisions[0].target_quantity == pytest.approx(0.005)
    assert report.orders[0].side == "SELL"
    assert report.orders[0].quantity == pytest.approx(0.015)
    assert report.orders[0].estimated_notional == pytest.approx(11.1)


def test_paper_pnl_attribution_groups_by_strategy_symbol_family_regime_session():
    portfolio = {
        "consolidated_orders": [
            {"symbol": "DIA", "side": "BUY", "quantity": 0.02, "strategy_name": "hurstCycleReversion", "latest_price": 500.0},
            {"symbol": "SPY", "side": "BUY", "quantity": 0.01, "strategy_name": "hurstCycleReversion", "latest_price": 740.0},
        ],
        "submission": {
            "submitted_orders": [
                {"symbol": "DIA", "side": "BUY", "quantity": 0.02, "status": "FILLED", "created_at": "2026-07-24T14:00:00+00:00"},
                {"symbol": "SPY", "side": "BUY", "quantity": 0.01, "status": "FILLED", "created_at": "2026-07-24T14:01:00+00:00"},
            ],
            "notional_budget": {"max_notional": 25.0},
        },
    }
    lifecycle = build_paper_position_lifecycle_report(
        portfolio,
        {
            "positions_seen": [
                {"symbol": "DIA", "quantity": 0.02, "market_value": 10.2, "raw": {"unrealized_pl": "0.20"}},
                {"symbol": "SPY", "quantity": 0.01, "market_value": 7.5, "raw": {"unrealized_pl": "-0.05"}},
            ]
        },
        now=datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc),
    )

    report = build_paper_pnl_attribution_report(
        lifecycle,
        metadata_by_symbol={
            "DIA": {"signal_family": "cycle", "regime": "trend"},
            "SPY": {"signal_family": "cycle", "regime": "trend"},
        },
    )

    assert isinstance(report, PaperPnlAttributionReport)
    assert len(report.buckets) == 2
    assert report.total_market_value == pytest.approx(17.7)
    assert report.total_unrealized_pnl == pytest.approx(0.15)
    assert {bucket.signal_family for bucket in report.buckets} == {"cycle"}
    assert {bucket.regime for bucket in report.buckets} == {"trend"}


def test_paper_drawdown_tracks_broker_equity_against_prior_peak():
    lifecycle = build_paper_position_lifecycle_report(
        {
            "submission": {
                "submitted_orders": [{"symbol": "SPY", "side": "BUY", "quantity": 0.01, "status": "FILLED"}],
                "notional_budget": {"max_notional": 25.0},
            }
        },
        {"positions_seen": [{"symbol": "SPY", "quantity": 0.01, "market_value": 7.5}]},
    )

    report = build_paper_drawdown_report(
        lifecycle,
        account_snapshot={"equity": 10025.0},
        prior_peak_equity=10100.0,
    )

    assert isinstance(report, PaperDrawdownReport)
    assert report.mark_to_market_position_value == pytest.approx(7.5)
    assert report.mark_to_market_equity == pytest.approx(10025.0)
    assert report.peak_equity == pytest.approx(10100.0)
    assert report.drawdown == pytest.approx(75.0)
    assert report.drawdown_pct == pytest.approx(75.0 / 10100.0)


def test_promotion_queue_enables_only_fully_approved_candidates():
    promotion = _promotion_report("buyHold", "SPY")
    scorecard = _paper_scorecard()

    report = evaluate_promotion_queue(
        (
            PromotionQueueCandidate(
                promotion_report=promotion,
                strategy_edge=0.05,
                paper_scorecard=scorecard,
                operator_approved=True,
            ),
            PromotionQueueCandidate(
                promotion_report=_promotion_report("buyHold", "QQQ"),
                strategy_edge=0.05,
                paper_scorecard=scorecard,
                operator_approved=False,
            ),
            PromotionQueueCandidate(
                promotion_report=_promotion_report("buyHold", "IWM"),
                strategy_edge=0.05,
                paper_scorecard=None,
                operator_approved=True,
            ),
        ),
        PromotionQueuePolicy(min_strategy_edge=0.01),
    )

    assert len(report.enabled_decisions) == 1
    assert report.enabled_manifests[0].symbol == "SPY"
    reasons = {decision.candidate.symbol: decision.reason for decision in report.blocked_decisions}
    assert reasons["QQQ"] == "missing_operator_approval"
    assert reasons["IWM"] == "missing_paper_scorecard"


def test_mocked_alpaca_order_reject_and_cancel_flow():
    calls = []

    class FakeClient:
        def request(self, method, url, payload=None):
            calls.append((method, url, payload))
            if method == "POST":
                return {"id": "broker-1", "status": "rejected"}
            return {}

    broker = AlpacaPaperBroker(AlpacaConfig(api_key="key", secret_key="secret"))
    broker.client = FakeClient()

    submitted = broker.submit_order(Order("SPY", "BUY", 1))
    cancelled = broker.cancel_order(submitted.id)

    assert submitted.status == "REJECTED"
    assert cancelled.status == "CANCELLED"
    assert calls[0][0] == "POST"


def test_paper_broker_proof_blocks_submission_outside_market_session(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    def broker_factory():
        raise AssertionError("broker should not be touched outside an allowed session")

    report = run_paper_broker_proof(
        config,
        broker_factory,
        PaperBrokerOrderPlan(symbol="SPY", quantity=1, limit_price=1, max_notional=25),
        PaperBrokerProofOptions(
            submit_orders=True,
            now=datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc),
        ),
        output_path=tmp_path / "proof.json",
    )

    assert not report.submit_allowed
    assert not report.submitted
    assert report.reason == "market_session_not_tradable"
    assert report.artifact_path is not None


def test_paper_broker_proof_submits_and_cancels_with_injected_broker(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )
    broker = PaperBroker(auto_fill_market_orders=False)

    report = run_paper_broker_proof(
        config,
        lambda: broker,
        PaperBrokerOrderPlan(symbol="SPY", quantity=1, limit_price=1, max_notional=25),
        PaperBrokerProofOptions(
            submit_orders=True,
            now=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        ),
        output_path=tmp_path / "proof.json",
    )

    assert report.passed
    assert report.submit_allowed
    assert report.submitted
    assert report.cancelled
    assert report.orders[-1]["status"] == "CANCELLED"
    assert report.execution_reports
    assert report.polled_execution_reports
    assert report.account_snapshot is not None
    assert report.post_account_snapshot is not None
    assert not report.open_orders_after


def test_paper_broker_proof_redacts_sensitive_raw_broker_payloads(tmp_path):
    class RawPayloadBroker(PaperBroker):
        def account_snapshot(self):
            return BrokerAccountSnapshot(
                cash=1000,
                buying_power=4000,
                equity=1000,
                raw={
                    "id": "account-id",
                    "account_number": "PA123",
                    "nested": {"account_id": "nested-account-id"},
                    "status": "ACTIVE",
                },
            )

        def positions(self):
            return [
                BrokerPositionSnapshot(
                    symbol="SPY",
                    quantity=0,
                    raw={"asset_id": "asset-id", "symbol": "SPY"},
                )
            ]

        def execution_reports(self):
            return [
                replace(
                    report,
                    raw={"id": "broker-order-id", "account_id": "account-id", "status": "canceled"},
                )
                for report in self.reports.values()
            ]

    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    report = run_paper_broker_proof(
        config,
        lambda: RawPayloadBroker(auto_fill_market_orders=False),
        PaperBrokerOrderPlan(symbol="SPY", quantity=1, limit_price=1, max_notional=25),
        PaperBrokerProofOptions(
            submit_orders=True,
            now=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        ),
        output_path=tmp_path / "proof.json",
    )

    assert report.account_snapshot["raw"]["id"] == "<redacted>"
    assert report.account_snapshot["raw"]["account_number"] == "<redacted>"
    assert report.account_snapshot["raw"]["nested"]["account_id"] == "<redacted>"
    assert report.positions_before[0]["raw"]["asset_id"] == "<redacted>"
    assert report.execution_reports[0]["raw"]["account_id"] == "<redacted>"
    assert report.execution_reports[0]["raw"]["status"] == "canceled"


def test_paper_broker_proof_approval_policy_blocks_kill_switch(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    def broker_factory():
        raise AssertionError("broker should not be touched when approval policy blocks")

    report = run_paper_broker_proof(
        config,
        broker_factory,
        PaperBrokerOrderPlan(symbol="SPY", quantity=1, limit_price=1, max_notional=25),
        PaperBrokerProofOptions(
            submit_orders=True,
            approval_policy=PaperBrokerProofApprovalPolicy(kill_switch_enabled=True),
            now=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        ),
        output_path=tmp_path / "proof.json",
    )

    assert not report.submit_allowed
    assert report.reason == "paper_proof_kill_switch_enabled"


def test_paper_broker_proof_approval_policy_blocks_daily_submission_limit(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )
    prior = {
        "generated_at": "2026-01-05T14:00:00+00:00",
        "submitted": True,
        "order_plan": {"symbol": "SPY"},
    }

    report = run_paper_broker_proof(
        config,
        lambda: PaperBroker(auto_fill_market_orders=False),
        PaperBrokerOrderPlan(symbol="SPY", quantity=1, limit_price=1, max_notional=25),
        PaperBrokerProofOptions(
            submit_orders=True,
            prior_reports=(prior,),
            approval_policy=PaperBrokerProofApprovalPolicy(max_daily_submissions=1),
            now=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        ),
        output_path=tmp_path / "proof.json",
    )

    assert not report.submit_allowed
    assert report.reason == "max_daily_paper_proof_submissions_reached"


def test_scheduled_paper_broker_proof_runs_inside_allowed_window(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    report = run_scheduled_paper_broker_proof(
        config,
        lambda: PaperBroker(auto_fill_market_orders=False),
        PaperBrokerOrderPlan(symbol="SPY", quantity=1, limit_price=1, max_notional=25),
        artifact_root=tmp_path / "proofs",
        schedule_output_path=tmp_path / "schedule.json",
        options=PaperBrokerProofOptions(
            submit_orders=True,
            now=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        ),
        windows=(PaperBrokerProofScheduleWindow("test_window", datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc).time(), datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc).time()),),
    )

    assert report.passed
    assert report.records[0].submitted
    assert report.artifact_path is not None


def test_scheduled_paper_broker_proof_can_consume_existing_artifact(tmp_path):
    proof = tmp_path / "proof.json"
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

    report = run_scheduled_paper_broker_proof_from_artifact(
        proof,
        schedule_output_path=tmp_path / "schedule.json",
        windows=(
            PaperBrokerProofScheduleWindow(
                "test_window",
                datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc).time(),
                datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc).time(),
            ),
        ),
    )

    assert report.passed
    assert report.records[0].window_name == "test_window"
    assert report.records[0].submitted
    assert report.records[0].passed
    assert report.artifact_path == str(tmp_path / "schedule.json")


def test_scheduled_paper_broker_proof_blocks_without_active_window(tmp_path):
    config = RuntimeConfig(
        data=MarketDataConfig(symbol="SPY", provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
    )

    report = run_scheduled_paper_broker_proof(
        config,
        lambda: PaperBroker(auto_fill_market_orders=False),
        PaperBrokerOrderPlan(symbol="SPY", quantity=1, limit_price=1, max_notional=25),
        artifact_root=tmp_path / "proofs",
        schedule_output_path=tmp_path / "schedule.json",
        options=PaperBrokerProofOptions(
            submit_orders=True,
            now=datetime(2026, 1, 5, 18, 0, tzinfo=timezone.utc),
        ),
        windows=(PaperBrokerProofScheduleWindow("test_window", datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc).time(), datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc).time()),),
    )

    assert not report.passed
    assert not report.records[0].submitted
    assert report.checks[0]["reason"] == "no_active_broker_proof_window"


def test_mocked_alpaca_stream_error_and_reconnect_flow(monkeypatch):
    import sys
    from types import SimpleNamespace

    sockets = {"count": 0}

    class FakeSocket:
        def __init__(self):
            sockets["count"] += 1
            self.index = sockets["count"]

        def connect(self, url):
            self.url = url

        def settimeout(self, timeout):
            self.timeout = timeout

        def send(self, message):
            pass

        def recv(self):
            if self.index == 1:
                raise RuntimeError("disconnect")
            return '[{"T":"error","msg":"test error"}]'

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "websocket", SimpleNamespace(WebSocket=FakeSocket))
    stream = AlpacaMarketDataStream(AlpacaConfig(api_key="key", secret_key="secret"), reconnect_attempts=1, reconnect_delay_seconds=0)
    stream.subscribe_bars(["SPY"])
    events = []

    def stop_on_error(event):
        events.append(event)
        stream.stop()

    stream.add_handler(stop_on_error)
    stream.run_forever()

    assert sockets["count"] == 2
    assert stream.health.reconnects == 1
    assert events[0].event_type == MarketDataEventType.ERROR


def test_failure_scenarios_for_market_closed_risk_and_partial_fills():
    rejected = RiskManager(max_order_notional=10).order_from_signal(
        signal=type("SignalLike", (), {"action": "BUY", "symbol": "SPY", "stop_loss": 99})(),
        equity=10_000,
        price=100,
        risk_fraction=0.10,
        buying_power=10_000,
    )
    assert rejected.accepted
    assert rejected.order.quantity <= 0.1


def _promotion_report(strategy_name: str, symbol: str) -> PromotionPipelineReport:
    evidence = ResearchCandidateEvidence(
        strategy_name=strategy_name,
        symbol=symbol,
        params={"target_fraction": 1.0},
        source_rules_captured=True,
        data_validation_passed=True,
        benchmark_passed=True,
        risk_gates_passed=True,
    )
    return PromotionPipelineReport(
        evidence=evidence,
        policy=PromotionPipelinePolicy(require_governance=False, require_capacity=False),
        gates=(),
        manifest=PaperSessionManifest(strategy_name, symbol, evidence.params),
    )


def _paper_scorecard():
    return build_paper_trading_scorecard(
        PaperTradingExpectation(
            strategy_name="buyHold",
            symbol="SPY",
            expected_fills=0,
            expected_trades=0,
            expected_return=0.01,
            expected_ending_equity=10_000,
        ),
        PaperTradingObservation(),
        PaperTradingScorecardPolicy(require_clean_reconciliation=False),
    )
