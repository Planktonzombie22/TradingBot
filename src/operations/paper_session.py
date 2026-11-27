from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import time
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
from src.data import DataSourceSnapshot, MarketSessionCalendar, MarketSessionPolicy, compare_live_data_sources
from src.engine import CommitteeExecutionPolicy, PaperAccountState, PaperSessionSupervisor, PaperSessionSupervisorConfig, RuntimePosition
from src.execution import BrokerAccountSnapshot, BrokerPositionSnapshot, BrokerReconciler, ExecutionReport
from src.models import Order
from src.storage import ImmutableArtifactStore, SQLiteStateStore

from .paper_broker_proof import PaperBrokerProofApprovalPolicy


@dataclass(frozen=True)
class PaperSessionRecoveryReport:
    enabled: bool
    state_path: str | None = None
    orders_loaded: int = 0
    reports_loaded: int = 0
    positions_loaded: int = 0
    account_loaded: bool = False
    reconciliation_clean: bool | None = None
    unresolved_orders: int = 0
    blocked: bool = False
    reason: str = "not_enabled"

    @property
    def passed(self) -> bool:
        return not self.blocked

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "state_path": self.state_path,
            "orders_loaded": self.orders_loaded,
            "reports_loaded": self.reports_loaded,
            "positions_loaded": self.positions_loaded,
            "account_loaded": self.account_loaded,
            "reconciliation_clean": self.reconciliation_clean,
            "unresolved_orders": self.unresolved_orders,
            "blocked": self.blocked,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperSessionRiskBudget:
    min_order_quantity: float = 0.0
    min_order_notional: float = 0.0
    max_session_notional: float | None = None
    max_new_exposure: float | None = None
    max_turnover: float | None = None
    cash_reserve: float = 0.0
    cooldown_symbols: tuple[str, ...] = ()
    repeated_reject_symbols: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "min_order_quantity": self.min_order_quantity,
            "min_order_notional": self.min_order_notional,
            "max_session_notional": self.max_session_notional,
            "max_new_exposure": self.max_new_exposure,
            "max_turnover": self.max_turnover,
            "cash_reserve": self.cash_reserve,
            "cooldown_symbols": list(self.cooldown_symbols),
            "repeated_reject_symbols": list(self.repeated_reject_symbols),
        }


@dataclass(frozen=True)
class PaperSessionRiskBudgetGate:
    name: str
    passed: bool
    reason: str
    value: float | str | None = None
    threshold: float | str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "value": self.value,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class PaperSessionRiskBudgetReport:
    budget: PaperSessionRiskBudget
    gates: tuple[PaperSessionRiskBudgetGate, ...]
    session_notional: float = 0.0
    new_exposure: float = 0.0
    turnover: float = 0.0

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def reason(self) -> str:
        if self.passed:
            return "risk_budget_passed"
        return next(gate.reason for gate in self.gates if not gate.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "budget": self.budget.to_dict(),
            "session_notional": self.session_notional,
            "new_exposure": self.new_exposure,
            "turnover": self.turnover,
            "gates": [gate.to_dict() for gate in self.gates],
        }


@dataclass(frozen=True)
class PaperSessionSubmissionGuardProbe:
    name: str
    passed: bool
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperSessionSubmissionGuardReport:
    probes: tuple[PaperSessionSubmissionGuardProbe, ...]
    submit_requested: bool

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    @property
    def reason(self) -> str:
        if self.passed:
            return "submission_guard_passed"
        return next(probe.reason for probe in self.probes if not probe.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "submit_requested": self.submit_requested,
            "probes": [probe.to_dict() for probe in self.probes],
        }


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
    recover_state: bool = False
    require_clean_recovery: bool = True
    sync_broker_state: bool = False
    state_db_path: str | None = None
    persist_state: bool = True
    risk_budget: PaperSessionRiskBudget | None = None
    broker_statement: Mapping[str, Any] = field(default_factory=dict)
    submission_approval_policy: PaperBrokerProofApprovalPolicy | None = None
    prior_broker_proof_reports: tuple[Mapping[str, Any], ...] = ()
    execution_policy: CommitteeExecutionPolicy | None = None
    fill_poll_attempts: int = 1
    fill_poll_interval_seconds: float = 0.0


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
    planned_orders: tuple[Mapping[str, Any], ...] = ()
    reconciliation_clean: bool | None = None
    paper_scorecard_passed: bool | None = None
    recovery: PaperSessionRecoveryReport = field(default_factory=lambda: PaperSessionRecoveryReport(enabled=False))
    risk_budget: PaperSessionRiskBudgetReport | None = None
    submission_guard: PaperSessionSubmissionGuardReport | None = None
    fill_poll_attempts: int = 0
    polled_execution_reports: int = 0

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
            "planned_orders": [dict(order) for order in self.planned_orders],
            "data_drift_reports": self.data_drift_reports,
            "reconciliation_clean": self.reconciliation_clean,
            "paper_scorecard_passed": self.paper_scorecard_passed,
            "recovery": self.recovery.to_dict(),
            "risk_budget": self.risk_budget.to_dict() if self.risk_budget else None,
            "submission_guard": self.submission_guard.to_dict() if self.submission_guard else None,
            "fill_poll_attempts": self.fill_poll_attempts,
            "polled_execution_reports": self.polled_execution_reports,
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
    recovery = _recover_previous_state(app, options)
    account_state = _paper_account_from_runtime(
        app,
        latest_prices,
        sync_broker=options.submit_orders or options.sync_broker_state,
        recovery=recovery,
    )
    context = _committee_context(app, regime, data_drift_reports, options, account_state, latest_prices)
    artifact_store = ImmutableArtifactStore(options.artifact_root)
    supervisor = PaperSessionSupervisor(
        artifact_store=artifact_store,
        config=PaperSessionSupervisorConfig(data_source=_data_source_payload(app, data)),
        committee_policy=TradeCommitteePolicy(
            require_paper_scorecard=options.require_paper_scorecard,
            require_data_health=options.require_data_health,
            max_position_weight=options.max_position_weight,
        ),
        execution_policy=options.execution_policy,
    )
    report = supervisor.prepare_dry_run(context, account_state, latest_prices)
    risk_budget_report = _evaluate_risk_budget(
        options.risk_budget,
        tuple(intent.order for intent in report.execution_plan.orders),
        latest_prices,
        account_state,
    )
    submission_guard = _evaluate_submission_guard(
        app,
        options,
        tuple(intent.order for intent in report.execution_plan.orders),
    )

    submitted_orders: tuple[Order, ...] = ()
    execution_reports: tuple[ExecutionReport, ...] = ()
    fill_poll_attempts = 0
    polled_execution_reports = 0
    reconciliation = None
    scorecard = None
    recovery_blocked = recovery.blocked and options.require_clean_recovery
    risk_blocked = risk_budget_report is not None and not risk_budget_report.passed
    submission_guard_blocked = options.submit_orders and not submission_guard.passed
    if options.submit_orders and report.ready_for_submission and not recovery_blocked and not risk_blocked and not submission_guard_blocked:
        broker = app.create_broker()
        submitted_orders = tuple(broker.submit_order(intent.order) for intent in report.execution_plan.orders)
        execution_reports = tuple(broker.execution_reports())
        polled = _poll_broker_execution_reports(broker, submitted_orders, options)
        if polled:
            fill_poll_attempts, execution_reports = polled
            polled_execution_reports = len(execution_reports)
            submitted_orders = _latest_broker_orders(broker, submitted_orders)
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
        if options.persist_state:
            _persist_broker_state(app, options, account_state, latest_prices, submitted_orders, execution_reports)

    final_report = supervisor.write_audit_trail(
        report,
        submitted_orders=submitted_orders,
        execution_reports=execution_reports,
        reconciliation=reconciliation,
        paper_scorecard=scorecard,
        post_session_account_snapshot=account_state.snapshot(latest_prices),
    )
    artifact_paths = dict(final_report.artifact_paths)
    artifact_paths["recovery"] = str(artifact_store.write_json(final_report.manifest, "recovery.json", recovery.to_dict(), overwrite=True))
    if risk_budget_report:
        artifact_paths["risk_budget"] = str(
            artifact_store.write_json(final_report.manifest, "risk-budget.json", risk_budget_report.to_dict(), overwrite=True)
        )
    artifact_paths["submission_guard"] = str(
        artifact_store.write_json(final_report.manifest, "submission-guard.json", submission_guard.to_dict(), overwrite=True)
    )
    warnings = tuple(final_report.warnings)
    if recovery_blocked:
        warnings = warnings + (f"Recovery blocked submission: {recovery.reason}",)
    if risk_blocked and risk_budget_report:
        warnings = warnings + (f"Risk budget blocked submission: {risk_budget_report.reason}",)
    if submission_guard_blocked:
        warnings = warnings + (f"Submission guard blocked broker routing: {submission_guard.reason}",)

    result = AutonomousPaperSessionResult(
        report_path=final_report.artifact_paths.get("session_report"),
        ready_for_submission=final_report.ready_for_submission and not recovery_blocked and not risk_blocked and not submission_guard_blocked,
        submitted=bool(submitted_orders),
        data_rows=len(data),
        latest_prices=latest_prices,
        regime=regime.to_dict(),
        orders_planned=len(final_report.execution_plan.orders),
        orders_submitted=len(submitted_orders),
        planned_orders=tuple(_planned_order_payload(intent.order) for intent in final_report.execution_plan.orders),
        data_drift_reports=len(data_drift_reports),
        reconciliation_clean=reconciliation.is_clean if reconciliation else None,
        paper_scorecard_passed=scorecard.passed if scorecard else None,
        recovery=recovery,
        risk_budget=risk_budget_report,
        submission_guard=submission_guard,
        fill_poll_attempts=fill_poll_attempts,
        polled_execution_reports=polled_execution_reports,
        warnings=warnings,
        artifact_paths=artifact_paths,
    )
    session_result_path = artifact_store.write_json(
        final_report.manifest,
        "paper-session-result.json",
        result.to_dict(),
        overwrite=True,
    )
    return replace(result, artifact_paths={**dict(result.artifact_paths), "paper_session_result": str(session_result_path)})


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
    recovery: PaperSessionRecoveryReport,
) -> PaperAccountState:
    account = PaperAccountState(app.config.account.initial_cash)
    if recovery.enabled and recovery.state_path:
        state = SQLiteStateStore(recovery.state_path).load_broker_state()
        if state.account and state.account.equity > 0:
            account = PaperAccountState(state.account.equity)
            account.cash = state.account.cash
        for position in state.positions:
            if not position.symbol:
                continue
            average_price = position.average_entry_price or latest_prices.get(position.symbol.upper(), 0.0)
            account.positions[position.symbol.upper()] = RuntimePosition(position.symbol.upper(), position.quantity, average_price)
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


def _recover_previous_state(
    app: TradingApplication,
    options: AutonomousPaperSessionOptions,
) -> PaperSessionRecoveryReport:
    if not options.recover_state:
        return PaperSessionRecoveryReport(enabled=False)
    path = options.state_db_path or app.config.execution.state_db_path
    state = SQLiteStateStore(path).load_broker_state()
    reconciliation = BrokerReconciler().reconcile_orders(state.orders, state.reports)
    unresolved = len(reconciliation.unresolved)
    blocked = options.require_clean_recovery and not reconciliation.is_clean
    if not state.orders and not state.reports and not state.account and not state.positions:
        reason = "no_prior_state"
    elif reconciliation.is_clean:
        reason = "recovery_clean"
    else:
        reason = "unresolved_prior_state"
    return PaperSessionRecoveryReport(
        enabled=True,
        state_path=str(path),
        orders_loaded=len(state.orders),
        reports_loaded=len(state.reports),
        positions_loaded=len(state.positions),
        account_loaded=state.account is not None,
        reconciliation_clean=reconciliation.is_clean,
        unresolved_orders=unresolved,
        blocked=blocked,
        reason=reason,
    )


def _persist_broker_state(
    app: TradingApplication,
    options: AutonomousPaperSessionOptions,
    account_state: PaperAccountState,
    latest_prices: Mapping[str, float],
    orders: Sequence[Order],
    reports: Sequence[ExecutionReport],
) -> None:
    path = options.state_db_path or app.config.execution.state_db_path
    store = SQLiteStateStore(path)
    snapshot = account_state.snapshot(dict(latest_prices))
    store.save_account_snapshot(
        BrokerAccountSnapshot(
            cash=float(snapshot["cash"]),
            buying_power=float(snapshot["cash"]),
            equity=float(snapshot["equity"]),
            raw={"source": "paper_session"},
        )
    )
    store.save_position_snapshots(
        [
            BrokerPositionSnapshot(
                symbol=symbol,
                quantity=float(position["quantity"]),
                average_entry_price=float(position["average_price"]),
                market_value=float(position["market_value"]),
                raw={"source": "paper_session"},
            )
            for symbol, position in snapshot["positions"].items()
        ]
    )
    for order in orders:
        store.save_order(order)
    for report in reports:
        store.save_execution_report(report)


def _poll_broker_execution_reports(
    broker: Any,
    orders: Sequence[Order],
    options: AutonomousPaperSessionOptions,
) -> tuple[int, tuple[ExecutionReport, ...]] | None:
    poll = getattr(broker, "poll_execution_reports", None)
    attempts = max(int(options.fill_poll_attempts), 0)
    if poll is None or attempts <= 0 or not orders:
        return None
    reports: tuple[ExecutionReport, ...] = ()
    completed_attempts = 0
    for attempt in range(attempts):
        completed_attempts = attempt + 1
        reports = tuple(poll(orders))
        if reports and all(report.status in {"FILLED", "CANCELLED", "REJECTED"} for report in reports):
            break
        if attempt + 1 < attempts and options.fill_poll_interval_seconds > 0:
            time.sleep(options.fill_poll_interval_seconds)
    return completed_attempts, reports


def _latest_broker_orders(broker: Any, orders: Sequence[Order]) -> tuple[Order, ...]:
    broker_orders = getattr(broker, "orders", None)
    if not isinstance(broker_orders, Mapping):
        return tuple(orders)
    return tuple(broker_orders.get(order.id, order) for order in orders)


def _evaluate_risk_budget(
    budget: PaperSessionRiskBudget | None,
    orders: Sequence[Order],
    latest_prices: Mapping[str, float],
    account_state: PaperAccountState,
) -> PaperSessionRiskBudgetReport | None:
    if budget is None:
        return None
    equity = account_state.equity(dict(latest_prices))
    order_payloads = []
    for order in orders:
        price = latest_prices.get(order.symbol, 0.0)
        notional = abs(float(order.quantity) * float(price))
        order_payloads.append((order, price, notional))
    session_notional = sum(item[2] for item in order_payloads)
    new_exposure = session_notional / equity if equity > 0 else 0.0
    turnover = session_notional / equity if equity > 0 else 0.0
    gates: list[PaperSessionRiskBudgetGate] = []

    for order, _, notional in order_payloads:
        symbol = order.symbol.upper()
        gates.append(
            PaperSessionRiskBudgetGate(
                f"{symbol}_min_quantity",
                float(order.quantity) >= budget.min_order_quantity,
                "min_quantity_passed" if float(order.quantity) >= budget.min_order_quantity else "order_quantity_below_minimum",
                float(order.quantity),
                budget.min_order_quantity,
            )
        )
        gates.append(
            PaperSessionRiskBudgetGate(
                f"{symbol}_min_notional",
                notional >= budget.min_order_notional,
                "min_notional_passed" if notional >= budget.min_order_notional else "order_notional_below_minimum",
                notional,
                budget.min_order_notional,
            )
        )
        cooldown = {item.upper() for item in budget.cooldown_symbols}
        gates.append(
            PaperSessionRiskBudgetGate(
                f"{symbol}_cooldown",
                symbol not in cooldown,
                "cooldown_passed" if symbol not in cooldown else "symbol_in_cooldown",
                symbol,
                "not_in_cooldown",
            )
        )
        rejects = {item.upper() for item in budget.repeated_reject_symbols}
        gates.append(
            PaperSessionRiskBudgetGate(
                f"{symbol}_repeated_reject",
                symbol not in rejects,
                "repeated_reject_passed" if symbol not in rejects else "symbol_locked_after_repeated_rejects",
                symbol,
                "not_repeated_reject",
            )
        )

    gates.append(_optional_max_gate("max_session_notional", session_notional, budget.max_session_notional, "session_notional_above_budget"))
    gates.append(_optional_max_gate("max_new_exposure", new_exposure, budget.max_new_exposure, "new_exposure_above_budget"))
    gates.append(_optional_max_gate("max_turnover", turnover, budget.max_turnover, "turnover_above_budget"))
    cash_after_orders = max(account_state.cash - session_notional, 0.0)
    cash_reserve = cash_after_orders / equity if equity > 0 else 0.0
    gates.append(
        PaperSessionRiskBudgetGate(
            "cash_reserve",
            cash_reserve >= budget.cash_reserve,
            "cash_reserve_passed" if cash_reserve >= budget.cash_reserve else "cash_reserve_below_budget",
            cash_reserve,
            budget.cash_reserve,
        )
    )
    return PaperSessionRiskBudgetReport(
        budget=budget,
        gates=tuple(gates),
        session_notional=session_notional,
        new_exposure=new_exposure,
        turnover=turnover,
    )


def _evaluate_submission_guard(
    app: TradingApplication,
    options: AutonomousPaperSessionOptions,
    orders: Sequence[Order],
) -> PaperSessionSubmissionGuardReport:
    if not options.submit_orders:
        return PaperSessionSubmissionGuardReport(
            (
                PaperSessionSubmissionGuardProbe(
                    "submit_requested",
                    True,
                    "submit_not_requested",
                    {"submit_orders": False},
                ),
            ),
            submit_requested=False,
        )
    now = datetime.now(timezone.utc)
    calendar = MarketSessionCalendar()
    policy = MarketSessionPolicy(
        allow_pre_market=app.config.schedule.allow_pre_market,
        allow_regular=True,
        allow_after_hours=app.config.schedule.allow_after_hours,
    )
    policy_config = options.submission_approval_policy
    symbols = sorted({order.symbol.upper() for order in orders})
    session_tradable = calendar.is_tradable_at(now, policy)
    session = calendar.session_at(now)
    probes = [
        PaperSessionSubmissionGuardProbe(
            "submit_requested",
            True,
            "passed",
            {"submit_orders": True, "orders": len(orders)},
        ),
        PaperSessionSubmissionGuardProbe(
            "market_session",
            session_tradable,
            "passed" if session_tradable else "market_session_not_tradable",
            {"timestamp": now.isoformat(), "session": session.value, "policy": _session_policy_payload(policy)},
        ),
        PaperSessionSubmissionGuardProbe(
            "orders_present",
            bool(orders),
            "passed" if orders else "no_orders_to_submit",
            {"orders": len(orders)},
        ),
    ]
    if policy_config is None:
        probes.append(PaperSessionSubmissionGuardProbe("approval_policy", True, "not_configured", {"configured": False}))
        return PaperSessionSubmissionGuardReport(tuple(probes), submit_requested=True)

    allowlist = {symbol.upper() for symbol in policy_config.symbol_allowlist}
    disallowed = sorted(symbol for symbol in symbols if allowlist and symbol not in allowlist)
    submitted_today = _submitted_reports_today(options.prior_broker_proof_reports, now)
    rejected_symbols = {
        symbol: _rejected_reports(options.prior_broker_proof_reports, symbol)
        for symbol in symbols
    }
    repeated_rejects = {
        symbol: count
        for symbol, count in rejected_symbols.items()
        if policy_config.repeated_reject_lockout_threshold is not None and count >= policy_config.repeated_reject_lockout_threshold
    }
    daily_limit_ok = policy_config.max_daily_submissions is None or submitted_today < policy_config.max_daily_submissions
    probes.extend(
        [
            PaperSessionSubmissionGuardProbe(
                "approval_policy",
                True,
                "passed",
                {"configured": True, "policy": policy_config.to_dict()},
            ),
            PaperSessionSubmissionGuardProbe(
                "approval_kill_switch",
                not policy_config.kill_switch_enabled,
                "passed" if not policy_config.kill_switch_enabled else "paper_session_kill_switch_enabled",
                {"kill_switch_enabled": policy_config.kill_switch_enabled},
            ),
            PaperSessionSubmissionGuardProbe(
                "approval_symbol_allowlist",
                not disallowed,
                "passed" if not disallowed else "symbol_not_allowed_for_paper_session",
                {"symbols": symbols, "symbol_allowlist": sorted(allowlist), "disallowed": disallowed},
            ),
            PaperSessionSubmissionGuardProbe(
                "approval_daily_submission_limit",
                daily_limit_ok,
                "passed" if daily_limit_ok else "max_daily_paper_session_submissions_reached",
                {"submitted_today": submitted_today, "max_daily_submissions": policy_config.max_daily_submissions},
            ),
            PaperSessionSubmissionGuardProbe(
                "approval_repeated_reject_lockout",
                not repeated_rejects,
                "passed" if not repeated_rejects else "repeated_reject_lockout_active",
                {"rejected_symbols": repeated_rejects, "threshold": policy_config.repeated_reject_lockout_threshold},
            ),
        ]
    )
    return PaperSessionSubmissionGuardReport(tuple(probes), submit_requested=True)


def evaluate_paper_session_submission_guard(
    app: TradingApplication,
    options: AutonomousPaperSessionOptions,
    orders: Sequence[Order],
) -> PaperSessionSubmissionGuardReport:
    return _evaluate_submission_guard(app, options, orders)


def _optional_max_gate(name: str, value: float, threshold: float | None, failure_reason: str) -> PaperSessionRiskBudgetGate:
    if threshold is None:
        return PaperSessionRiskBudgetGate(name, True, "not_required", value, None)
    return PaperSessionRiskBudgetGate(
        name,
        value <= threshold,
        "budget_passed" if value <= threshold else failure_reason,
        value,
        threshold,
    )


def _planned_order_payload(order: Order) -> dict:
    return {
        "id": order.id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "order_type": order.order_type,
        "limit_price": order.limit_price,
        "stop_price": order.stop_price,
        "take_profit_price": order.take_profit_price,
        "trail_percent": order.trail_percent,
        "time_in_force": order.time_in_force,
        "parent_order_id": order.parent_order_id,
        "order_group_id": order.order_group_id,
        "status": order.status,
        "created_at": order.created_at.isoformat(),
    }


def _session_policy_payload(policy: MarketSessionPolicy) -> dict:
    return {
        "allow_pre_market": policy.allow_pre_market,
        "allow_regular": policy.allow_regular,
        "allow_after_hours": policy.allow_after_hours,
    }


def _submitted_reports_today(reports: tuple[Mapping[str, Any], ...], now: datetime) -> int:
    current_date = now.date()
    count = 0
    for report in reports:
        if not report.get("submitted"):
            continue
        generated_at = _parse_report_datetime(report.get("generated_at"))
        if generated_at and generated_at.date() == current_date:
            count += 1
    return count


def _rejected_reports(reports: tuple[Mapping[str, Any], ...], symbol: str) -> int:
    rejected = 0
    for report in reports:
        plan = dict(report.get("order_plan", {}))
        if plan.get("symbol", "").upper() != symbol.upper():
            continue
        if report.get("reason") == "paper_order_rejected":
            rejected += 1
            continue
        for order in report.get("orders", []):
            if order.get("status") == "REJECTED":
                rejected += 1
                break
    return rejected


def _parse_report_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


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
