import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.operations import (
    AutonomousPaperSessionResult,
    PaperSessionSoakReport,
    PortfolioPaperSessionReport,
    PromotionQueueReport,
)


@dataclass(frozen=True)
class DailyPaperTradingReport:
    report_date: str
    sessions: tuple[AutonomousPaperSessionResult, ...] = ()
    portfolio_report: PortfolioPaperSessionReport | None = None
    soak_report: PaperSessionSoakReport | None = None
    promotion_queue: PromotionQueueReport | None = None
    notes: tuple[str, ...] = ()

    @property
    def orders_planned(self) -> int:
        portfolio_orders = len(self.portfolio_report.consolidated_orders) if self.portfolio_report else 0
        return sum(session.orders_planned for session in self.sessions) + portfolio_orders

    @property
    def orders_submitted(self) -> int:
        return sum(session.orders_submitted for session in self.sessions)

    @property
    def sessions_ready(self) -> int:
        return sum(1 for session in self.sessions if session.ready_for_submission)

    @property
    def warnings(self) -> tuple[str, ...]:
        values: list[str] = []
        for session in self.sessions:
            values.extend(session.warnings)
        if self.portfolio_report and not self.portfolio_report.ready_for_submission:
            values.append("Portfolio paper session is not ready for submission.")
        if self.soak_report and not self.soak_report.passed:
            values.append("Paper-session soak checks did not pass.")
        if self.promotion_queue and self.promotion_queue.blocked_decisions:
            values.append(f"{len(self.promotion_queue.blocked_decisions)} promotion queue candidate(s) are blocked.")
        return tuple(values)

    @property
    def recommendations(self) -> tuple[str, ...]:
        recommendations: list[str] = []
        if self.warnings:
            recommendations.append("Resolve warnings before escalating paper exposure.")
        if any(session.recovery.blocked for session in self.sessions):
            recommendations.append("Reconcile persisted broker state before the next paper session.")
        if any(session.submitted and session.reconciliation_clean is not True for session in self.sessions):
            recommendations.append("Investigate unreconciled submitted orders before new submissions.")
        if any(session.paper_scorecard_passed is False for session in self.sessions):
            recommendations.append("Demote or pause candidates with failing paper scorecards.")
        if self.soak_report and not self.soak_report.passed:
            recommendations.append("Continue dry-run soaks until all soak gates pass.")
        if self.promotion_queue and self.promotion_queue.enabled_decisions:
            recommendations.append("Use enabled promotion queue manifests as the next paper-session candidate set.")
        if not recommendations:
            recommendations.append("Continue with guarded dry-run or micro-notional paper rehearsal.")
        return tuple(dict.fromkeys(recommendations))

    def to_dict(self) -> dict:
        return {
            "report_date": self.report_date,
            "summary": {
                "sessions": len(self.sessions),
                "sessions_ready": self.sessions_ready,
                "orders_planned": self.orders_planned,
                "orders_submitted": self.orders_submitted,
                "submitted_sessions": sum(1 for session in self.sessions if session.submitted),
                "data_drift_reports": sum(session.data_drift_reports for session in self.sessions),
                "promotion_enabled": len(self.promotion_queue.enabled_decisions) if self.promotion_queue else 0,
                "promotion_blocked": len(self.promotion_queue.blocked_decisions) if self.promotion_queue else 0,
            },
            "decisions": [_session_decision_payload(session) for session in self.sessions],
            "orders": _orders_payload(self.sessions, self.portfolio_report),
            "fills": _fills_payload(self.sessions),
            "reconciliation": _reconciliation_payload(self.sessions),
            "scorecards": _scorecard_payload(self.sessions),
            "data_drift": [
                {"report_path": session.report_path, "reports": session.data_drift_reports}
                for session in self.sessions
                if session.data_drift_reports
            ],
            "portfolio": self.portfolio_report.to_dict() if self.portfolio_report else None,
            "soak": self.soak_report.to_dict() if self.soak_report else None,
            "promotion_queue": self.promotion_queue.to_dict() if self.promotion_queue else None,
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class PaperActivationReport:
    report_date: str
    broker_proof: Mapping[str, Any] | None = None
    scheduled_broker_proof: Mapping[str, Any] | None = None
    paper_submit_evidence: Mapping[str, Any] | None = None
    paper_cleanup: Mapping[str, Any] | None = None
    notes: tuple[str, ...] = ()

    @property
    def broker_submitted(self) -> bool:
        return bool((self.broker_proof or {}).get("submitted", False))

    @property
    def broker_passed(self) -> bool:
        return bool((self.broker_proof or {}).get("passed", False))

    @property
    def schedule_passed(self) -> bool:
        return bool((self.scheduled_broker_proof or {}).get("passed", False))

    @property
    def cleanup_present(self) -> bool:
        return self.paper_cleanup is not None

    @property
    def cleanup_submitted(self) -> bool:
        return bool((self.paper_cleanup or {}).get("submitted", False))

    @property
    def cleanup_blocked(self) -> bool:
        if not self.paper_cleanup:
            return False
        return bool(self.paper_cleanup.get("submit_requested")) and not bool(self.paper_cleanup.get("submitted"))

    @property
    def cleanup_positions_remaining(self) -> int:
        return len((self.paper_cleanup or {}).get("positions_seen", []))

    @property
    def evidence_by_id(self) -> dict[str, Mapping[str, Any]]:
        if not self.paper_submit_evidence:
            return {}
        return {
            str(item.get("check_id")): dict(item)
            for item in self.paper_submit_evidence.get("evidence", [])
        }

    @property
    def warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        if not self.broker_proof:
            warnings.append("Direct broker-proof artifact is missing.")
        elif not self.broker_passed:
            warnings.append(f"Direct broker proof did not pass: {(self.broker_proof or {}).get('reason', 'unknown')}.")
        if not self.scheduled_broker_proof:
            warnings.append("Scheduled broker-proof artifact is missing.")
        elif not self.schedule_passed:
            warnings.append(f"Scheduled broker proof did not pass: {_schedule_reason(self.scheduled_broker_proof)}.")
        if self.paper_cleanup:
            if self.cleanup_blocked:
                warnings.append(f"Paper cleanup did not submit: {self.paper_cleanup.get('reason', 'unknown')}.")
            elif self.cleanup_positions_remaining and not self.cleanup_submitted:
                warnings.append(f"Paper cleanup preview still shows {self.cleanup_positions_remaining} open position(s).")
        for check_id in ("alpaca_paper_order_lifecycle", "real_alpaca_fill_polling", "broker_account_parity", "paper_account_parity"):
            evidence = self.evidence_by_id.get(check_id)
            if evidence and evidence.get("status") != "passed":
                warnings.append(f"{check_id} evidence is {evidence.get('status')}: {evidence.get('reason')}.")
        return tuple(warnings)

    @property
    def recommendations(self) -> tuple[str, ...]:
        recommendations: list[str] = []
        if not self.broker_submitted:
            recommendations.append("Run the guarded broker proof during the next regular market-session window.")
        if self.broker_submitted and not self.evidence_by_id.get("real_alpaca_fill_polling", {}).get("passed", False):
            recommendations.append("Review broker-polled execution reports before escalating autonomous paper submission.")
        if self.evidence_by_id.get("broker_account_parity", {}).get("status") == "failed":
            recommendations.append("Resolve broker account parity before the next paper activation step.")
        if self.paper_cleanup and self.cleanup_positions_remaining and not self.cleanup_submitted:
            recommendations.append("Run guarded paper cleanup during the next regular market-session window before retrying promoted portfolios.")
        if self.paper_cleanup and self.cleanup_submitted and self.paper_cleanup.get("reconciliation_clean") is not True:
            recommendations.append("Review paper cleanup reconciliation before retrying promoted portfolios.")
        if not self.schedule_passed:
            recommendations.append("Keep scheduled proof automation enabled, but do not override closed-session blocks.")
        if not recommendations:
            recommendations.append("Continue to autonomous paper-session micro-notional promotion.")
        return tuple(dict.fromkeys(recommendations))

    def to_dict(self) -> dict:
        evidence = self.evidence_by_id
        return {
            "report_date": self.report_date,
            "summary": {
                "broker_proof_present": self.broker_proof is not None,
                "broker_passed": self.broker_passed,
                "broker_submitted": self.broker_submitted,
                "broker_reason": (self.broker_proof or {}).get("reason"),
                "scheduled_proof_present": self.scheduled_broker_proof is not None,
                "scheduled_passed": self.schedule_passed,
                "scheduled_reason": _schedule_reason(self.scheduled_broker_proof),
                "orders": len((self.broker_proof or {}).get("orders", [])),
                "execution_reports": len((self.broker_proof or {}).get("execution_reports", [])),
                "polled_execution_reports": len((self.broker_proof or {}).get("polled_execution_reports", [])),
                "cleanup_present": self.cleanup_present,
                "cleanup_submitted": self.cleanup_submitted,
                "cleanup_reason": (self.paper_cleanup or {}).get("reason"),
                "cleanup_positions_seen": self.cleanup_positions_remaining,
            },
            "broker_proof": self.broker_proof,
            "scheduled_broker_proof": self.scheduled_broker_proof,
            "paper_submit_evidence": {
                check_id: evidence.get(check_id)
                for check_id in (
                    "alpaca_paper_order_lifecycle",
                    "paper_broker_proof_schedule",
                    "real_alpaca_fill_polling",
                    "broker_account_parity",
                    "paper_account_parity",
                )
            },
            "paper_cleanup": self.paper_cleanup,
            "next_windows": _next_windows(self.scheduled_broker_proof),
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
            "notes": list(self.notes),
        }


def build_daily_paper_trading_report(
    sessions: Sequence[AutonomousPaperSessionResult] = (),
    portfolio_report: PortfolioPaperSessionReport | None = None,
    soak_report: PaperSessionSoakReport | None = None,
    promotion_queue: PromotionQueueReport | None = None,
    report_date: str | date | None = None,
    notes: Sequence[str] = (),
) -> DailyPaperTradingReport:
    value = report_date or date.today()
    normalized_date = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return DailyPaperTradingReport(
        report_date=normalized_date,
        sessions=tuple(sessions),
        portfolio_report=portfolio_report,
        soak_report=soak_report,
        promotion_queue=promotion_queue,
        notes=tuple(notes),
    )


def build_paper_activation_report(
    broker_proof_path: str | Path | None = None,
    scheduled_broker_proof_path: str | Path | None = None,
    paper_submit_evidence_path: str | Path | None = None,
    paper_cleanup_path: str | Path | None = None,
    report_date: str | date | None = None,
    notes: Sequence[str] = (),
) -> PaperActivationReport:
    value = report_date or date.today()
    normalized_date = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return PaperActivationReport(
        report_date=normalized_date,
        broker_proof=_load_optional_json(broker_proof_path),
        scheduled_broker_proof=_load_optional_json(scheduled_broker_proof_path),
        paper_submit_evidence=_load_optional_json(paper_submit_evidence_path),
        paper_cleanup=_load_optional_json(paper_cleanup_path),
        notes=tuple(notes),
    )


def write_daily_paper_trading_report(report: DailyPaperTradingReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return destination


def write_paper_activation_report(report: PaperActivationReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return destination


def _load_optional_json(path: str | Path | None) -> Mapping[str, Any] | None:
    if not path:
        return None
    source = Path(path)
    if not source.exists():
        return None
    return json.loads(source.read_text(encoding="utf-8"))


def _schedule_reason(payload: Mapping[str, Any] | None) -> str | None:
    if not payload:
        return None
    for check in payload.get("checks", []):
        if not check.get("passed"):
            return str(check.get("reason") or "scheduled_broker_proof_failed")
    return "passed" if payload.get("passed") else "scheduled_broker_proof_failed"


def _next_windows(payload: Mapping[str, Any] | None) -> list[dict]:
    if not payload:
        return []
    return [
        {
            "name": window.get("name"),
            "start_time": window.get("start_time"),
            "end_time": window.get("end_time"),
            "submit_orders_allowed": window.get("submit_orders_allowed"),
        }
        for window in payload.get("windows", [])
        if window.get("submit_orders_allowed")
    ]


def _session_decision_payload(session: AutonomousPaperSessionResult) -> dict:
    return {
        "report_path": session.report_path,
        "ready_for_submission": session.ready_for_submission,
        "submitted": session.submitted,
        "orders_planned": session.orders_planned,
        "orders_submitted": session.orders_submitted,
        "regime": dict(session.regime),
        "warnings": list(session.warnings),
        "recovery": session.recovery.to_dict(),
    }


def _orders_payload(
    sessions: Sequence[AutonomousPaperSessionResult],
    portfolio_report: PortfolioPaperSessionReport | None,
) -> dict:
    session_orders = []
    for session in sessions:
        for order in session.planned_orders:
            payload = dict(order)
            payload["source_report_path"] = session.report_path
            session_orders.append(payload)
    return {
        "session_planned": session_orders,
        "portfolio_consolidated": [dict(order) for order in portfolio_report.consolidated_orders] if portfolio_report else [],
    }


def _fills_payload(sessions: Sequence[AutonomousPaperSessionResult]) -> dict:
    submitted = [session for session in sessions if session.submitted]
    missed = [
        session
        for session in sessions
        if session.orders_planned > session.orders_submitted
    ]
    return {
        "submitted_sessions": len(submitted),
        "missed_or_unsubmitted_sessions": len(missed),
        "expected_vs_submitted": [
            {
                "report_path": session.report_path,
                "orders_planned": session.orders_planned,
                "orders_submitted": session.orders_submitted,
            }
            for session in sessions
        ],
    }


def _reconciliation_payload(sessions: Sequence[AutonomousPaperSessionResult]) -> dict:
    submitted = [session for session in sessions if session.submitted]
    clean = sum(1 for session in submitted if session.reconciliation_clean is True)
    unresolved = [session for session in submitted if session.reconciliation_clean is not True]
    return {
        "submitted_sessions": len(submitted),
        "clean_sessions": clean,
        "unresolved_sessions": len(unresolved),
        "recovery_blocked_sessions": sum(1 for session in sessions if session.recovery.blocked),
    }


def _scorecard_payload(sessions: Sequence[AutonomousPaperSessionResult]) -> dict:
    available = [session for session in sessions if session.paper_scorecard_passed is not None]
    passed = sum(1 for session in available if session.paper_scorecard_passed is True)
    failed = sum(1 for session in available if session.paper_scorecard_passed is False)
    return {
        "available": len(available),
        "passed": passed,
        "failed": failed,
        "equity_drift_available": False,
    }
