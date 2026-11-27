import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


PAPER_NOTIONAL_TIERS = (25.0, 50.0, 100.0, 250.0, 500.0, 1000.0)
REQUIRED_LIVE_FIRE_DRILLS = ("flatten_all", "cancel_all", "stale_open_order", "broker_outage", "data_outage", "process_crash")
REQUIRED_REGIMES = ("trend", "chop", "high_volatility", "low_volatility", "event_driven")
MONTH_END_REVIEW_SECTIONS = ("drawdown", "exposure", "slippage", "rejects", "missed_fills", "operator_actions")


@dataclass(frozen=True)
class PaperNotionalTierDecision:
    target_notional: float
    passed: bool
    reason: str
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict:
        return {
            "target_notional": self.target_notional,
            "passed": self.passed,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperNotionalEscalationReport:
    current_notional: float
    decisions: tuple[PaperNotionalTierDecision, ...]

    @property
    def approved_notional(self) -> float:
        approved = [decision.target_notional for decision in self.decisions if decision.passed]
        return max([self.current_notional, *approved])

    @property
    def next_blocked_tier(self) -> PaperNotionalTierDecision | None:
        for decision in self.decisions:
            if decision.target_notional > self.approved_notional and not decision.passed:
                return decision
        return None

    @property
    def passed(self) -> bool:
        return self.approved_notional >= self.current_notional

    def to_dict(self) -> dict:
        blocked = self.next_blocked_tier
        return {
            "passed": self.passed,
            "current_notional": self.current_notional,
            "approved_notional": self.approved_notional,
            "next_blocked_tier": blocked.to_dict() if blocked else None,
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


@dataclass(frozen=True)
class PaperNotionalDownshiftDecision:
    current_notional: float
    recommended_notional: float
    reason: str
    triggers: tuple[str, ...]

    @property
    def downshifted(self) -> bool:
        return self.recommended_notional < self.current_notional

    def to_dict(self) -> dict:
        return {
            "current_notional": self.current_notional,
            "recommended_notional": self.recommended_notional,
            "downshifted": self.downshifted,
            "reason": self.reason,
            "triggers": list(self.triggers),
        }


@dataclass(frozen=True)
class StrategyPaperCapitalLadderDecision:
    strategy_name: str
    current_notional: float
    approved_notional: float
    reason: str

    @property
    def passed(self) -> bool:
        return self.approved_notional >= self.current_notional

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "current_notional": self.current_notional,
            "approved_notional": self.approved_notional,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyPaperCapitalLadderReport:
    decisions: tuple[StrategyPaperCapitalLadderDecision, ...]

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "decisions": [decision.to_dict() for decision in self.decisions]}


@dataclass(frozen=True)
class PaperLiveFireDrillReport:
    drills: tuple[Mapping[str, Any], ...]

    @property
    def missing_drills(self) -> tuple[str, ...]:
        passed = {str(row.get("name")) for row in self.drills if row.get("passed") and row.get("paper_evidence_path")}
        return tuple(name for name in REQUIRED_LIVE_FIRE_DRILLS if name not in passed)

    @property
    def passed(self) -> bool:
        return not self.missing_drills

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "drills": [dict(row) for row in self.drills],
            "missing_drills": list(self.missing_drills),
        }


@dataclass(frozen=True)
class StrategyFamilyOvernightGateReport:
    families: tuple[Mapping[str, Any], ...]

    @property
    def blocked_families(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.families if bool(row.get("holds_overnight")) and not bool(row.get("clean_flatten_proven")))

    @property
    def passed(self) -> bool:
        return not self.blocked_families

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "families": [dict(row) for row in self.families],
            "blocked_families": [dict(row) for row in self.blocked_families],
        }


@dataclass(frozen=True)
class PaperActiveEvidenceReport:
    trading_days: int
    clean_days: int
    required_days: int = 30

    @property
    def passed(self) -> bool:
        return self.trading_days >= self.required_days and self.clean_days >= self.required_days

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "trading_days": self.trading_days,
            "clean_days": self.clean_days,
            "required_days": self.required_days,
            "remaining_days": max(0, self.required_days - min(self.trading_days, self.clean_days)),
        }


@dataclass(frozen=True)
class RegimePerformanceReviewReport:
    rows: tuple[Mapping[str, Any], ...]

    @property
    def missing_regimes(self) -> tuple[str, ...]:
        covered = {str(row.get("regime")) for row in self.rows if row.get("reviewed") and row.get("paper_scorecard_passed")}
        return tuple(regime for regime in REQUIRED_REGIMES if regime not in covered)

    @property
    def passed(self) -> bool:
        return not self.missing_regimes

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "rows": [dict(row) for row in self.rows],
            "missing_regimes": list(self.missing_regimes),
        }


@dataclass(frozen=True)
class UndertradingEvidenceReport:
    opportunities: tuple[Mapping[str, Any], ...]
    min_no_trade_rate: float = 0.20

    @property
    def no_trade_rate(self) -> float:
        if not self.opportunities:
            return 0.0
        no_trades = sum(1 for row in self.opportunities if str(row.get("decision", "")).lower() in {"hold", "cash", "no_trade"})
        return no_trades / len(self.opportunities)

    @property
    def passed(self) -> bool:
        return bool(self.opportunities) and self.no_trade_rate >= self.min_no_trade_rate

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "opportunities": [dict(row) for row in self.opportunities],
            "no_trade_rate": self.no_trade_rate,
            "min_no_trade_rate": self.min_no_trade_rate,
        }


@dataclass(frozen=True)
class CashDecisionRespectReport:
    rows: tuple[Mapping[str, Any], ...]

    @property
    def violations(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.rows if bool(row.get("out_of_regime")) and str(row.get("decision", "")).lower() not in {"hold", "cash", "no_trade"})

    @property
    def passed(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "rows": [dict(row) for row in self.rows],
            "violations": [dict(row) for row in self.violations],
        }


@dataclass(frozen=True)
class PaperMonthEndReviewReport:
    sections: Mapping[str, Any]

    @property
    def missing_sections(self) -> tuple[str, ...]:
        return tuple(name for name in MONTH_END_REVIEW_SECTIONS if not self.sections.get(name))

    @property
    def passed(self) -> bool:
        return not self.missing_sections

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "sections": dict(self.sections),
            "missing_sections": list(self.missing_sections),
        }


@dataclass(frozen=True)
class SchedulerUptimeEvidenceReport:
    days_observed: int
    missed_jobs: int
    failed_jobs: int
    required_days: int = 14

    @property
    def passed(self) -> bool:
        return self.days_observed >= self.required_days and self.missed_jobs == 0 and self.failed_jobs == 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "days_observed": self.days_observed,
            "missed_jobs": self.missed_jobs,
            "failed_jobs": self.failed_jobs,
            "required_days": self.required_days,
            "remaining_days": max(0, self.required_days - self.days_observed),
        }


def build_paper_notional_escalation_report(
    evidence: Mapping[str, Any],
    current_notional: float = 25.0,
) -> PaperNotionalEscalationReport:
    decisions = tuple(_tier_decision(tier, evidence) for tier in PAPER_NOTIONAL_TIERS if tier > current_notional)
    return PaperNotionalEscalationReport(current_notional, decisions)


def build_paper_notional_downshift_decision(
    current_notional: float,
    evidence: Mapping[str, Any],
) -> PaperNotionalDownshiftDecision:
    triggers = []
    if evidence.get("failed_monitor"):
        triggers.append("failed_monitor")
    if int(evidence.get("reject_streak", 0) or 0) > 0:
        triggers.append("reject_streak")
    if evidence.get("unresolved_order"):
        triggers.append("unresolved_order")
    if evidence.get("strategy_scorecard_failed"):
        triggers.append("strategy_scorecard_failed")
    if evidence.get("data_outage"):
        triggers.append("data_outage")
    recommended = max(25.0, _previous_tier(current_notional)) if triggers else current_notional
    return PaperNotionalDownshiftDecision(current_notional, recommended, "_".join(triggers) if triggers else "no_downshift_required", tuple(triggers))


def build_strategy_paper_capital_ladder_report(
    strategies: Sequence[Mapping[str, Any]],
) -> StrategyPaperCapitalLadderReport:
    return StrategyPaperCapitalLadderReport(tuple(_strategy_ladder_decision(row) for row in strategies))


def build_paper_live_fire_drill_report(drills: Sequence[Mapping[str, Any]]) -> PaperLiveFireDrillReport:
    return PaperLiveFireDrillReport(tuple(dict(row) for row in drills))


def build_strategy_family_overnight_gate_report(families: Sequence[Mapping[str, Any]]) -> StrategyFamilyOvernightGateReport:
    return StrategyFamilyOvernightGateReport(tuple(dict(row) for row in families))


def build_paper_active_evidence_report(trading_days: int, clean_days: int, required_days: int = 30) -> PaperActiveEvidenceReport:
    return PaperActiveEvidenceReport(trading_days, clean_days, required_days)


def build_regime_performance_review_report(rows: Sequence[Mapping[str, Any]]) -> RegimePerformanceReviewReport:
    return RegimePerformanceReviewReport(tuple(dict(row) for row in rows))


def build_undertrading_evidence_report(opportunities: Sequence[Mapping[str, Any]], min_no_trade_rate: float = 0.20) -> UndertradingEvidenceReport:
    return UndertradingEvidenceReport(tuple(dict(row) for row in opportunities), min_no_trade_rate)


def build_cash_decision_respect_report(rows: Sequence[Mapping[str, Any]]) -> CashDecisionRespectReport:
    return CashDecisionRespectReport(tuple(dict(row) for row in rows))


def build_paper_month_end_review_report(sections: Mapping[str, Any]) -> PaperMonthEndReviewReport:
    return PaperMonthEndReviewReport(dict(sections))


def build_scheduler_uptime_evidence_report(days_observed: int, missed_jobs: int, failed_jobs: int, required_days: int = 14) -> SchedulerUptimeEvidenceReport:
    return SchedulerUptimeEvidenceReport(days_observed, missed_jobs, failed_jobs, required_days)


def write_paper_escalation_report(report: Any, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return destination


def _tier_decision(tier: float, evidence: Mapping[str, Any]) -> PaperNotionalTierDecision:
    if tier == 50.0:
        passed = int(evidence.get("clean_monitored_sessions", 0) or 0) >= 10
        reason = "passed" if passed else "requires_10_clean_monitored_sessions"
    elif tier == 100.0:
        passed = int(evidence.get("clean_monitored_sessions", 0) or 0) >= 20 and bool(evidence.get("clean_exit_tests")) and not bool(evidence.get("unresolved_orders"))
        reason = "passed" if passed else "requires_20_clean_sessions_clean_exits_no_unresolved_orders"
    elif tier == 250.0:
        passed = bool(evidence.get("scorecards_acceptable")) and bool(evidence.get("slippage_acceptable")) and bool(evidence.get("pnl_drift_acceptable")) and bool(evidence.get("benchmark_relative_acceptable"))
        reason = "passed" if passed else "requires_acceptable_scorecards_slippage_pnl_drift_and_benchmark_behavior"
    elif tier == 500.0:
        passed = bool(evidence.get("daily_reports_clean")) and bool(evidence.get("scheduled_jobs_clean")) and bool(evidence.get("recovery_clean")) and bool(evidence.get("monitor_clean")) and bool(evidence.get("dashboard_clean")) and int(evidence.get("clean_calendar_days", 0) or 0) >= 14
        reason = "passed" if passed else "requires_two_weeks_clean_reports_scheduler_recovery_monitor_dashboard"
    else:
        passed = bool(evidence.get("portfolio_risk_passed")) and bool(evidence.get("kill_switch_drills_passed"))
        reason = "passed" if passed else "requires_portfolio_risk_and_kill_switch_drills"
    return PaperNotionalTierDecision(tier, passed, reason, dict(evidence))


def _previous_tier(current_notional: float) -> float:
    previous = 25.0
    for tier in PAPER_NOTIONAL_TIERS:
        if tier >= current_notional:
            return previous
        previous = tier
    return previous


def _strategy_ladder_decision(row: Mapping[str, Any]) -> StrategyPaperCapitalLadderDecision:
    name = str(row.get("strategy_name") or row.get("strategy") or "unknown")
    current = float(row.get("current_notional", 25.0) or 25.0)
    evidence = dict(row.get("evidence", {}))
    approved = build_paper_notional_escalation_report(evidence, current).approved_notional
    downshift = build_paper_notional_downshift_decision(approved, evidence)
    return StrategyPaperCapitalLadderDecision(name, current, downshift.recommended_notional, downshift.reason if downshift.downshifted else "ladder_evaluated")
