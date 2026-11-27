import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from src.models import BacktestResult

from ..execution.calibration import FillObservation, TransactionCostCalibration
from .paper_scorecard import PaperTradingExpectation


@dataclass(frozen=True)
class PaperBacktestReplayEvent:
    order_id: str
    symbol: str
    paper_timestamp: str | None
    backtest_price: float | None
    paper_price: float | None
    price_drift_bps: float | None
    expected_quantity: float | None
    paper_quantity: float | None
    quantity_drift: float | None
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "paper_timestamp": self.paper_timestamp,
            "backtest_price": self.backtest_price,
            "paper_price": self.paper_price,
            "price_drift_bps": self.price_drift_bps,
            "expected_quantity": self.expected_quantity,
            "paper_quantity": self.paper_quantity,
            "quantity_drift": self.quantity_drift,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperBacktestReplayReport:
    events: tuple[PaperBacktestReplayEvent, ...]
    expected_fills: int
    observed_fills: int
    max_price_drift_bps: float = 25.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.expected_fills == self.observed_fills and all(event.passed for event in self.events)

    @property
    def reason(self) -> str:
        if self.expected_fills != self.observed_fills:
            return "paper_backtest_fill_count_mismatch"
        if self.passed:
            return "paper_backtest_replay_passed"
        return next(event.reason for event in self.events if not event.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "expected_fills": self.expected_fills,
            "observed_fills": self.observed_fills,
            "max_price_drift_bps": self.max_price_drift_bps,
            "events": [event.to_dict() for event in self.events],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class BacktestPaperExpectationReport:
    expectation: PaperTradingExpectation
    generated_at: str
    strategy_name: str
    symbol: str
    assumptions: Mapping[str, Any] = field(default_factory=dict)
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.expectation.expected_fills >= 0 and self.expectation.expected_trades >= 0

    @property
    def reason(self) -> str:
        return "backtest_paper_expectation_generated" if self.passed else "invalid_backtest_paper_expectation"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "generated_at": self.generated_at,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "assumptions": dict(self.assumptions),
            "expectation": self.expectation.to_dict(),
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class FillModelCalibrationReport:
    calibration: TransactionCostCalibration
    model_version: str
    min_observations: int = 5
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.calibration.observations >= self.min_observations

    @property
    def reason(self) -> str:
        return "fill_model_calibration_passed" if self.passed else "fill_model_observations_too_few"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "model_version": self.model_version,
            "min_observations": self.min_observations,
            "calibration": {
                "spread_bps": self.calibration.spread_bps,
                "impact_bps_per_volume_share": self.calibration.impact_bps_per_volume_share,
                "observations": self.calibration.observations,
            },
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class SlippageModelVersion:
    name: str
    version: str
    parameters: Mapping[str, Any]
    calibrated_from: str | None = None
    notes: str = ""

    @property
    def passed(self) -> bool:
        return bool(self.name and self.version and self.parameters)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "parameters": dict(self.parameters),
            "calibrated_from": self.calibrated_from,
            "notes": self.notes,
            "passed": self.passed,
            "reason": "slippage_model_version_recorded" if self.passed else "slippage_model_version_incomplete",
        }


@dataclass(frozen=True)
class SlippageModelVersionReport:
    models: tuple[SlippageModelVersion, ...]
    active_version: str | None = None
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(model.passed for model in self.models) and (self.active_version is None or self.active_version in {model.version for model in self.models})

    @property
    def reason(self) -> str:
        if self.active_version is not None and self.active_version not in {model.version for model in self.models}:
            return "active_slippage_version_missing"
        if self.passed:
            return "slippage_model_versions_valid"
        return "slippage_model_version_incomplete"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "active_version": self.active_version,
            "models": [model.to_dict() for model in self.models],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class LatencyAwareBacktestEvent:
    order_id: str
    decision_timestamp: str | None
    simulated_submission_timestamp: str | None
    simulated_fill_timestamp: str | None
    decision_delay_ms: float
    broker_submission_delay_ms: float
    fill_delay_ms: float
    total_latency_ms: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "decision_timestamp": self.decision_timestamp,
            "simulated_submission_timestamp": self.simulated_submission_timestamp,
            "simulated_fill_timestamp": self.simulated_fill_timestamp,
            "decision_delay_ms": self.decision_delay_ms,
            "broker_submission_delay_ms": self.broker_submission_delay_ms,
            "fill_delay_ms": self.fill_delay_ms,
            "total_latency_ms": self.total_latency_ms,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LatencyAwareBacktestReport:
    events: tuple[LatencyAwareBacktestEvent, ...]
    max_total_latency_ms: float = 1_000.0
    artifact_path: str | None = None

    @property
    def p95_total_latency_ms(self) -> float:
        values = sorted(event.total_latency_ms for event in self.events)
        if not values:
            return 0.0
        index = min(int(len(values) * 0.95), len(values) - 1)
        return values[index]

    @property
    def average_total_latency_ms(self) -> float:
        return mean(event.total_latency_ms for event in self.events) if self.events else 0.0

    @property
    def passed(self) -> bool:
        return all(event.passed for event in self.events)

    @property
    def reason(self) -> str:
        if self.passed:
            return "latency_aware_backtest_passed"
        return next(event.reason for event in self.events if not event.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_total_latency_ms": self.max_total_latency_ms,
            "average_total_latency_ms": self.average_total_latency_ms,
            "p95_total_latency_ms": self.p95_total_latency_ms,
            "events": [event.to_dict() for event in self.events],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class IntrabarExecutionCheck:
    order_id: str
    symbol: str
    order_type: str
    simulated_triggered: bool
    paper_triggered: bool
    simulated_price: float | None
    paper_price: float | None
    price_drift_bps: float | None
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "order_type": self.order_type,
            "simulated_triggered": self.simulated_triggered,
            "paper_triggered": self.paper_triggered,
            "simulated_price": self.simulated_price,
            "paper_price": self.paper_price,
            "price_drift_bps": self.price_drift_bps,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class IntrabarExecutionAssumptionReport:
    checks: tuple[IntrabarExecutionCheck, ...]
    max_price_drift_bps: float = 25.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "intrabar_execution_assumptions_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_price_drift_bps": self.max_price_drift_bps,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ShortBorrowFeeCheck:
    symbol: str
    short_notional: float
    locate_available: bool
    borrow_rate: float
    holding_days: float
    estimated_fee: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "short_notional": self.short_notional,
            "locate_available": self.locate_available,
            "borrow_rate": self.borrow_rate,
            "holding_days": self.holding_days,
            "estimated_fee": self.estimated_fee,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ShortBorrowFeeReport:
    checks: tuple[ShortBorrowFeeCheck, ...]
    max_borrow_rate: float = 0.15
    max_total_fee: float = 100.0
    artifact_path: str | None = None

    @property
    def total_estimated_fee(self) -> float:
        return sum(check.estimated_fee for check in self.checks)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks) and self.total_estimated_fee <= self.max_total_fee

    @property
    def reason(self) -> str:
        if self.total_estimated_fee > self.max_total_fee:
            return "short_borrow_total_fee_too_high"
        if self.passed:
            return "short_borrow_fee_checks_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_borrow_rate": self.max_borrow_rate,
            "max_total_fee": self.max_total_fee,
            "total_estimated_fee": self.total_estimated_fee,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class MarginLeverageCostCheck:
    symbol: str
    borrowed_notional: float
    margin_rate: float
    holding_days: float
    leverage: float
    estimated_interest: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "borrowed_notional": self.borrowed_notional,
            "margin_rate": self.margin_rate,
            "holding_days": self.holding_days,
            "leverage": self.leverage,
            "estimated_interest": self.estimated_interest,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MarginLeverageCostReport:
    checks: tuple[MarginLeverageCostCheck, ...]
    max_leverage: float = 1.0
    max_total_interest: float = 100.0
    artifact_path: str | None = None

    @property
    def total_estimated_interest(self) -> float:
        return sum(check.estimated_interest for check in self.checks)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks) and self.total_estimated_interest <= self.max_total_interest

    @property
    def reason(self) -> str:
        if self.total_estimated_interest > self.max_total_interest:
            return "margin_total_interest_too_high"
        if self.passed:
            return "margin_leverage_costs_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_leverage": self.max_leverage,
            "max_total_interest": self.max_total_interest,
            "total_estimated_interest": self.total_estimated_interest,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class CorporateActionCashflowCheck:
    symbol: str
    action_type: str
    quantity_before: float
    quantity_after: float | None
    cashflow: float
    expected_quantity_after: float | None
    expected_cashflow: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action_type": self.action_type,
            "quantity_before": self.quantity_before,
            "quantity_after": self.quantity_after,
            "cashflow": self.cashflow,
            "expected_quantity_after": self.expected_quantity_after,
            "expected_cashflow": self.expected_cashflow,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CorporateActionCashflowReport:
    checks: tuple[CorporateActionCashflowCheck, ...]
    tolerance: float = 1e-6
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "corporate_action_cashflows_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "tolerance": self.tolerance,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PortfolioRebalanceParityCheck:
    symbol: str
    backtest_target_notional: float
    paper_target_notional: float
    notional_drift: float
    tolerance_notional: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "backtest_target_notional": self.backtest_target_notional,
            "paper_target_notional": self.paper_target_notional,
            "notional_drift": self.notional_drift,
            "tolerance_notional": self.tolerance_notional,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PortfolioRebalanceParityReport:
    checks: tuple[PortfolioRebalanceParityCheck, ...]
    default_tolerance_notional: float = 1.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "portfolio_rebalance_parity_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "default_tolerance_notional": self.default_tolerance_notional,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ReferenceBacktestComparison:
    scenario: str
    metric: str
    local_value: float
    reference_value: float
    drift: float
    tolerance: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "metric": self.metric,
            "local_value": self.local_value,
            "reference_value": self.reference_value,
            "drift": self.drift,
            "tolerance": self.tolerance,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReferenceBacktestComparisonReport:
    comparisons: tuple[ReferenceBacktestComparison, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(comparison.passed for comparison in self.comparisons)

    @property
    def reason(self) -> str:
        if self.passed:
            return "reference_backtest_comparisons_passed"
        return next(comparison.reason for comparison in self.comparisons if not comparison.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "comparisons": [comparison.to_dict() for comparison in self.comparisons],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PaperSessionRegressionFixture:
    fixture_id: str
    artifact_paths: tuple[str, ...]
    replay_passed: bool
    scorecard_passed: bool
    monitor_passed: bool
    broker_reconciliation_passed: bool
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "artifact_paths": list(self.artifact_paths),
            "replay_passed": self.replay_passed,
            "scorecard_passed": self.scorecard_passed,
            "monitor_passed": self.monitor_passed,
            "broker_reconciliation_passed": self.broker_reconciliation_passed,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperSessionRegressionFixtureReport:
    fixtures: tuple[PaperSessionRegressionFixture, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(fixture.passed for fixture in self.fixtures)

    @property
    def reason(self) -> str:
        if self.passed:
            return "paper_session_regression_fixtures_passed"
        return next(fixture.reason for fixture in self.fixtures if not fixture.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "fixtures": [fixture.to_dict() for fixture in self.fixtures],
            "artifact_path": self.artifact_path,
        }


def build_paper_backtest_replay_report(
    backtest_result: BacktestResult,
    paper_events: Sequence[Mapping[str, Any]],
    max_price_drift_bps: float = 25.0,
) -> PaperBacktestReplayReport:
    expected = _expected_fills_by_order_id(backtest_result)
    events = tuple(_paper_backtest_event(row, expected.get(str(row.get("order_id") or "")), max_price_drift_bps) for row in paper_events)
    return PaperBacktestReplayReport(events, expected_fills=len(expected), observed_fills=len(paper_events), max_price_drift_bps=max_price_drift_bps)


def build_backtest_paper_expectation_report(
    backtest_result: BacktestResult,
    strategy_name: str,
    symbol: str,
    assumptions: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> BacktestPaperExpectationReport:
    generated = now or datetime.now(timezone.utc)
    return BacktestPaperExpectationReport(
        expectation=PaperTradingExpectation.from_backtest(backtest_result, strategy_name, symbol),
        generated_at=generated.isoformat(),
        strategy_name=strategy_name,
        symbol=symbol,
        assumptions=dict(assumptions or {}),
    )


def build_fill_model_calibration_report(
    rows: Sequence[Mapping[str, Any]],
    model_version: str = "paper-fill-calibration-v1",
    min_observations: int = 5,
) -> FillModelCalibrationReport:
    observations = tuple(_fill_observation(row) for row in rows)
    return FillModelCalibrationReport(
        TransactionCostCalibration.from_observations(observations),
        model_version=model_version,
        min_observations=min_observations,
    )


def build_slippage_model_version_report(
    rows: Sequence[Mapping[str, Any]],
    active_version: str | None = None,
) -> SlippageModelVersionReport:
    return SlippageModelVersionReport(tuple(_slippage_model_version(row) for row in rows), active_version=active_version)


def build_latency_aware_backtest_report(
    rows: Sequence[Mapping[str, Any]],
    max_total_latency_ms: float = 1_000.0,
) -> LatencyAwareBacktestReport:
    return LatencyAwareBacktestReport(tuple(_latency_event(row, max_total_latency_ms) for row in rows), max_total_latency_ms=max_total_latency_ms)


def build_intrabar_execution_assumption_report(
    rows: Sequence[Mapping[str, Any]],
    max_price_drift_bps: float = 25.0,
) -> IntrabarExecutionAssumptionReport:
    return IntrabarExecutionAssumptionReport(
        tuple(_intrabar_execution_check(row, max_price_drift_bps) for row in rows),
        max_price_drift_bps=max_price_drift_bps,
    )


def build_short_borrow_fee_report(
    rows: Sequence[Mapping[str, Any]],
    max_borrow_rate: float = 0.15,
    max_total_fee: float = 100.0,
) -> ShortBorrowFeeReport:
    return ShortBorrowFeeReport(tuple(_short_borrow_fee_check(row, max_borrow_rate) for row in rows), max_borrow_rate=max_borrow_rate, max_total_fee=max_total_fee)


def build_margin_leverage_cost_report(
    rows: Sequence[Mapping[str, Any]],
    max_leverage: float = 1.0,
    max_total_interest: float = 100.0,
) -> MarginLeverageCostReport:
    return MarginLeverageCostReport(
        tuple(_margin_leverage_cost_check(row, max_leverage) for row in rows),
        max_leverage=max_leverage,
        max_total_interest=max_total_interest,
    )


def build_corporate_action_cashflow_report(
    rows: Sequence[Mapping[str, Any]],
    tolerance: float = 1e-6,
) -> CorporateActionCashflowReport:
    return CorporateActionCashflowReport(tuple(_corporate_action_cashflow_check(row, tolerance) for row in rows), tolerance=tolerance)


def build_portfolio_rebalance_parity_report(
    rows: Sequence[Mapping[str, Any]],
    default_tolerance_notional: float = 1.0,
) -> PortfolioRebalanceParityReport:
    return PortfolioRebalanceParityReport(
        tuple(_portfolio_rebalance_parity_check(row, default_tolerance_notional) for row in rows),
        default_tolerance_notional=default_tolerance_notional,
    )


def build_reference_backtest_comparison_report(rows: Sequence[Mapping[str, Any]]) -> ReferenceBacktestComparisonReport:
    return ReferenceBacktestComparisonReport(tuple(_reference_backtest_comparison(row) for row in rows))


def build_paper_session_regression_fixture_report(rows: Sequence[Mapping[str, Any]]) -> PaperSessionRegressionFixtureReport:
    return PaperSessionRegressionFixtureReport(tuple(_paper_session_regression_fixture(row) for row in rows))


def write_paper_backtest_replay_report(report: PaperBacktestReplayReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_backtest_paper_expectation_report(report: BacktestPaperExpectationReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_fill_model_calibration_report(report: FillModelCalibrationReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_slippage_model_version_report(report: SlippageModelVersionReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_latency_aware_backtest_report(report: LatencyAwareBacktestReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_intrabar_execution_assumption_report(report: IntrabarExecutionAssumptionReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_short_borrow_fee_report(report: ShortBorrowFeeReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_margin_leverage_cost_report(report: MarginLeverageCostReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_corporate_action_cashflow_report(report: CorporateActionCashflowReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_portfolio_rebalance_parity_report(report: PortfolioRebalanceParityReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_reference_backtest_comparison_report(report: ReferenceBacktestComparisonReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_paper_session_regression_fixture_report(report: PaperSessionRegressionFixtureReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def _expected_fills_by_order_id(backtest_result: BacktestResult) -> dict[str, Mapping[str, Any]]:
    expected = {}
    for index, fill in enumerate(backtest_result.fills):
        order = getattr(fill, "order", None)
        order_id = str(getattr(order, "id", "") or f"fill-{index}")
        expected[order_id] = {
            "symbol": str(getattr(order, "symbol", "")),
            "price": _optional_float(getattr(fill, "price", None)),
            "quantity": _optional_float(getattr(fill, "quantity", None)),
        }
    return expected


def _paper_backtest_event(row: Mapping[str, Any], expected: Mapping[str, Any] | None, max_price_drift_bps: float) -> PaperBacktestReplayEvent:
    order_id = str(row.get("order_id") or "")
    paper_price = _optional_float(row.get("paper_price") or row.get("fill_price"))
    paper_quantity = _optional_float(row.get("paper_quantity") or row.get("quantity"))
    if expected is None:
        price_drift = None
        quantity_drift = None
        reason = "paper_fill_missing_backtest_match"
    else:
        backtest_price = expected.get("price")
        expected_quantity = expected.get("quantity")
        price_drift = _price_drift_bps(backtest_price, paper_price)
        quantity_drift = None if expected_quantity is None or paper_quantity is None else abs(paper_quantity - expected_quantity)
        if price_drift is not None and price_drift > max_price_drift_bps:
            reason = "paper_backtest_price_drift_too_high"
        elif quantity_drift is not None and quantity_drift > 1e-9:
            reason = "paper_backtest_quantity_drift"
        else:
            reason = "paper_backtest_event_matched"
    return PaperBacktestReplayEvent(
        order_id=order_id,
        symbol=str(row.get("symbol") or (expected or {}).get("symbol") or "").upper(),
        paper_timestamp=_date_text(row.get("paper_timestamp") or row.get("timestamp")),
        backtest_price=(expected or {}).get("price"),
        paper_price=paper_price,
        price_drift_bps=price_drift,
        expected_quantity=(expected or {}).get("quantity"),
        paper_quantity=paper_quantity,
        quantity_drift=quantity_drift,
        passed=reason == "paper_backtest_event_matched",
        reason=reason,
    )


def _fill_observation(row: Mapping[str, Any]) -> FillObservation:
    return FillObservation(
        symbol=str(row.get("symbol") or "").upper(),
        side=str(row.get("side") or "BUY").upper(),
        expected_price=_optional_float(row.get("expected_price")) or 0.0,
        fill_price=_optional_float(row.get("fill_price")) or 0.0,
        quantity=_optional_float(row.get("quantity")) or 0.0,
        quoted_bid=_optional_float(row.get("quoted_bid")),
        quoted_ask=_optional_float(row.get("quoted_ask")),
        bar_volume=_optional_float(row.get("bar_volume")),
    )


def _slippage_model_version(row: Mapping[str, Any]) -> SlippageModelVersion:
    params = row.get("parameters") if isinstance(row.get("parameters"), Mapping) else {}
    return SlippageModelVersion(
        name=str(row.get("name") or "slippage_model"),
        version=str(row.get("version") or ""),
        parameters=params,
        calibrated_from=str(row.get("calibrated_from")) if row.get("calibrated_from") else None,
        notes=str(row.get("notes") or ""),
    )


def _latency_event(row: Mapping[str, Any], max_total_latency_ms: float) -> LatencyAwareBacktestEvent:
    decision_at = _parse_datetime(row.get("decision_timestamp") or row.get("timestamp"))
    decision_delay = _optional_float(row.get("decision_delay_ms")) or 0.0
    submission_delay = _optional_float(row.get("broker_submission_delay_ms") or row.get("submission_delay_ms")) or 0.0
    fill_delay = _optional_float(row.get("fill_delay_ms")) or 0.0
    total = decision_delay + submission_delay + fill_delay
    submitted_at = decision_at + timedelta(milliseconds=decision_delay + submission_delay) if decision_at else None
    filled_at = submitted_at + timedelta(milliseconds=fill_delay) if submitted_at else None
    reason = "latency_aware_event_passed" if total <= max_total_latency_ms else "latency_total_above_threshold"
    return LatencyAwareBacktestEvent(
        order_id=str(row.get("order_id") or "unknown"),
        decision_timestamp=decision_at.isoformat() if decision_at else None,
        simulated_submission_timestamp=submitted_at.isoformat() if submitted_at else None,
        simulated_fill_timestamp=filled_at.isoformat() if filled_at else None,
        decision_delay_ms=decision_delay,
        broker_submission_delay_ms=submission_delay,
        fill_delay_ms=fill_delay,
        total_latency_ms=total,
        passed=reason == "latency_aware_event_passed",
        reason=reason,
    )


def _intrabar_execution_check(row: Mapping[str, Any], max_price_drift_bps: float) -> IntrabarExecutionCheck:
    order_type = str(row.get("order_type") or "MARKET").upper()
    simulated_triggered, simulated_price = _simulate_intrabar_trigger(row, order_type)
    paper_triggered = bool(row.get("paper_triggered", row.get("observed_triggered", False)))
    paper_price = _optional_float(row.get("paper_price") or row.get("fill_price"))
    drift = _price_drift_bps(simulated_price, paper_price)
    if simulated_triggered != paper_triggered:
        reason = "intrabar_trigger_mismatch"
    elif drift is not None and drift > max_price_drift_bps:
        reason = "intrabar_execution_price_drift_too_high"
    else:
        reason = "intrabar_execution_assumption_matched"
    return IntrabarExecutionCheck(
        order_id=str(row.get("order_id") or "unknown"),
        symbol=str(row.get("symbol") or "").upper(),
        order_type=order_type,
        simulated_triggered=simulated_triggered,
        paper_triggered=paper_triggered,
        simulated_price=simulated_price,
        paper_price=paper_price,
        price_drift_bps=drift,
        passed=reason == "intrabar_execution_assumption_matched",
        reason=reason,
    )


def _simulate_intrabar_trigger(row: Mapping[str, Any], order_type: str) -> tuple[bool, float | None]:
    side = str(row.get("side") or "BUY").upper()
    high = _optional_float(row.get("high"))
    low = _optional_float(row.get("low"))
    stop = _optional_float(row.get("stop_price") or row.get("stop_loss"))
    limit = _optional_float(row.get("limit_price") or row.get("take_profit_price"))
    if order_type in {"STOP", "STOP_LIMIT"} and stop is not None:
        triggered = (high is not None and high >= stop) if side == "BUY" else (low is not None and low <= stop)
        return triggered, stop if triggered else None
    if order_type == "LIMIT" and limit is not None:
        triggered = (low is not None and low <= limit) if side == "BUY" else (high is not None and high >= limit)
        return triggered, limit if triggered else None
    if order_type == "BRACKET":
        stop_triggered = low is not None and stop is not None and low <= stop
        target_triggered = high is not None and limit is not None and high >= limit
        if stop_triggered:
            return True, stop
        if target_triggered:
            return True, limit
        return False, None
    close = _optional_float(row.get("close"))
    return True, close


def _short_borrow_fee_check(row: Mapping[str, Any], max_borrow_rate: float) -> ShortBorrowFeeCheck:
    notional = abs(_optional_float(row.get("short_notional") or row.get("notional")) or 0.0)
    rate = _optional_float(row.get("borrow_rate") or row.get("annual_borrow_rate")) or 0.0
    days = _optional_float(row.get("holding_days")) or 0.0
    locate_available = bool(row.get("locate_available", row.get("easy_to_borrow", False)))
    fee = notional * rate * days / 365.0
    if not locate_available:
        reason = "short_locate_unavailable"
    elif rate > max_borrow_rate:
        reason = "short_borrow_rate_too_high"
    else:
        reason = "short_borrow_fee_check_passed"
    return ShortBorrowFeeCheck(
        symbol=str(row.get("symbol") or "").upper(),
        short_notional=notional,
        locate_available=locate_available,
        borrow_rate=rate,
        holding_days=days,
        estimated_fee=fee,
        passed=reason == "short_borrow_fee_check_passed",
        reason=reason,
    )


def _margin_leverage_cost_check(row: Mapping[str, Any], max_leverage: float) -> MarginLeverageCostCheck:
    borrowed = abs(_optional_float(row.get("borrowed_notional") or row.get("margin_notional")) or 0.0)
    rate = _optional_float(row.get("margin_rate") or row.get("annual_margin_rate")) or 0.0
    days = _optional_float(row.get("holding_days")) or 0.0
    leverage = _optional_float(row.get("leverage")) or 1.0
    interest = borrowed * rate * days / 365.0
    if leverage > max_leverage:
        reason = "margin_leverage_too_high"
    else:
        reason = "margin_leverage_cost_check_passed"
    return MarginLeverageCostCheck(
        symbol=str(row.get("symbol") or "").upper(),
        borrowed_notional=borrowed,
        margin_rate=rate,
        holding_days=days,
        leverage=leverage,
        estimated_interest=interest,
        passed=reason == "margin_leverage_cost_check_passed",
        reason=reason,
    )


def _corporate_action_cashflow_check(row: Mapping[str, Any], tolerance: float) -> CorporateActionCashflowCheck:
    action = str(row.get("action_type") or row.get("type") or "dividend").lower()
    quantity_before = _optional_float(row.get("quantity_before") or row.get("quantity")) or 0.0
    quantity_after = _optional_float(row.get("quantity_after"))
    split_ratio = _optional_float(row.get("split_ratio")) or 1.0
    dividend = _optional_float(row.get("dividend_per_share")) or 0.0
    cashflow = _optional_float(row.get("cashflow") or row.get("observed_cashflow")) or 0.0
    expected_quantity = quantity_before * split_ratio if action == "split" else quantity_before
    expected_cashflow = quantity_before * dividend if action == "dividend" else 0.0
    if quantity_after is not None and abs(quantity_after - expected_quantity) > tolerance:
        reason = "corporate_action_quantity_mismatch"
    elif abs(cashflow - expected_cashflow) > tolerance:
        reason = "corporate_action_cashflow_mismatch"
    else:
        reason = "corporate_action_cashflow_passed"
    return CorporateActionCashflowCheck(
        symbol=str(row.get("symbol") or "").upper(),
        action_type=action,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        cashflow=cashflow,
        expected_quantity_after=expected_quantity,
        expected_cashflow=expected_cashflow,
        passed=reason == "corporate_action_cashflow_passed",
        reason=reason,
    )


def _portfolio_rebalance_parity_check(row: Mapping[str, Any], default_tolerance_notional: float) -> PortfolioRebalanceParityCheck:
    backtest_target = _optional_float(row.get("backtest_target_notional")) or 0.0
    paper_target = _optional_float(row.get("paper_target_notional")) or 0.0
    tolerance = _optional_float(row.get("tolerance_notional")) or default_tolerance_notional
    drift = abs(backtest_target - paper_target)
    passed = drift <= tolerance
    return PortfolioRebalanceParityCheck(
        symbol=str(row.get("symbol") or "").upper(),
        backtest_target_notional=backtest_target,
        paper_target_notional=paper_target,
        notional_drift=drift,
        tolerance_notional=tolerance,
        passed=passed,
        reason="portfolio_rebalance_parity_matched" if passed else "portfolio_rebalance_target_mismatch",
    )


def _reference_backtest_comparison(row: Mapping[str, Any]) -> ReferenceBacktestComparison:
    local = _optional_float(row.get("local_value")) or 0.0
    reference = _optional_float(row.get("reference_value")) or 0.0
    tolerance = _optional_float(row.get("tolerance")) or 0.0
    drift = abs(local - reference)
    passed = drift <= tolerance
    return ReferenceBacktestComparison(
        scenario=str(row.get("scenario") or "unknown"),
        metric=str(row.get("metric") or "metric"),
        local_value=local,
        reference_value=reference,
        drift=drift,
        tolerance=tolerance,
        passed=passed,
        reason="reference_backtest_comparison_matched" if passed else "reference_backtest_comparison_drift",
    )


def _paper_session_regression_fixture(row: Mapping[str, Any]) -> PaperSessionRegressionFixture:
    paths = tuple(str(path) for path in row.get("artifact_paths", ()) or ())
    replay = bool(row.get("replay_passed", False))
    scorecard = bool(row.get("scorecard_passed", False))
    monitor = bool(row.get("monitor_passed", False))
    reconciliation = bool(row.get("broker_reconciliation_passed", False))
    if not paths:
        reason = "paper_fixture_missing_artifacts"
    elif not replay:
        reason = "paper_fixture_replay_failed"
    elif not scorecard:
        reason = "paper_fixture_scorecard_failed"
    elif not monitor:
        reason = "paper_fixture_monitor_failed"
    elif not reconciliation:
        reason = "paper_fixture_reconciliation_failed"
    else:
        reason = "paper_session_regression_fixture_passed"
    return PaperSessionRegressionFixture(
        fixture_id=str(row.get("fixture_id") or "unknown"),
        artifact_paths=paths,
        replay_passed=replay,
        scorecard_passed=scorecard,
        monitor_passed=monitor,
        broker_reconciliation_passed=reconciliation,
        passed=reason == "paper_session_regression_fixture_passed",
        reason=reason,
    )


def _price_drift_bps(expected: float | None, observed: float | None) -> float | None:
    if expected is None or observed is None or expected <= 0:
        return None
    return abs(observed - expected) / expected * 10_000


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _date_text(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    return parsed.isoformat() if parsed else None


def _write_report(payload: dict, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)
