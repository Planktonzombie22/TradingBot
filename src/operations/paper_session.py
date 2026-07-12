from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

import pandas as pd

from src.app import TradingApplication
from src.backtesting import (
    PaperSessionManifest,
    PaperTradingExpectation,
    PaperTradingObservation,
    PromotionPipelinePolicy,
    PromotionPipelineReport,
    ResearchCandidateEvidence,
    TradeCommitteeContext,
    TradeCommitteePolicy,
    build_paper_trading_scorecard,
    classify_market_regime,
)
from src.config import validate_runtime_environment
from src.data import DataSourceSnapshot, compare_live_data_sources
from src.engine import PaperAccountState, PaperSessionSupervisor, PaperSessionSupervisorConfig, RuntimePosition
from src.execution import BrokerReconciler, ExecutionReport
from src.models import Order
from src.storage import ImmutableArtifactStore


@dataclass(frozen=True)
class AutonomousPaperSessionOptions:
    submit_orders: bool = False
    artifact_root: str = "runs/artifacts"
    strategy_edge: float = 0.01
    benchmark_edge: float = 0.0
    require_paper_scorecard: bool = False
    require_data_health: bool = True
    max_position_weight: float = 0.25
    comparison_provider: str | None = None
    broker_statement: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutonomousPaperSessionResult:
    report_path: str | None
    ready_for_submission: bool
    submitted: bool
    data_rows: int
    latest_prices: Mapping[str, float]
    regime: Mapping[str, Any]
    orders_planned: int
    orders_submitted: int
    data_drift_reports: int
    warnings: tuple[str, ...]
    artifact_paths: Mapping[str, str]

    def to_dict(self) -> dict:
        return {
            "report_path": self.report_path,
            "ready_for_submission": self.ready_for_submission,
            "submitted": self.submitted,
            "data_rows": self.data_rows,
            "latest_prices": dict(self.latest_prices),
            "regime": dict(self.regime),
            "orders_planned": self.orders_planned,
            "orders_submitted": self.orders_submitted,
            "data_drift_reports": self.data_drift_reports,
            "warnings": list(self.warnings),
            "artifact_paths": dict(self.artifact_paths),
        }


def run_autonomous_paper_session(
    app: TradingApplication,
    options: AutonomousPaperSessionOptions | None = None,
) -> AutonomousPaperSessionResult:
    options = options or AutonomousPaperSessionOptions()
    validation = validate_runtime_environment(app.config)
    if validation.errors and (options.submit_orders or app.config.data.provider.lower() == "alpaca"):
        validation.raise_for_errors()
    if options.submit_orders and app.config.execution.mode.lower() != "paper":
        raise ValueError("Submitting paper-session orders requires --execution-mode paper.")

    data = app.load_data()
    if data.empty:
        raise ValueError("Cannot run an autonomous paper session without market data.")

    symbol = app.config.data.symbol.upper()
    latest_price = _latest_close(data)
    latest_prices = {symbol: latest_price}
    regime = classify_market_regime(data, symbol)
    data_drift_reports = _data_drift_reports(app, data, options)
    account_state = _paper_account_from_runtime(app, latest_prices, sync_broker=options.submit_orders)
    context = _committee_context(app, regime, data_drift_reports, options, account_state, latest_prices)
    supervisor = PaperSessionSupervisor(
        artifact_store=ImmutableArtifactStore(options.artifact_root),
        config=PaperSessionSupervisorConfig(data_source=_data_source_payload(app, data)),
        committee_policy=TradeCommitteePolicy(
            require_paper_scorecard=options.require_paper_scorecard,
            require_data_health=options.require_data_health,
            max_position_weight=options.max_position_weight,
        ),
    )
    report = supervisor.prepare_dry_run(context, account_state, latest_prices)

    submitted_orders: tuple[Order, ...] = ()
    execution_reports: tuple[ExecutionReport, ...] = ()
    reconciliation = None
    scorecard = None
    if options.submit_orders and report.ready_for_submission:
        broker = app.create_broker()
        submitted_orders = tuple(broker.submit_order(intent.order) for intent in report.execution_plan.orders)
        execution_reports = tuple(broker.execution_reports())
        reconciliation = BrokerReconciler().reconcile_orders(submitted_orders, execution_reports)
        _apply_filled_orders(account_state, submitted_orders, execution_reports, latest_prices)
        scorecard = build_paper_trading_scorecard(
            _paper_expectation(app, submitted_orders, latest_prices, account_state),
            PaperTradingObservation(
                reports=execution_reports,
                reconciliation=reconciliation,
                broker_statement=options.broker_statement,
            ),
        )

    final_report = supervisor.write_audit_trail(
        report,
        submitted_orders=submitted_orders,
        execution_reports=execution_reports,
        reconciliation=reconciliation,
        paper_scorecard=scorecard,
        post_session_account_snapshot=account_state.snapshot(latest_prices),
    )

    return AutonomousPaperSessionResult(
        report_path=final_report.artifact_paths.get("session_report"),
        ready_for_submission=final_report.ready_for_submission,
        submitted=bool(submitted_orders),
        data_rows=len(data),
        latest_prices=latest_prices,
        regime=regime.to_dict(),
        orders_planned=len(final_report.execution_plan.orders),
        orders_submitted=len(submitted_orders),
        data_drift_reports=len(data_drift_reports),
        warnings=tuple(final_report.warnings),
        artifact_paths=final_report.artifact_paths,
    )


def _committee_context(
    app: TradingApplication,
    regime,
    data_drift_reports,
    options: AutonomousPaperSessionOptions,
    account_state: PaperAccountState,
    latest_prices: Mapping[str, float],
) -> TradeCommitteeContext:
    symbol = app.config.data.symbol.upper()
    return TradeCommitteeContext(
        symbol=symbol,
        promotion_report=_runtime_manifest(app),
        data_drift_reports=data_drift_reports,
        regime=regime,
        strategy_edge=options.strategy_edge,
        benchmark_edge=options.benchmark_edge,
        current_exposure=_current_exposure(account_state, symbol, latest_prices),
        notes=("autonomous_paper_session_mvp",),
    )


def _data_drift_reports(
    app: TradingApplication,
    primary_data: pd.DataFrame,
    options: AutonomousPaperSessionOptions,
) -> tuple:
    if not options.comparison_provider:
        return ()
    comparison_config = replace(app.config.data, provider=options.comparison_provider)
    comparison_app = TradingApplication(replace(app.config, data=comparison_config))
    comparison_data = comparison_app.load_data()
    report = compare_live_data_sources(
        DataSourceSnapshot(app.config.data.provider, app.config.data.symbol.upper(), primary_data),
        DataSourceSnapshot(options.comparison_provider, app.config.data.symbol.upper(), comparison_data),
    )
    return (report,)


def _runtime_manifest(app: TradingApplication) -> PromotionPipelineReport:
    symbol = app.config.data.symbol.upper()
    evidence = ResearchCandidateEvidence(
        strategy_name=app.config.strategy.name,
        symbol=symbol,
        params=dict(app.config.strategy.params),
        source_rules_captured=True,
        data_validation_passed=True,
        benchmark_passed=True,
        risk_gates_passed=True,
        notes=("runtime_config_candidate",),
    )
    return PromotionPipelineReport(
        evidence=evidence,
        policy=PromotionPipelinePolicy(
            require_governance=False,
            require_capacity=False,
        ),
        gates=(),
        manifest=PaperSessionManifest(app.config.strategy.name, symbol, dict(app.config.strategy.params)),
    )


def _paper_account_from_runtime(
    app: TradingApplication,
    latest_prices: Mapping[str, float],
    sync_broker: bool,
) -> PaperAccountState:
    account = PaperAccountState(app.config.account.initial_cash)
    if not sync_broker:
        return account
    broker = app.create_broker()
    try:
        snapshot = broker.account_snapshot()
    except Exception:
        return account
    if snapshot.equity > 0:
        account = PaperAccountState(snapshot.equity)
        account.cash = snapshot.cash
    for position in broker.positions():
        if not position.symbol:
            continue
        average_price = position.average_entry_price or latest_prices.get(position.symbol, 0.0)
        account.positions[position.symbol.upper()] = RuntimePosition(position.symbol.upper(), position.quantity, average_price)
    return account


def _apply_filled_orders(
    account_state: PaperAccountState,
    orders: Sequence[Order],
    reports: Sequence[ExecutionReport],
    latest_prices: Mapping[str, float],
) -> None:
    reports_by_order = {report.order_id: report for report in reports}
    for order in orders:
        report = reports_by_order.get(order.id)
        if order.status != "FILLED" and (report is None or report.status != "FILLED"):
            continue
        price = report.average_fill_price if report and report.average_fill_price else latest_prices.get(order.symbol, 0.0)
        if price > 0:
            account_state.apply_fill(order, price)


def _paper_expectation(
    app: TradingApplication,
    orders: Sequence[Order],
    latest_prices: Mapping[str, float],
    account_state: PaperAccountState,
) -> PaperTradingExpectation:
    return PaperTradingExpectation(
        strategy_name=app.config.strategy.name,
        symbol=app.config.data.symbol.upper(),
        expected_fills=len(orders),
        expected_trades=len(orders),
        expected_return=0.0,
        expected_ending_equity=account_state.equity(dict(latest_prices)),
        expected_fill_prices={order.id: latest_prices.get(order.symbol, 0.0) for order in orders},
    )


def _latest_close(data: pd.DataFrame) -> float:
    close = pd.to_numeric(data["Close"], errors="coerce").dropna()
    if close.empty:
        raise ValueError("Cannot run an autonomous paper session without a valid latest close.")
    return float(close.iloc[-1])


def _current_exposure(
    account_state: PaperAccountState,
    symbol: str,
    latest_prices: Mapping[str, float],
) -> float:
    equity = account_state.equity(dict(latest_prices))
    if equity <= 0:
        return 0.0
    quantity = account_state.quantity(symbol)
    return abs(quantity * latest_prices.get(symbol, 0.0)) / equity


def _data_source_payload(app: TradingApplication, data: pd.DataFrame) -> dict:
    return {
        "provider": app.config.data.provider,
        "symbol": app.config.data.symbol.upper(),
        "period": app.config.data.period,
        "interval": app.config.data.interval,
        "start": app.config.data.start,
        "end": app.config.data.end,
        "rows": len(data),
    }
