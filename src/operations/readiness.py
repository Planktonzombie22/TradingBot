from dataclasses import dataclass
from typing import Any, Mapping

from src.config import RuntimeConfig

from .soak import PaperSessionSoakReport


@dataclass(frozen=True)
class PreLiveReadinessPolicy:
    min_soak_sessions: int = 3
    require_submitted_sessions: bool = True
    require_restart_recovery_proof: bool = True
    require_broker_statement_match: bool = True
    require_no_unresolved_orders: bool = True
    require_live_implementation_proof: bool = True
    live_trading_implemented: bool = False
    operator_approved_live_unlock: bool = False

    def to_dict(self) -> dict:
        return {
            "min_soak_sessions": self.min_soak_sessions,
            "require_submitted_sessions": self.require_submitted_sessions,
            "require_restart_recovery_proof": self.require_restart_recovery_proof,
            "require_broker_statement_match": self.require_broker_statement_match,
            "require_no_unresolved_orders": self.require_no_unresolved_orders,
            "require_live_implementation_proof": self.require_live_implementation_proof,
            "live_trading_implemented": self.live_trading_implemented,
            "operator_approved_live_unlock": self.operator_approved_live_unlock,
        }


@dataclass(frozen=True)
class PreLiveReadinessGate:
    name: str
    passed: bool
    reason: str
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PreLiveReadinessReport:
    policy: PreLiveReadinessPolicy
    gates: tuple[PreLiveReadinessGate, ...]
    live_unlock_allowed: bool

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def reason(self) -> str:
        if self.passed:
            return "pre_live_readiness_passed"
        return next(gate.reason for gate in self.gates if not gate.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "live_unlock_allowed": self.live_unlock_allowed,
            "policy": self.policy.to_dict(),
            "gates": [gate.to_dict() for gate in self.gates],
        }


def evaluate_pre_live_readiness(
    soak_report: PaperSessionSoakReport,
    config: RuntimeConfig,
    policy: PreLiveReadinessPolicy | None = None,
    broker_statement_matched: bool | None = None,
) -> PreLiveReadinessReport:
    policy = policy or PreLiveReadinessPolicy()
    sessions = soak_report.sessions
    submitted_sessions = [session for session in sessions if session.submitted]
    recovered_sessions = [
        session
        for session in sessions
        if session.recovery.enabled
        and session.recovery.passed
        and (
            session.recovery.orders_loaded
            or session.recovery.reports_loaded
            or session.recovery.positions_loaded
            or session.recovery.account_loaded
        )
    ]
    unresolved_orders = sum(session.recovery.unresolved_orders for session in sessions)
    dirty_reconciliation = [
        session
        for session in sessions
        if session.reconciliation_clean is False or session.recovery.blocked
    ]
    gates = (
        PreLiveReadinessGate(
            "multi_session_paper_soak",
            soak_report.passed and soak_report.completed_sessions >= policy.min_soak_sessions,
            "passed" if soak_report.passed and soak_report.completed_sessions >= policy.min_soak_sessions else "paper_soak_not_clean",
            {
                "soak_passed": soak_report.passed,
                "completed_sessions": soak_report.completed_sessions,
                "required_sessions": policy.min_soak_sessions,
            },
        ),
        PreLiveReadinessGate(
            "submitted_paper_sessions",
            (not policy.require_submitted_sessions) or bool(submitted_sessions),
            "passed" if (not policy.require_submitted_sessions) or bool(submitted_sessions) else "missing_submitted_paper_session",
            {"submitted_sessions": len(submitted_sessions)},
        ),
        PreLiveReadinessGate(
            "restart_recovery_proof",
            (not policy.require_restart_recovery_proof) or bool(recovered_sessions),
            "passed" if (not policy.require_restart_recovery_proof) or bool(recovered_sessions) else "missing_restart_recovery_proof",
            {"recovered_sessions": len(recovered_sessions)},
        ),
        PreLiveReadinessGate(
            "broker_statement_match",
            (not policy.require_broker_statement_match) or broker_statement_matched is True,
            "passed" if (not policy.require_broker_statement_match) or broker_statement_matched is True else "missing_broker_statement_match",
            {"broker_statement_matched": broker_statement_matched},
        ),
        PreLiveReadinessGate(
            "no_unresolved_orders",
            (not policy.require_no_unresolved_orders) or (unresolved_orders == 0 and not dirty_reconciliation),
            "passed" if (not policy.require_no_unresolved_orders) or (unresolved_orders == 0 and not dirty_reconciliation) else "unresolved_orders_present",
            {
                "unresolved_orders": unresolved_orders,
                "dirty_reconciliation_sessions": len(dirty_reconciliation),
            },
        ),
        PreLiveReadinessGate(
            "live_execution_implementation",
            (not policy.require_live_implementation_proof) or policy.live_trading_implemented,
            "passed" if (not policy.require_live_implementation_proof) or policy.live_trading_implemented else "live_execution_not_implemented",
            {
                "live_trading_implemented": policy.live_trading_implemented,
                "allow_live_trading": config.execution.allow_live_trading,
            },
        ),
        PreLiveReadinessGate(
            "operator_live_unlock_approval",
            policy.operator_approved_live_unlock,
            "passed" if policy.operator_approved_live_unlock else "missing_operator_live_unlock_approval",
            {"operator_approved_live_unlock": policy.operator_approved_live_unlock},
        ),
        PreLiveReadinessGate(
            "live_flag_guard",
            (not config.execution.allow_live_trading) or (policy.live_trading_implemented and policy.operator_approved_live_unlock),
            "passed"
            if (not config.execution.allow_live_trading) or (policy.live_trading_implemented and policy.operator_approved_live_unlock)
            else "allow_live_trading_set_without_unlock",
            {"allow_live_trading": config.execution.allow_live_trading},
        ),
    )
    passed = all(gate.passed for gate in gates)
    return PreLiveReadinessReport(
        policy=policy,
        gates=gates,
        live_unlock_allowed=passed and policy.live_trading_implemented and policy.operator_approved_live_unlock,
    )
