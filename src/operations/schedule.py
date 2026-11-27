from dataclasses import dataclass, replace
from datetime import datetime, time, timezone
import json
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from src.app import TradingApplication
from src.data import MarketSession, MarketSessionCalendar

from .paper_session import AutonomousPaperSessionOptions, AutonomousPaperSessionResult, run_autonomous_paper_session


@dataclass(frozen=True)
class PaperSessionScheduleWindow:
    name: str
    start_time: time
    end_time: time
    required: bool = True
    submit_orders_allowed: bool = False
    description: str = ""

    def contains(self, value: datetime) -> bool:
        current = value.timetz().replace(tzinfo=None)
        return self.start_time <= current <= self.end_time

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "required": self.required,
            "submit_orders_allowed": self.submit_orders_allowed,
            "description": self.description,
        }


@dataclass(frozen=True)
class ScheduledPaperSessionRecord:
    window_name: str
    ran_at: datetime
    result: AutonomousPaperSessionResult | Mapping

    @property
    def passed(self) -> bool:
        payload = _result_payload(self.result)
        return bool(payload.get("ready_for_submission", False)) and not payload.get("warnings", ())

    @property
    def submitted(self) -> bool:
        return bool(_result_payload(self.result).get("submitted", False))

    def to_dict(self) -> dict:
        return {
            "window_name": self.window_name,
            "ran_at": self.ran_at.isoformat(),
            "passed": self.passed,
            "submitted": self.submitted,
            "result": _result_payload(self.result),
        }


@dataclass(frozen=True)
class PaperSessionScheduleReport:
    windows: tuple[PaperSessionScheduleWindow, ...]
    records: tuple[ScheduledPaperSessionRecord, ...]
    checks: tuple[Mapping, ...]
    active_window: str | None = None
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(bool(check["passed"]) for check in self.checks)

    def to_evidence(self, check_id: str = "paper_session_schedule") -> "ValidationEvidence":
        from src.validation.manifest import ValidationEvidence

        return ValidationEvidence(
            check_id,
            "passed" if self.passed else "failed",
            reason="passed" if self.passed else "scheduled_paper_session_window_failed",
            metadata=self.to_dict(),
        )

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "active_window": self.active_window,
            "windows": [window.to_dict() for window in self.windows],
            "records": [record.to_dict() for record in self.records],
            "checks": [dict(check) for check in self.checks],
            "artifact_path": self.artifact_path,
        }


def default_paper_session_schedule_windows() -> tuple[PaperSessionScheduleWindow, ...]:
    return (
        PaperSessionScheduleWindow("pre_market", time(8, 0), time(8, 45), required=False, description="Pre-market data and recovery check."),
        PaperSessionScheduleWindow("market_open", time(8, 30), time(10, 0), submit_orders_allowed=True, description="Opening-session guarded paper decision."),
        PaperSessionScheduleWindow("intraday", time(10, 0), time(14, 30), submit_orders_allowed=True, description="Intraday data/reconciliation check."),
        PaperSessionScheduleWindow("market_close", time(14, 30), time(15, 15), submit_orders_allowed=True, description="Closing-session guarded paper decision."),
        PaperSessionScheduleWindow("end_of_day", time(15, 15), time(17, 0), submit_orders_allowed=False, description="Daily report and no-new-orders evidence window."),
    )


def evaluate_paper_session_schedule(
    records: Sequence[ScheduledPaperSessionRecord],
    windows: Sequence[PaperSessionScheduleWindow] | None = None,
) -> PaperSessionScheduleReport:
    windows = tuple(windows or default_paper_session_schedule_windows())
    records = tuple(records)
    checks = []
    by_window = {}
    for record in records:
        by_window.setdefault(record.window_name, []).append(record)
    for window in windows:
        window_records = tuple(by_window.get(window.name, ()))
        in_window = tuple(record for record in window_records if window.contains(record.ran_at))
        submitted_when_blocked = any(record.submitted for record in in_window) and not window.submit_orders_allowed
        required_ok = (not window.required) or bool(in_window)
        records_ok = all(record.passed for record in in_window)
        passed = required_ok and records_ok and not submitted_when_blocked
        checks.append(
            {
                "name": window.name,
                "passed": passed,
                "reason": "passed" if passed else _schedule_failure_reason(required_ok, records_ok, submitted_when_blocked),
                "records": len(window_records),
                "records_in_window": len(in_window),
                "required": window.required,
                "submit_orders_allowed": window.submit_orders_allowed,
            }
        )
    return PaperSessionScheduleReport(windows, records, tuple(checks))


def run_scheduled_paper_session(
    app: TradingApplication,
    options: AutonomousPaperSessionOptions | None = None,
    windows: Sequence[PaperSessionScheduleWindow] | None = None,
    now: datetime | None = None,
    schedule_output_path: str | Path | None = None,
    artifact_root: str | Path = "runs/paper-session-schedule",
) -> PaperSessionScheduleReport:
    options = options or AutonomousPaperSessionOptions()
    now = now or datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    windows = tuple(windows or default_paper_session_schedule_windows())
    local_now = now.astimezone(ZoneInfo("America/Chicago"))
    market_session = MarketSessionCalendar().session_at(now)
    active_window = None
    if market_session != MarketSession.CLOSED:
        active_window = next((window for window in windows if window.contains(local_now)), None)

    records: tuple[ScheduledPaperSessionRecord, ...] = ()
    if active_window is not None:
        session_artifact_root = Path(artifact_root) / f"{now.strftime('%Y%m%dT%H%M%SZ')}-{active_window.name}-paper-session"
        session_options = replace(
            options,
            submit_orders=bool(options.submit_orders and active_window.submit_orders_allowed),
            artifact_root=str(session_artifact_root),
        )
        result = run_autonomous_paper_session(app, session_options)
        records = (ScheduledPaperSessionRecord(active_window.name, now, result),)

    report = evaluate_active_paper_session_schedule(records, windows, active_window, schedule_output_path)
    return report


def evaluate_active_paper_session_schedule(
    records: Sequence[ScheduledPaperSessionRecord],
    windows: Sequence[PaperSessionScheduleWindow] | None = None,
    active_window: PaperSessionScheduleWindow | None = None,
    output_path: str | Path | None = None,
) -> PaperSessionScheduleReport:
    windows = tuple(windows or default_paper_session_schedule_windows())
    records = tuple(records)
    checks: list[Mapping] = []
    if active_window is None:
        checks.append({"name": "active_window", "passed": False, "reason": "no_active_paper_session_window"})
    else:
        active_records = tuple(record for record in records if record.window_name == active_window.name)
        submitted_when_blocked = any(record.submitted for record in active_records) and not active_window.submit_orders_allowed
        session_ok = (
            all(record.passed for record in active_records)
            if active_window.submit_orders_allowed
            else all(not record.submitted for record in active_records)
        )
        checks.extend(
            [
                {
                    "name": "active_window",
                    "passed": bool(active_records),
                    "reason": "passed" if active_records else "missing_active_window_record",
                    "window": active_window.name,
                    "records": len(active_records),
                },
                {
                    "name": "paper_session_result",
                    "passed": session_ok,
                    "reason": "passed" if session_ok else "scheduled_paper_session_failed",
                    "window": active_window.name,
                    "submit_orders_allowed": active_window.submit_orders_allowed,
                },
                {
                    "name": "blocked_window_no_submit",
                    "passed": not submitted_when_blocked,
                    "reason": "passed" if not submitted_when_blocked else "orders_submitted_in_blocked_window",
                    "window": active_window.name,
                },
            ]
        )
    report = PaperSessionScheduleReport(windows, records, tuple(checks), active_window=active_window.name if active_window else None)
    if output_path is None:
        return report
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return PaperSessionScheduleReport(report.windows, report.records, report.checks, report.active_window, artifact_path=str(path))


def _schedule_failure_reason(required_ok: bool, records_ok: bool, submitted_when_blocked: bool) -> str:
    if not required_ok:
        return "missing_required_window_record"
    if submitted_when_blocked:
        return "orders_submitted_in_blocked_window"
    if not records_ok:
        return "scheduled_session_failed"
    return "scheduled_session_unknown_failure"


def _result_payload(result: AutonomousPaperSessionResult | Mapping) -> dict:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return dict(result)
