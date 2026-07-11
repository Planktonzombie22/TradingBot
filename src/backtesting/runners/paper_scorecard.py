from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from src.execution import BrokerAccountSnapshot, ExecutionReport, ReconciliationResult
from src.models import BacktestResult

from ..core.types import Fill


@dataclass(frozen=True)
class PaperTradingScorecardPolicy:
    max_average_slippage_bps: float = 10.0
    max_missed_fill_rate: float = 0.05
    max_reject_rate: float = 0.02
    max_equity_drift_pct: float = 0.02
    require_clean_reconciliation: bool = True


@dataclass(frozen=True)
class PaperTradingExpectation:
    strategy_name: str
    symbol: str
    expected_fills: int
    expected_trades: int
    expected_return: float
    expected_ending_equity: float
    expected_fill_prices: Mapping[str, float] = field(default_factory=dict)

    @classmethod
    def from_backtest(
        cls,
        result: BacktestResult,
        strategy_name: str,
        symbol: str,
    ) -> "PaperTradingExpectation":
        expected_fill_prices = {
            fill.order.id: float(fill.price)
            for fill in result.fills
            if isinstance(fill, Fill) and getattr(fill, "order", None) is not None
        }
        ending_equity = float(result.metrics.get("ending_equity", result.equity.iloc[-1] if len(result.equity) else 0.0))
        return cls(
            strategy_name=strategy_name,
            symbol=symbol,
            expected_fills=len(result.fills),
            expected_trades=len(result.trades),
            expected_return=float(result.total_pnl_pct),
            expected_ending_equity=ending_equity,
            expected_fill_prices=expected_fill_prices,
        )

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "expected_fills": self.expected_fills,
            "expected_trades": self.expected_trades,
            "expected_return": self.expected_return,
            "expected_ending_equity": self.expected_ending_equity,
            "expected_fill_prices": dict(self.expected_fill_prices),
        }


@dataclass(frozen=True)
class PaperTradingObservation:
    reports: Sequence[ExecutionReport] = field(default_factory=tuple)
    account: BrokerAccountSnapshot | None = None
    reconciliation: ReconciliationResult | None = None
    broker_statement: Mapping[str, Any] = field(default_factory=dict)

    @property
    def filled_reports(self) -> list[ExecutionReport]:
        return [report for report in self.reports if report.filled_quantity > 0 or report.status == "FILLED"]

    @property
    def rejected_reports(self) -> list[ExecutionReport]:
        return [report for report in self.reports if report.status == "REJECTED"]

    def to_dict(self) -> dict:
        return {
            "reports": [_report_payload(report) for report in self.reports],
            "account": {
                "cash": self.account.cash,
                "buying_power": self.account.buying_power,
                "equity": self.account.equity,
            }
            if self.account
            else None,
            "reconciliation_clean": self.reconciliation.is_clean if self.reconciliation else None,
            "broker_statement": dict(self.broker_statement),
        }


@dataclass(frozen=True)
class PaperTradingScorecardGate:
    name: str
    passed: bool
    value: float | bool | None
    threshold: float | bool | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperTradingScorecard:
    expectation: PaperTradingExpectation
    observation: PaperTradingObservation
    policy: PaperTradingScorecardPolicy
    average_slippage_bps: float
    missed_fill_rate: float
    reject_rate: float
    equity_drift_pct: float | None
    gates: tuple[PaperTradingScorecardGate, ...]

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def reason(self) -> str:
        if self.passed:
            return "paper_behavior_in_line"
        return next(gate.reason for gate in self.gates if not gate.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "expectation": self.expectation.to_dict(),
            "observation": self.observation.to_dict(),
            "policy": {
                "max_average_slippage_bps": self.policy.max_average_slippage_bps,
                "max_missed_fill_rate": self.policy.max_missed_fill_rate,
                "max_reject_rate": self.policy.max_reject_rate,
                "max_equity_drift_pct": self.policy.max_equity_drift_pct,
                "require_clean_reconciliation": self.policy.require_clean_reconciliation,
            },
            "average_slippage_bps": self.average_slippage_bps,
            "missed_fill_rate": self.missed_fill_rate,
            "reject_rate": self.reject_rate,
            "equity_drift_pct": self.equity_drift_pct,
            "gates": [gate.to_dict() for gate in self.gates],
        }


def build_paper_trading_scorecard(
    expectation: PaperTradingExpectation,
    observation: PaperTradingObservation,
    policy: PaperTradingScorecardPolicy | None = None,
) -> PaperTradingScorecard:
    policy = policy or PaperTradingScorecardPolicy()
    average_slippage_bps = _average_slippage_bps(expectation.expected_fill_prices, observation.filled_reports)
    missed_fill_rate = _missed_fill_rate(expectation.expected_fills, len(observation.filled_reports))
    reject_rate = _rate(len(observation.rejected_reports), len(observation.reports))
    equity_drift_pct = _equity_drift_pct(expectation.expected_ending_equity, observation.account)
    gates = (
        _numeric_gate("average_slippage_bps", average_slippage_bps, policy.max_average_slippage_bps, "slippage_too_high"),
        _numeric_gate("missed_fill_rate", missed_fill_rate, policy.max_missed_fill_rate, "missed_fill_rate_too_high"),
        _numeric_gate("reject_rate", reject_rate, policy.max_reject_rate, "reject_rate_too_high"),
        _optional_numeric_gate("equity_drift_pct", equity_drift_pct, policy.max_equity_drift_pct, "equity_drift_too_high"),
        _reconciliation_gate(observation.reconciliation, policy.require_clean_reconciliation),
    )
    return PaperTradingScorecard(
        expectation=expectation,
        observation=observation,
        policy=policy,
        average_slippage_bps=average_slippage_bps,
        missed_fill_rate=missed_fill_rate,
        reject_rate=reject_rate,
        equity_drift_pct=equity_drift_pct,
        gates=gates,
    )


def paper_scorecard_from_backtest(
    result: BacktestResult,
    strategy_name: str,
    symbol: str,
    reports: Iterable[ExecutionReport],
    account: BrokerAccountSnapshot | None = None,
    reconciliation: ReconciliationResult | None = None,
    broker_statement: Mapping[str, Any] | None = None,
    policy: PaperTradingScorecardPolicy | None = None,
) -> PaperTradingScorecard:
    return build_paper_trading_scorecard(
        PaperTradingExpectation.from_backtest(result, strategy_name, symbol),
        PaperTradingObservation(
            reports=tuple(reports),
            account=account,
            reconciliation=reconciliation,
            broker_statement=dict(broker_statement or {}),
        ),
        policy,
    )


def _average_slippage_bps(expected_prices: Mapping[str, float], reports: Sequence[ExecutionReport]) -> float:
    slippages = []
    for report in reports:
        expected_price = expected_prices.get(report.order_id)
        if expected_price is None or expected_price <= 0 or report.average_fill_price is None:
            continue
        slippages.append(abs(float(report.average_fill_price) - expected_price) / expected_price * 10_000)
    return sum(slippages) / len(slippages) if slippages else 0.0


def _missed_fill_rate(expected_fills: int, actual_fills: int) -> float:
    if expected_fills <= 0:
        return 0.0
    return max(expected_fills - actual_fills, 0) / expected_fills


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _equity_drift_pct(expected_ending_equity: float, account: BrokerAccountSnapshot | None) -> float | None:
    if account is None or expected_ending_equity <= 0:
        return None
    return abs(float(account.equity) - expected_ending_equity) / expected_ending_equity


def _numeric_gate(name: str, value: float, threshold: float, reason: str) -> PaperTradingScorecardGate:
    return PaperTradingScorecardGate(name, value <= threshold, value, threshold, "passed" if value <= threshold else reason)


def _optional_numeric_gate(
    name: str,
    value: float | None,
    threshold: float,
    reason: str,
) -> PaperTradingScorecardGate:
    if value is None:
        return PaperTradingScorecardGate(name, True, None, threshold, "not_available")
    return _numeric_gate(name, value, threshold, reason)


def _reconciliation_gate(
    reconciliation: ReconciliationResult | None,
    required: bool,
) -> PaperTradingScorecardGate:
    if not required:
        return PaperTradingScorecardGate("reconciliation", True, None, False, "not_required")
    if reconciliation is None:
        return PaperTradingScorecardGate("reconciliation", False, None, True, "missing_reconciliation")
    return PaperTradingScorecardGate(
        "reconciliation",
        reconciliation.is_clean,
        reconciliation.is_clean,
        True,
        "passed" if reconciliation.is_clean else "unresolved_reconciliation_items",
    )


def _report_payload(report: ExecutionReport) -> dict:
    return {
        "order_id": report.order_id,
        "status": report.status,
        "broker_order_id": report.broker_order_id,
        "filled_quantity": report.filled_quantity,
        "average_fill_price": report.average_fill_price,
    }
