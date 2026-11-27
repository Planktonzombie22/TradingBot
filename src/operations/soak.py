import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, List, Mapping

from src.app import TradingApplication

from .paper_session import AutonomousPaperSessionOptions, AutonomousPaperSessionResult, run_autonomous_paper_session


@dataclass(frozen=True)
class SoakCheck:
    name: str
    passed: bool
    evidence: str = ""


@dataclass(frozen=True)
class SoakChecklist:
    checks: List[SoakCheck] = field(default_factory=list)

    @classmethod
    def default(cls) -> "SoakChecklist":
        return cls(
            [
                SoakCheck("several_market_sessions", False, "Run across multiple regular market sessions."),
                SoakCheck("no_unreconciled_orders", False, "Broker and local order state match after each session."),
                SoakCheck("clean_restarts", False, "Restart recovery restores account, orders, positions, and reports."),
                SoakCheck("no_unhandled_exceptions", False, "Logs contain no unhandled runtime exceptions."),
                SoakCheck("broker_statement_match", False, "PnL, cash, positions, and fills match broker statements."),
            ]
        )

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def with_result(self, name: str, passed: bool, evidence: str = "") -> "SoakChecklist":
        updated = [
            SoakCheck(check.name, passed, evidence) if check.name == name else check
            for check in self.checks
        ]
        return SoakChecklist(updated)


@dataclass(frozen=True)
class PaperSessionSoakConfig:
    sessions: int = 3
    require_ready: bool = True
    require_no_warnings: bool = True
    require_artifacts: bool = True
    require_reconciliation_when_submitted: bool = True
    require_scorecard_when_submitted: bool = True
    stop_on_failure: bool = False
    min_clean_streak_for_promotion: int = 10
    operator_acknowledged_failure: bool = False
    operator_failure_action: str | None = None


@dataclass(frozen=True)
class PaperSoakSessionScore:
    index: int
    passed: bool
    ready_for_submission: bool
    submitted: bool
    runtime_seconds: float
    exposure: float
    pnl: float | None
    fill_quality: str
    drift_reports: int
    monitor_status: str
    failure_reasons: tuple[str, ...] = ()
    report_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "passed": self.passed,
            "ready_for_submission": self.ready_for_submission,
            "submitted": self.submitted,
            "runtime_seconds": self.runtime_seconds,
            "exposure": self.exposure,
            "pnl": self.pnl,
            "fill_quality": self.fill_quality,
            "drift_reports": self.drift_reports,
            "monitor_status": self.monitor_status,
            "failure_reasons": list(self.failure_reasons),
            "report_path": self.report_path,
        }


@dataclass(frozen=True)
class PaperSoakScoreboard:
    session_scores: tuple[PaperSoakSessionScore, ...]

    @property
    def passed_sessions(self) -> int:
        return sum(1 for score in self.session_scores if score.passed)

    @property
    def failed_sessions(self) -> int:
        return len(self.session_scores) - self.passed_sessions

    @property
    def current_pass_streak(self) -> int:
        streak = 0
        for score in reversed(self.session_scores):
            if not score.passed:
                break
            streak += 1
        return streak

    @property
    def current_fail_streak(self) -> int:
        streak = 0
        for score in reversed(self.session_scores):
            if score.passed:
                break
            streak += 1
        return streak

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        for score in self.session_scores:
            reasons.extend(score.failure_reasons)
        return tuple(dict.fromkeys(reasons))

    @property
    def total_exposure(self) -> float:
        return sum(score.exposure for score in self.session_scores)

    @property
    def total_pnl(self) -> float | None:
        values = [score.pnl for score in self.session_scores if score.pnl is not None]
        return sum(values) if values else None

    @property
    def average_runtime_seconds(self) -> float:
        if not self.session_scores:
            return 0.0
        return sum(score.runtime_seconds for score in self.session_scores) / len(self.session_scores)

    def to_dict(self) -> dict:
        return {
            "passed_sessions": self.passed_sessions,
            "failed_sessions": self.failed_sessions,
            "current_pass_streak": self.current_pass_streak,
            "current_fail_streak": self.current_fail_streak,
            "failure_reasons": list(self.failure_reasons),
            "total_exposure": self.total_exposure,
            "total_pnl": self.total_pnl,
            "average_runtime_seconds": self.average_runtime_seconds,
            "sessions": [score.to_dict() for score in self.session_scores],
        }


@dataclass(frozen=True)
class PaperSoakPromotionGate:
    required_clean_streak: int
    current_clean_streak: int
    passed: bool
    reason: str

    @property
    def graduation_allowed(self) -> bool:
        return self.passed

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "graduation_allowed": self.graduation_allowed,
            "reason": self.reason,
            "required_clean_streak": self.required_clean_streak,
            "current_clean_streak": self.current_clean_streak,
        }


@dataclass(frozen=True)
class PaperSoakFailureHalt:
    halted: bool
    acknowledged: bool = False
    operator_action: str | None = None
    reason: str = "passed"
    allowed_actions: tuple[str, ...] = ("retry", "flatten", "disable")

    @property
    def release_allowed(self) -> bool:
        return (not self.halted) or (self.acknowledged and self.operator_action in self.allowed_actions)

    def to_dict(self) -> dict:
        return {
            "halted": self.halted,
            "acknowledged": self.acknowledged,
            "operator_action": self.operator_action,
            "release_allowed": self.release_allowed,
            "reason": self.reason,
            "allowed_actions": list(self.allowed_actions),
        }


@dataclass(frozen=True)
class PaperSessionSoakReport:
    config: PaperSessionSoakConfig
    options: AutonomousPaperSessionOptions
    sessions: tuple[AutonomousPaperSessionResult, ...]
    checks: tuple[SoakCheck, ...]
    scoreboard: PaperSoakScoreboard = field(default_factory=lambda: PaperSoakScoreboard(()))
    promotion_gate: PaperSoakPromotionGate | None = None
    failure_halt: PaperSoakFailureHalt | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def completed_sessions(self) -> int:
        return len(self.sessions)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "completed_sessions": self.completed_sessions,
            "config": {
                "sessions": self.config.sessions,
                "require_ready": self.config.require_ready,
                "require_no_warnings": self.config.require_no_warnings,
                "require_artifacts": self.config.require_artifacts,
                "require_reconciliation_when_submitted": self.config.require_reconciliation_when_submitted,
                "require_scorecard_when_submitted": self.config.require_scorecard_when_submitted,
                "stop_on_failure": self.config.stop_on_failure,
                "min_clean_streak_for_promotion": self.config.min_clean_streak_for_promotion,
                "operator_acknowledged_failure": self.config.operator_acknowledged_failure,
                "operator_failure_action": self.config.operator_failure_action,
            },
            "options": {
                "submit_orders": self.options.submit_orders,
                "artifact_root": self.options.artifact_root,
                "comparison_provider": self.options.comparison_provider,
                "require_data_health": self.options.require_data_health,
                "max_position_weight": self.options.max_position_weight,
            },
            "checks": [
                {"name": check.name, "passed": check.passed, "evidence": check.evidence}
                for check in self.checks
            ],
            "scoreboard": self.scoreboard.to_dict(),
            "promotion_gate": self.promotion_gate.to_dict() if self.promotion_gate else None,
            "failure_halt": self.failure_halt.to_dict() if self.failure_halt else None,
            "sessions": [session.to_dict() for session in self.sessions],
        }


def run_paper_session_soak(
    app: TradingApplication,
    options: AutonomousPaperSessionOptions | None = None,
    config: PaperSessionSoakConfig | None = None,
) -> PaperSessionSoakReport:
    options = options or AutonomousPaperSessionOptions()
    config = config or PaperSessionSoakConfig()
    results: list[AutonomousPaperSessionResult] = []
    runtimes: list[float] = []

    for index in range(config.sessions):
        session_options = replace(options, artifact_root=f"{options.artifact_root}/session-{index + 1:02d}")
        started = perf_counter()
        result = run_autonomous_paper_session(app, session_options)
        runtimes.append(perf_counter() - started)
        results.append(result)
        if config.stop_on_failure and _blocking_failure(result, config):
            break

    sessions = tuple(results)
    checks = tuple(_soak_checks(sessions, config))
    scoreboard = build_paper_soak_scoreboard(sessions, config, tuple(runtimes))
    promotion_gate = evaluate_paper_soak_promotion_gate(scoreboard, config.min_clean_streak_for_promotion)
    failure_halt = evaluate_paper_soak_failure_halt(
        checks,
        scoreboard,
        acknowledged=config.operator_acknowledged_failure,
        operator_action=config.operator_failure_action,
    )
    return PaperSessionSoakReport(
        config=config,
        options=options,
        sessions=sessions,
        checks=checks,
        scoreboard=scoreboard,
        promotion_gate=promotion_gate,
        failure_halt=failure_halt,
    )


def write_paper_session_soak_report(report: PaperSessionSoakReport, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return str(output)


def build_paper_soak_scoreboard(
    sessions: tuple[AutonomousPaperSessionResult, ...],
    config: PaperSessionSoakConfig | None = None,
    runtimes: tuple[float, ...] = (),
) -> PaperSoakScoreboard:
    config = config or PaperSessionSoakConfig()
    scores = tuple(
        _session_score(index, session, config, runtimes[index - 1] if index - 1 < len(runtimes) else 0.0)
        for index, session in enumerate(sessions, start=1)
    )
    return PaperSoakScoreboard(scores)


def evaluate_paper_soak_promotion_gate(
    scoreboard: PaperSoakScoreboard,
    required_clean_streak: int = 10,
) -> PaperSoakPromotionGate:
    passed = scoreboard.current_pass_streak >= required_clean_streak
    return PaperSoakPromotionGate(
        required_clean_streak=required_clean_streak,
        current_clean_streak=scoreboard.current_pass_streak,
        passed=passed,
        reason="paper_soak_clean_streak_passed" if passed else "paper_soak_clean_streak_incomplete",
    )


def evaluate_paper_soak_failure_halt(
    checks: tuple[SoakCheck, ...],
    scoreboard: PaperSoakScoreboard,
    acknowledged: bool = False,
    operator_action: str | None = None,
) -> PaperSoakFailureHalt:
    failed_checks = tuple(check.name for check in checks if not check.passed)
    failure_reasons = tuple(dict.fromkeys(failed_checks + scoreboard.failure_reasons))
    if not failure_reasons:
        return PaperSoakFailureHalt(halted=False, acknowledged=acknowledged, operator_action=operator_action)
    return PaperSoakFailureHalt(
        halted=True,
        acknowledged=acknowledged,
        operator_action=operator_action,
        reason=";".join(failure_reasons),
    )


def _blocking_failure(result: AutonomousPaperSessionResult, config: PaperSessionSoakConfig) -> bool:
    if config.require_ready and not result.ready_for_submission:
        return True
    if config.require_no_warnings and result.warnings:
        return True
    if config.require_artifacts and not result.report_path:
        return True
    if result.submitted and config.require_reconciliation_when_submitted and result.reconciliation_clean is False:
        return True
    if result.submitted and config.require_scorecard_when_submitted and result.paper_scorecard_passed is False:
        return True
    return False


def _session_score(
    index: int,
    session: AutonomousPaperSessionResult,
    config: PaperSessionSoakConfig,
    runtime_seconds: float,
) -> PaperSoakSessionScore:
    reasons = tuple(_session_failure_reasons(session, config))
    return PaperSoakSessionScore(
        index=index,
        passed=not reasons,
        ready_for_submission=session.ready_for_submission,
        submitted=session.submitted,
        runtime_seconds=runtime_seconds,
        exposure=_session_exposure(session),
        pnl=_session_pnl(session),
        fill_quality=_fill_quality(session),
        drift_reports=session.data_drift_reports,
        monitor_status=_monitor_status(session),
        failure_reasons=reasons,
        report_path=session.report_path,
    )


def _session_failure_reasons(
    session: AutonomousPaperSessionResult,
    config: PaperSessionSoakConfig,
) -> Iterable[str]:
    if config.require_ready and not session.ready_for_submission:
        yield "not_ready_for_submission"
    if config.require_no_warnings and session.warnings:
        yield "session_warnings"
    if config.require_artifacts and not session.report_path:
        yield "missing_session_report"
    if session.submitted and config.require_reconciliation_when_submitted and session.reconciliation_clean is not True:
        yield "submitted_session_unreconciled"
    if session.submitted and config.require_scorecard_when_submitted and session.paper_scorecard_passed is not True:
        yield "paper_scorecard_failed"


def _session_exposure(session: AutonomousPaperSessionResult) -> float:
    total = 0.0
    for order in session.planned_orders:
        if not isinstance(order, Mapping):
            continue
        symbol = str(order.get("symbol") or "").upper()
        price = session.latest_prices.get(symbol)
        if price is None:
            continue
        total += abs(float(order.get("quantity") or 0.0) * float(price))
    return total


def _session_pnl(session: AutonomousPaperSessionResult) -> float | None:
    statement = (session.recovery.to_dict() if session.recovery else {}).get("broker_statement") or {}
    value = statement.get("realized_pnl") if isinstance(statement, Mapping) else None
    return float(value) if value is not None else None


def _fill_quality(session: AutonomousPaperSessionResult) -> str:
    if not session.submitted:
        return "not_submitted"
    if session.paper_scorecard_passed is True:
        return "passed"
    if session.paper_scorecard_passed is False:
        return "failed"
    return "unknown"


def _monitor_status(session: AutonomousPaperSessionResult) -> str:
    if "paper_monitor" in session.artifact_paths:
        return "present"
    return "not_required_for_session"


def _soak_checks(
    sessions: tuple[AutonomousPaperSessionResult, ...],
    config: PaperSessionSoakConfig,
) -> Iterable[SoakCheck]:
    yield SoakCheck(
        "minimum_sessions",
        len(sessions) >= config.sessions,
        f"completed={len(sessions)} required={config.sessions}",
    )
    yield SoakCheck(
        "all_ready_for_submission",
        (not config.require_ready) or all(session.ready_for_submission for session in sessions),
        f"ready={sum(1 for session in sessions if session.ready_for_submission)} total={len(sessions)}",
    )
    warning_count = sum(len(session.warnings) for session in sessions)
    yield SoakCheck(
        "no_session_warnings",
        (not config.require_no_warnings) or warning_count == 0,
        f"warnings={warning_count}",
    )
    reports_written = sum(1 for session in sessions if session.report_path)
    yield SoakCheck(
        "artifact_reports_written",
        (not config.require_artifacts) or reports_written == len(sessions),
        f"reports={reports_written} total={len(sessions)}",
    )
    submitted = [session for session in sessions if session.submitted]
    unreconciled = [
        session
        for session in submitted
        if session.reconciliation_clean is not True
    ]
    yield SoakCheck(
        "submitted_orders_reconciled",
        (not config.require_reconciliation_when_submitted) or not unreconciled,
        f"submitted_sessions={len(submitted)} unreconciled={len(unreconciled)}",
    )
    failed_scorecards = [
        session
        for session in submitted
        if session.paper_scorecard_passed is not True
    ]
    yield SoakCheck(
        "paper_scorecards_passed",
        (not config.require_scorecard_when_submitted) or not failed_scorecards,
        f"submitted_sessions={len(submitted)} failed_scorecards={len(failed_scorecards)}",
    )
