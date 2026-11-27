import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


BROKER_EVIDENCE_CHECKS = (
    "alpaca_paper_order_lifecycle",
    "broker_account_parity",
    "paper_account_parity",
    "real_alpaca_fill_polling",
)


@dataclass(frozen=True)
class PaperPilotReport:
    cleanup: Mapping[str, Any]
    validation: Mapping[str, Any]
    activation: Mapping[str, Any]
    portfolio: Mapping[str, Any] | None = None
    artifacts: Mapping[str, str] = field(default_factory=dict)
    decision: str = "blocked"
    ready_for_promoted_portfolio_submit: bool = False
    blockers: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.ready_for_promoted_portfolio_submit and not self.blockers

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "decision": self.decision,
            "ready_for_promoted_portfolio_submit": self.ready_for_promoted_portfolio_submit,
            "blockers": list(self.blockers),
            "next_actions": list(self.next_actions),
            "artifacts": dict(self.artifacts),
            "cleanup": dict(self.cleanup),
            "validation": dict(self.validation),
            "activation": dict(self.activation),
            "portfolio": dict(self.portfolio) if self.portfolio else None,
            "artifact_path": self.artifact_path,
        }


def build_paper_pilot_report(
    cleanup: Mapping[str, Any],
    validation: Mapping[str, Any],
    activation: Mapping[str, Any],
    portfolio: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, str] | None = None,
) -> PaperPilotReport:
    blockers = _paper_pilot_blockers(cleanup, validation, portfolio)
    next_actions = _paper_pilot_next_actions(blockers, portfolio)
    ready = not blockers and bool(portfolio and portfolio.get("ready_for_submission"))
    decision = _paper_pilot_decision(blockers, portfolio, ready)
    return PaperPilotReport(
        cleanup=_cleanup_summary(cleanup),
        validation=_validation_summary(validation),
        activation=_activation_summary(activation),
        portfolio=_portfolio_summary(portfolio) if portfolio else None,
        artifacts=dict(artifacts or {}),
        decision=decision,
        ready_for_promoted_portfolio_submit=ready,
        blockers=tuple(blockers),
        next_actions=tuple(next_actions),
    )


def write_paper_pilot_report(report: PaperPilotReport, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def _paper_pilot_blockers(
    cleanup: Mapping[str, Any],
    validation: Mapping[str, Any],
    portfolio: Mapping[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    if not _paper_runtime_passed(validation):
        blockers.append("runtime_mode:alpaca_paper_required")
    cleanup_evidence = _evidence_by_id(validation).get("paper_account_cleanup")
    cleanup_ok = _cleanup_passed(cleanup) or _evidence_passed(cleanup_evidence)
    if not cleanup_ok:
        blockers.append(f"paper_account_cleanup:{_cleanup_reason(cleanup, cleanup_evidence)}")
    for check_id in BROKER_EVIDENCE_CHECKS:
        evidence = _evidence_by_id(validation).get(check_id)
        if not _evidence_passed(evidence):
            blockers.append(f"{check_id}:{_evidence_reason(evidence)}")
    if portfolio is None:
        blockers.append("portfolio_preview:missing")
    elif not portfolio.get("ready_for_submission"):
        blockers.append(f"portfolio_preview:{portfolio.get('reason') or 'not_ready_for_submission'}")
    return blockers


def _paper_pilot_next_actions(blockers: Sequence[str], portfolio: Mapping[str, Any] | None) -> list[str]:
    actions: list[str] = []
    if any(blocker.startswith("runtime_mode:") for blocker in blockers):
        actions.append("Run paper-pilot with provider=alpaca and execution-mode=paper before broker submission readiness can pass.")
    if any(blocker.startswith("paper_account_cleanup:") for blocker in blockers):
        actions.append("Run guarded paper-cleanup during an allowed market session until the cleanup artifact is flat or reconciled cleanly.")
    if any(blocker.startswith("alpaca_paper_order_lifecycle:") for blocker in blockers):
        actions.append("Run or reuse a tiny Alpaca paper broker proof with submit/cancel/fill-polling evidence.")
    if any(blocker.startswith("real_alpaca_fill_polling:") for blocker in blockers):
        actions.append("Capture broker-polled execution reports from Alpaca paper after a submitted proof order.")
    if any(blocker.startswith("broker_account_parity:") or blocker.startswith("paper_account_parity:") for blocker in blockers):
        actions.append("Refresh broker account parity evidence after the next submitted paper proof.")
    if portfolio is None:
        actions.append("Run a promoted portfolio paper preview from the latest promotion manifest.")
    elif any(blocker.startswith("portfolio_preview:") for blocker in blockers):
        actions.append("Review the portfolio preview warnings, symbols, and risk budget before allowing broker submission.")
    if not actions:
        actions.append("Proceed to a tiny promoted portfolio paper submit under the normal submission guard.")
    return actions


def _paper_pilot_decision(blockers: Sequence[str], portfolio: Mapping[str, Any] | None, ready: bool) -> str:
    if ready:
        return "ready_for_guarded_promoted_portfolio_submit"
    if any(blocker.startswith("runtime_mode:") for blocker in blockers):
        return "blocked_alpaca_paper_runtime_required"
    if any(blocker.startswith("paper_account_cleanup:") for blocker in blockers):
        return "blocked_cleanup_required"
    if any(blocker.startswith("alpaca_paper_order_lifecycle:") for blocker in blockers):
        return "blocked_broker_lifecycle_required"
    if portfolio is None:
        return "blocked_portfolio_preview_required"
    return "blocked_evidence_or_portfolio_review_required"


def _evidence_by_id(validation: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("check_id")): item
        for item in validation.get("evidence", [])
        if isinstance(item, Mapping) and item.get("check_id")
    }


def _paper_runtime_passed(validation: Mapping[str, Any]) -> bool:
    metadata = validation.get("run_metadata") or {}
    return metadata.get("provider") == "alpaca" and metadata.get("broker_mode") == "paper"


def _cleanup_summary(cleanup: Mapping[str, Any]) -> dict:
    return {
        "submit_requested": bool(cleanup.get("submit_requested")),
        "attempted": bool(cleanup.get("attempted")),
        "submitted": bool(cleanup.get("submitted")),
        "positions_seen": len(cleanup.get("positions_seen") or ()),
        "planned_orders": len(cleanup.get("planned_orders") or ()),
        "submitted_orders": len(cleanup.get("submitted_orders") or ()),
        "reconciliation_clean": cleanup.get("reconciliation_clean"),
        "polled_execution_reports": int(cleanup.get("polled_execution_reports") or 0),
        "reason": cleanup.get("reason"),
        "artifact_path": cleanup.get("artifact_path"),
    }


def _validation_summary(validation: Mapping[str, Any]) -> dict:
    evidence = _evidence_by_id(validation)
    relevant = ("paper_account_cleanup",) + BROKER_EVIDENCE_CHECKS
    return {
        "run_id": (validation.get("run_metadata") or {}).get("run_id"),
        "provider": (validation.get("run_metadata") or {}).get("provider"),
        "broker_mode": (validation.get("run_metadata") or {}).get("broker_mode"),
        "checks": {
            check_id: {
                "status": evidence.get(check_id, {}).get("status", "missing"),
                "reason": _evidence_reason(evidence.get(check_id)),
                "artifact_path": evidence.get(check_id, {}).get("artifact_path"),
            }
            for check_id in relevant
        },
        "evidence_count": len(validation.get("evidence") or ()),
        "readiness_score": (validation.get("readiness_index") or {}).get("readiness_score"),
    }


def _activation_summary(activation: Mapping[str, Any]) -> dict:
    summary = activation.get("summary") or {}
    return {
        "broker_proof_present": bool(summary.get("broker_proof_present")),
        "broker_proof_passed": bool(summary.get("broker_passed")),
        "broker_proof_submitted": bool(summary.get("broker_submitted")),
        "scheduled_proof_present": bool(summary.get("scheduled_proof_present")),
        "scheduled_proof_passed": bool(summary.get("scheduled_passed")),
        "cleanup_present": bool(summary.get("cleanup_present")),
        "cleanup_submitted": bool(summary.get("cleanup_submitted")),
        "cleanup_positions_seen": int(summary.get("cleanup_positions_seen") or 0),
        "cleanup_reason": summary.get("cleanup_reason"),
        "warnings": list(activation.get("warnings") or ()),
        "recommendations": list(activation.get("recommendations") or ()),
    }


def _portfolio_summary(portfolio: Mapping[str, Any]) -> dict:
    submission = portfolio.get("submission") or {}
    return {
        "ready_for_submission": bool(portfolio.get("ready_for_submission")),
        "symbols": list(portfolio.get("symbols") or ()),
        "accepted_symbols": list(portfolio.get("accepted_symbols") or ()),
        "candidate_count": int(portfolio.get("candidate_count") or 0),
        "consolidated_order_count": int(portfolio.get("consolidated_order_count") or 0),
        "artifact_path": portfolio.get("artifact_path"),
        "submission": {
            "submit_requested": bool(submission.get("submit_requested")),
            "attempted": bool(submission.get("attempted")),
            "submitted": bool(submission.get("submitted")),
            "orders_submitted": int(submission.get("orders_submitted") or 0),
            "reason": submission.get("reason"),
            "reconciliation_clean": submission.get("reconciliation_clean"),
        },
    }


def _cleanup_passed(cleanup: Mapping[str, Any]) -> bool:
    positions = cleanup.get("positions_seen") or ()
    return not positions or bool(cleanup.get("submitted") and cleanup.get("reconciliation_clean") is True)


def _cleanup_reason(cleanup: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> str:
    if evidence and evidence.get("reason"):
        return str(evidence["reason"])
    return str(cleanup.get("reason") or "paper_cleanup_required")


def _evidence_passed(evidence: Mapping[str, Any] | None) -> bool:
    return bool(evidence and evidence.get("status") == "passed")


def _evidence_reason(evidence: Mapping[str, Any] | None) -> str:
    if not evidence:
        return "missing"
    return str(evidence.get("reason") or evidence.get("status") or "not_passed")
