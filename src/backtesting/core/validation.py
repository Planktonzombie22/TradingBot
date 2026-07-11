from dataclasses import dataclass, field
from typing import Sequence

import pandas as pd

from src.models import BacktestResult


@dataclass(frozen=True)
class BacktestValidationIssue:
    severity: str
    code: str
    message: str


@dataclass
class BacktestValidationReport:
    issues: list[BacktestValidationIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "ERROR" for issue in self.issues)

    def add(self, severity: str, code: str, message: str) -> None:
        self.issues.append(BacktestValidationIssue(severity, code, message))

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": [
                {"severity": issue.severity, "code": issue.code, "message": issue.message}
                for issue in self.issues
            ],
        }


def validate_backtest_result(
    result: BacktestResult,
    *,
    require_flat: bool | None = None,
    tolerance: float = 1e-6,
) -> BacktestValidationReport:
    """Validate structural invariants that every backtest result should satisfy."""

    report = BacktestValidationReport()
    _validate_equity(result, report, tolerance)
    _validate_fills(result.fills, report)
    _validate_final_positions(result, report, require_flat)
    return report


def _validate_equity(result: BacktestResult, report: BacktestValidationReport, tolerance: float) -> None:
    if result.equity.empty:
        report.add("ERROR", "EMPTY_EQUITY", "Backtest result has no equity history.")
        return

    if result.equity.isna().any():
        report.add("ERROR", "NAN_EQUITY", "Backtest equity contains NaN values.")

    if (result.equity <= 0).any():
        report.add("WARNING", "NON_POSITIVE_EQUITY", "Backtest equity reached zero or below.")

    if not result.money_available.empty and len(result.money_available) != len(result.equity):
        report.add("ERROR", "MONEY_AVAILABLE_LENGTH", "Money-available series length does not match equity history.")

    ending_equity = float(result.equity.iloc[-1])
    metric_ending = _metric_float(result.metrics, "ending_equity")
    if metric_ending is not None and abs(metric_ending - ending_equity) > tolerance:
        report.add("ERROR", "ENDING_EQUITY_MISMATCH", "Metrics ending equity does not match result equity.")

    expected_return = float(result.total_pnl_pct)
    metric_return = _metric_float(result.metrics, "total_return")
    if metric_return is not None and abs(metric_return - expected_return) > tolerance:
        report.add("ERROR", "TOTAL_RETURN_MISMATCH", "Metrics total return does not match headline PnL percent.")


def _validate_fills(fills: Sequence[object], report: BacktestValidationReport) -> None:
    for index, fill in enumerate(fills):
        if getattr(fill, "quantity", 0.0) <= 0:
            report.add("ERROR", "INVALID_FILL_QUANTITY", f"Fill {index} has non-positive quantity.")
        if getattr(fill, "price", 0.0) <= 0:
            report.add("ERROR", "INVALID_FILL_PRICE", f"Fill {index} has non-positive price.")
        if getattr(fill, "commission", 0.0) < 0:
            report.add("ERROR", "NEGATIVE_COMMISSION", f"Fill {index} has negative commission.")
        liquidity_fraction = getattr(fill, "liquidity_fraction", 1.0)
        if liquidity_fraction < 0 or liquidity_fraction > 1:
            report.add("ERROR", "INVALID_LIQUIDITY_FRACTION", f"Fill {index} has invalid liquidity fraction.")


def _validate_final_positions(
    result: BacktestResult,
    report: BacktestValidationReport,
    require_flat: bool | None,
) -> None:
    if not result.account_history:
        return

    should_require_flat = require_flat
    if should_require_flat is None:
        should_require_flat = bool(getattr(result.config, "force_flat_at_end", False))
    if not should_require_flat:
        return

    positions = result.account_history[-1].positions
    open_positions = {symbol: quantity for symbol, quantity in positions.items() if abs(quantity) > 1e-9}
    if open_positions:
        report.add("ERROR", "NOT_FLAT_AT_END", f"Backtest ended with open positions: {open_positions}")


def _metric_float(metrics: dict, name: str) -> float | None:
    if name not in metrics:
        return None
    try:
        value = float(metrics[name])
    except (TypeError, ValueError):
        return None
    return value if pd.notna(value) else None
