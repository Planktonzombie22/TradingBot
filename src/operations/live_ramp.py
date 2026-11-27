import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


LIVE_RAMP_ISSUES = (
    "live_monitor_mismatch",
    "unresolved_order",
    "data_outage",
    "rejected_order",
    "slippage_breach",
    "drawdown_breach",
)


@dataclass(frozen=True)
class LiveMicroPhaseScopeReport:
    strategies: tuple[str, ...]
    symbols: tuple[str, ...]
    max_orders_per_day: int
    max_notional: float

    @property
    def passed(self) -> bool:
        return bool(self.strategies) and len(self.strategies) == 1 and 0 < len(self.symbols) <= 2 and self.max_orders_per_day == 1 and self.max_notional > 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "strategies": list(self.strategies),
            "symbols": list(self.symbols),
            "max_orders_per_day": self.max_orders_per_day,
            "max_notional": self.max_notional,
            "reason": "live_micro_scope_passed" if self.passed else "live_micro_scope_too_broad",
        }


@dataclass(frozen=True)
class LiveMicroOrderEvidenceReport:
    order_id: str
    preview_passed: bool
    monitor_passed: bool
    reconciliation_passed: bool
    daily_report_passed: bool
    parity_passed: bool

    @property
    def passed(self) -> bool:
        return bool(self.order_id) and self.preview_passed and self.monitor_passed and self.reconciliation_passed and self.daily_report_passed and self.parity_passed

    def to_dict(self) -> dict:
        checks = {
            "preview_passed": self.preview_passed,
            "monitor_passed": self.monitor_passed,
            "reconciliation_passed": self.reconciliation_passed,
            "daily_report_passed": self.daily_report_passed,
            "parity_passed": self.parity_passed,
        }
        return {"passed": self.passed, "order_id": self.order_id, "checks": checks, "blockers": [key for key, value in checks.items() if not value]}


@dataclass(frozen=True)
class LiveNotionalRampReport:
    current_notional: float
    requested_notional: float
    clean_live_micro_trades: int
    required_clean_trades: int
    current_paper_evidence: bool
    operator_approved: bool = False

    @property
    def passed(self) -> bool:
        return (
            self.requested_notional >= self.current_notional
            and self.clean_live_micro_trades >= self.required_clean_trades
            and self.current_paper_evidence
            and self.operator_approved
        )

    @property
    def approved_notional(self) -> float:
        return self.requested_notional if self.passed else self.current_notional

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "current_notional": self.current_notional,
            "requested_notional": self.requested_notional,
            "approved_notional": self.approved_notional,
            "clean_live_micro_trades": self.clean_live_micro_trades,
            "required_clean_trades": self.required_clean_trades,
            "current_paper_evidence": self.current_paper_evidence,
            "operator_approved": self.operator_approved,
            "reason": "live_notional_ramp_approved" if self.passed else "live_notional_ramp_blocked",
        }


@dataclass(frozen=True)
class LiveIssueResponseReport:
    current_notional: float
    issues: Mapping[str, bool]
    downshift_notional: float = 0.0

    @property
    def active_issues(self) -> tuple[str, ...]:
        return tuple(issue for issue in LIVE_RAMP_ISSUES if bool(self.issues.get(issue)))

    @property
    def locked(self) -> bool:
        return bool(self.active_issues)

    @property
    def recommended_notional(self) -> float:
        return min(self.current_notional, self.downshift_notional) if self.locked else self.current_notional

    def to_dict(self) -> dict:
        return {
            "passed": not self.locked,
            "locked": self.locked,
            "current_notional": self.current_notional,
            "recommended_notional": self.recommended_notional,
            "issues": dict(self.issues),
            "active_issues": list(self.active_issues),
        }


@dataclass(frozen=True)
class ParallelPaperControlReport:
    live_orders: tuple[Mapping[str, Any], ...]
    paper_orders: tuple[Mapping[str, Any], ...]
    control_active: bool

    @property
    def missing_symbols(self) -> tuple[str, ...]:
        paper_symbols = {str(order.get("symbol", "")).upper() for order in self.paper_orders}
        return tuple(symbol for symbol in sorted({str(order.get("symbol", "")).upper() for order in self.live_orders}) if symbol not in paper_symbols)

    @property
    def passed(self) -> bool:
        return self.control_active and not self.missing_symbols

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "control_active": self.control_active,
            "live_orders": [dict(order) for order in self.live_orders],
            "paper_orders": [dict(order) for order in self.paper_orders],
            "missing_symbols": list(self.missing_symbols),
        }


@dataclass(frozen=True)
class LivePaperFillComparisonReport:
    comparisons: tuple[Mapping[str, Any], ...]
    max_price_diff_bps: float = 5.0

    @property
    def breaches(self) -> tuple[Mapping[str, Any], ...]:
        rows = []
        for row in self.comparisons:
            diff = abs(_float(row.get("live_fill_price")) - _float(row.get("paper_fill_price")))
            baseline = abs(_float(row.get("paper_fill_price"))) or 1.0
            diff_bps = diff / baseline * 10_000
            if diff_bps > self.max_price_diff_bps:
                rows.append({**dict(row), "price_diff_bps": diff_bps})
        return tuple(rows)

    @property
    def passed(self) -> bool:
        return bool(self.comparisons) and not self.breaches

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "comparisons": [dict(row) for row in self.comparisons],
            "max_price_diff_bps": self.max_price_diff_bps,
            "breaches": [dict(row) for row in self.breaches],
        }


@dataclass(frozen=True)
class LiveStrategyQuarantineReport:
    strategy_name: str
    fill_quality_passed: bool
    behavior_parity_passed: bool
    divergence_count: int = 0
    max_divergence_count: int = 0

    @property
    def quarantined(self) -> bool:
        return not self.fill_quality_passed or not self.behavior_parity_passed or self.divergence_count > self.max_divergence_count

    def to_dict(self) -> dict:
        return {
            "passed": not self.quarantined,
            "strategy_name": self.strategy_name,
            "quarantined": self.quarantined,
            "fill_quality_passed": self.fill_quality_passed,
            "behavior_parity_passed": self.behavior_parity_passed,
            "divergence_count": self.divergence_count,
            "max_divergence_count": self.max_divergence_count,
        }


@dataclass(frozen=True)
class LiveCapitalRampApprovalReport:
    approvals: tuple[Mapping[str, Any], ...]
    requested_notional: float

    @property
    def latest_approval(self) -> Mapping[str, Any] | None:
        return self.approvals[-1] if self.approvals else None

    @property
    def passed(self) -> bool:
        latest = self.latest_approval or {}
        return bool(latest.get("approved")) and _float(latest.get("approved_notional")) >= self.requested_notional and bool(latest.get("operator")) and bool(latest.get("timestamp"))

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "requested_notional": self.requested_notional,
            "latest_approval": dict(self.latest_approval or {}),
            "approvals": [dict(row) for row in self.approvals],
        }


@dataclass(frozen=True)
class LiveLossBudgetReport:
    realized_loss: float
    unrealized_loss: float
    max_loss_budget: float
    clean_micro_months: int = 0
    required_clean_months: int = 3

    @property
    def total_loss(self) -> float:
        return max(0.0, self.realized_loss) + max(0.0, self.unrealized_loss)

    @property
    def passed(self) -> bool:
        return self.total_loss <= self.max_loss_budget and self.clean_micro_months >= self.required_clean_months

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "realized_loss": self.realized_loss,
            "unrealized_loss": self.unrealized_loss,
            "total_loss": self.total_loss,
            "max_loss_budget": self.max_loss_budget,
            "clean_micro_months": self.clean_micro_months,
            "required_clean_months": self.required_clean_months,
        }


@dataclass(frozen=True)
class PostMicroCapitalBoundaryReport:
    requested_phase: str
    fresh_review_required: bool = True
    fresh_review_approved: bool = False

    @property
    def passed(self) -> bool:
        return self.requested_phase == "micro" or (self.fresh_review_required and self.fresh_review_approved)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "requested_phase": self.requested_phase,
            "fresh_review_required": self.fresh_review_required,
            "fresh_review_approved": self.fresh_review_approved,
            "reason": "phase_allowed" if self.passed else "post_micro_requires_fresh_review",
        }


def build_live_micro_phase_scope_report(strategies: Sequence[str], symbols: Sequence[str], max_orders_per_day: int, max_notional: float) -> LiveMicroPhaseScopeReport:
    return LiveMicroPhaseScopeReport(tuple(str(item) for item in strategies), tuple(str(symbol).upper() for symbol in symbols), max_orders_per_day, max_notional)


def build_live_micro_order_evidence_report(order_id: str, preview_passed: bool, monitor_passed: bool, reconciliation_passed: bool, daily_report_passed: bool, parity_passed: bool) -> LiveMicroOrderEvidenceReport:
    return LiveMicroOrderEvidenceReport(order_id, preview_passed, monitor_passed, reconciliation_passed, daily_report_passed, parity_passed)


def build_live_notional_ramp_report(current_notional: float, requested_notional: float, clean_live_micro_trades: int, required_clean_trades: int, current_paper_evidence: bool, operator_approved: bool = False) -> LiveNotionalRampReport:
    return LiveNotionalRampReport(current_notional, requested_notional, clean_live_micro_trades, required_clean_trades, current_paper_evidence, operator_approved)


def build_live_issue_response_report(current_notional: float, issues: Mapping[str, bool], downshift_notional: float = 0.0) -> LiveIssueResponseReport:
    return LiveIssueResponseReport(current_notional, dict(issues), downshift_notional)


def build_parallel_paper_control_report(live_orders: Sequence[Mapping[str, Any]], paper_orders: Sequence[Mapping[str, Any]], control_active: bool) -> ParallelPaperControlReport:
    return ParallelPaperControlReport(tuple(dict(order) for order in live_orders), tuple(dict(order) for order in paper_orders), control_active)


def build_live_paper_fill_comparison_report(comparisons: Sequence[Mapping[str, Any]], max_price_diff_bps: float = 5.0) -> LivePaperFillComparisonReport:
    return LivePaperFillComparisonReport(tuple(dict(row) for row in comparisons), max_price_diff_bps)


def build_live_strategy_quarantine_report(strategy_name: str, fill_quality_passed: bool, behavior_parity_passed: bool, divergence_count: int = 0, max_divergence_count: int = 0) -> LiveStrategyQuarantineReport:
    return LiveStrategyQuarantineReport(strategy_name, fill_quality_passed, behavior_parity_passed, divergence_count, max_divergence_count)


def build_live_capital_ramp_approval_report(approvals: Sequence[Mapping[str, Any]], requested_notional: float) -> LiveCapitalRampApprovalReport:
    return LiveCapitalRampApprovalReport(tuple(dict(row) for row in approvals), requested_notional)


def build_live_loss_budget_report(realized_loss: float, unrealized_loss: float, max_loss_budget: float, clean_micro_months: int = 0, required_clean_months: int = 3) -> LiveLossBudgetReport:
    return LiveLossBudgetReport(realized_loss, unrealized_loss, max_loss_budget, clean_micro_months, required_clean_months)


def build_post_micro_capital_boundary_report(requested_phase: str, fresh_review_required: bool = True, fresh_review_approved: bool = False) -> PostMicroCapitalBoundaryReport:
    return PostMicroCapitalBoundaryReport(requested_phase, fresh_review_required, fresh_review_approved)


def write_live_ramp_report(report: Any, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return destination


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
