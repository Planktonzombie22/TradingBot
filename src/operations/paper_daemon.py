from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
from typing import Callable, Mapping, Sequence

from src.app import TradingApplication

from .data_reliability import (
    WebsocketRestParityReport,
    build_websocket_rest_parity_report,
    write_websocket_rest_parity_report,
)
from .paper_cleanup import PaperCleanupOptions, PaperCleanupReport, run_paper_cleanup
from .paper_monitor import PaperMonitorReport, build_paper_monitor_report, write_paper_monitor_report
from .paper_session import AutonomousPaperSessionOptions
from .schedule import PaperSessionScheduleReport, run_scheduled_paper_session


@dataclass(frozen=True)
class PaperTradingDaemonOptions:
    interval_seconds: float = 300.0
    max_iterations: int | None = None
    kill_switch_path: str = "runs/paper-daemon.kill"
    state_path: str = "runs/paper-daemon-state.json"
    heartbeat_path: str = "runs/paper-daemon-heartbeat.json"
    lock_path: str = "runs/paper-daemon.lock"
    lock_stale_after_seconds: float = 1_800.0
    artifact_root: str = "runs/paper-daemon"
    schedule_output_path: str = "reports/paper-daemon-schedule.json"
    report_path: str = "reports/paper-daemon-report.json"
    cleanup_each_iteration: bool = False
    cleanup_submit_orders: bool = False
    cleanup_output_path: str = "reports/paper-daemon-cleanup.json"
    monitor_each_iteration: bool = False
    monitor_output_path: str = "reports/paper-daemon-monitor.json"
    monitor_max_open_order_age_minutes: float = 15.0
    data_parity_each_iteration: bool = False
    data_parity_output_path: str = "reports/paper-daemon-data-parity.json"
    data_parity_max_close_drift_bps: float = 5.0
    submit_orders: bool = False

    def __post_init__(self) -> None:
        if self.interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative.")
        if self.max_iterations is not None and self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive when supplied.")
        if self.lock_stale_after_seconds <= 0:
            raise ValueError("lock_stale_after_seconds must be positive.")
        if self.monitor_max_open_order_age_minutes <= 0:
            raise ValueError("monitor_max_open_order_age_minutes must be positive.")
        if self.data_parity_max_close_drift_bps <= 0:
            raise ValueError("data_parity_max_close_drift_bps must be positive.")

    def to_dict(self) -> dict:
        return {
            "interval_seconds": self.interval_seconds,
            "max_iterations": self.max_iterations,
            "kill_switch_path": self.kill_switch_path,
            "state_path": self.state_path,
            "heartbeat_path": self.heartbeat_path,
            "lock_path": self.lock_path,
            "lock_stale_after_seconds": self.lock_stale_after_seconds,
            "artifact_root": self.artifact_root,
            "schedule_output_path": self.schedule_output_path,
            "report_path": self.report_path,
            "cleanup_each_iteration": self.cleanup_each_iteration,
            "cleanup_submit_orders": self.cleanup_submit_orders,
            "cleanup_output_path": self.cleanup_output_path,
            "monitor_each_iteration": self.monitor_each_iteration,
            "monitor_output_path": self.monitor_output_path,
            "monitor_max_open_order_age_minutes": self.monitor_max_open_order_age_minutes,
            "data_parity_each_iteration": self.data_parity_each_iteration,
            "data_parity_output_path": self.data_parity_output_path,
            "data_parity_max_close_drift_bps": self.data_parity_max_close_drift_bps,
            "submit_orders": self.submit_orders,
        }


@dataclass(frozen=True)
class PaperTradingDaemonIteration:
    iteration: int
    started_at: datetime
    ended_at: datetime
    status: str
    reason: str
    active_window: str | None = None
    submitted: bool = False
    passed: bool = False
    artifact_paths: tuple[str, ...] = ()
    cleanup_artifact_path: str | None = None
    cleanup_reason: str | None = None
    cleanup_planned_orders: int = 0
    cleanup_submitted_orders: int = 0
    monitor_artifact_path: str | None = None
    monitor_passed: bool | None = None
    monitor_reason: str | None = None
    monitor_unexpected_symbols: tuple[str, ...] = ()
    monitor_missing_symbols: tuple[str, ...] = ()
    monitor_position_mismatches: int = 0
    monitor_stale_open_orders: int = 0
    monitor_observed_notional: float | None = None
    data_parity_artifact_path: str | None = None
    data_parity_passed: bool | None = None
    data_parity_reason: str | None = None
    data_parity_checks: int = 0
    data_parity_failed_checks: int = 0

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "status": self.status,
            "reason": self.reason,
            "active_window": self.active_window,
            "submitted": self.submitted,
            "passed": self.passed,
            "artifact_paths": list(self.artifact_paths),
            "cleanup_artifact_path": self.cleanup_artifact_path,
            "cleanup_reason": self.cleanup_reason,
            "cleanup_planned_orders": self.cleanup_planned_orders,
            "cleanup_submitted_orders": self.cleanup_submitted_orders,
            "monitor_artifact_path": self.monitor_artifact_path,
            "monitor_passed": self.monitor_passed,
            "monitor_reason": self.monitor_reason,
            "monitor_unexpected_symbols": list(self.monitor_unexpected_symbols),
            "monitor_missing_symbols": list(self.monitor_missing_symbols),
            "monitor_position_mismatches": self.monitor_position_mismatches,
            "monitor_stale_open_orders": self.monitor_stale_open_orders,
            "monitor_observed_notional": self.monitor_observed_notional,
            "data_parity_artifact_path": self.data_parity_artifact_path,
            "data_parity_passed": self.data_parity_passed,
            "data_parity_reason": self.data_parity_reason,
            "data_parity_checks": self.data_parity_checks,
            "data_parity_failed_checks": self.data_parity_failed_checks,
        }


@dataclass(frozen=True)
class PaperTradingDaemonState:
    status: str
    iteration: int
    last_heartbeat_at: datetime
    kill_switch_path: str
    state_path: str
    heartbeat_path: str
    lock_path: str = "runs/paper-daemon.lock"
    next_run_at: datetime | None = None
    last_reason: str = "initialized"
    last_error: str | None = None
    last_active_window: str | None = None

    @property
    def running(self) -> bool:
        return self.status == "running"

    @property
    def stopped(self) -> bool:
        return self.status in {"completed", "kill_switch_active", "lock_active", "stopped", "error"}

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "iteration": self.iteration,
            "last_heartbeat_at": self.last_heartbeat_at.isoformat(),
            "kill_switch_path": self.kill_switch_path,
            "state_path": self.state_path,
            "heartbeat_path": self.heartbeat_path,
            "lock_path": self.lock_path,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_reason": self.last_reason,
            "last_error": self.last_error,
            "last_active_window": self.last_active_window,
        }


@dataclass(frozen=True)
class PaperTradingDaemonReport:
    options: PaperTradingDaemonOptions
    state: PaperTradingDaemonState
    iterations: tuple[PaperTradingDaemonIteration, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return (
            self.state.status in {"completed", "kill_switch_active", "stopped"}
            and not self.state.last_error
            and all(iteration.passed for iteration in self.iterations)
        )

    @property
    def stopped_by_kill_switch(self) -> bool:
        return self.state.status == "kill_switch_active"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "stopped_by_kill_switch": self.stopped_by_kill_switch,
            "options": self.options.to_dict(),
            "state": self.state.to_dict(),
            "iterations": [iteration.to_dict() for iteration in self.iterations],
            "artifact_path": self.artifact_path,
        }


SessionRunner = Callable[..., PaperSessionScheduleReport]
CleanupRunner = Callable[..., PaperCleanupReport]
ParityRunner = Callable[..., WebsocketRestParityReport]
SleepFn = Callable[[float], None]
ClockFn = Callable[[], datetime]


def request_paper_daemon_stop(
    path: str | Path = "runs/paper-daemon.kill",
    *,
    reason: str = "operator_requested_stop",
    now: datetime | None = None,
) -> Path:
    stop_path = Path(path)
    stop_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now(now)
    stop_path.write_text(
        json.dumps({"requested_at": timestamp.isoformat(), "reason": reason}, indent=2),
        encoding="utf-8",
    )
    return stop_path


def clear_paper_daemon_stop(path: str | Path = "runs/paper-daemon.kill") -> bool:
    stop_path = Path(path)
    if not stop_path.exists():
        return False
    stop_path.unlink()
    return True


def load_paper_daemon_state(path: str | Path = "runs/paper-daemon-state.json") -> Mapping:
    state_path = Path(path)
    if not state_path.exists():
        return {
            "status": "missing",
            "state_path": str(state_path),
            "reason": "paper_daemon_state_missing",
        }
    return json.loads(state_path.read_text(encoding="utf-8"))


def run_paper_trading_daemon(
    app: TradingApplication,
    session_options: AutonomousPaperSessionOptions | None = None,
    daemon_options: PaperTradingDaemonOptions | None = None,
    *,
    session_runner: SessionRunner = run_scheduled_paper_session,
    cleanup_runner: CleanupRunner = run_paper_cleanup,
    parity_runner: ParityRunner | None = None,
    sleep_fn: SleepFn = time.sleep,
    clock: ClockFn | None = None,
) -> PaperTradingDaemonReport:
    daemon_options = daemon_options or PaperTradingDaemonOptions()
    session_options = session_options or AutonomousPaperSessionOptions()
    clock = clock or (lambda: datetime.now(timezone.utc))
    iterations: list[PaperTradingDaemonIteration] = []
    _validate_daemon_paths(daemon_options)
    lock = _acquire_lock(daemon_options, now=_utc_now(clock()))
    if not lock.acquired:
        state = _write_state(
            daemon_options,
            status="lock_active",
            iteration=0,
            now=_utc_now(clock()),
            reason=lock.reason,
        )
        return _write_report(daemon_options, state, iterations)

    try:
        if Path(daemon_options.kill_switch_path).exists():
            state = _write_state(
                daemon_options,
                status="kill_switch_active",
                iteration=0,
                now=_utc_now(clock()),
                reason="kill_switch_present_before_start",
            )
            return _write_report(daemon_options, state, iterations)

        state = _write_state(
            daemon_options,
            status="running",
            iteration=0,
            now=_utc_now(clock()),
            reason="daemon_started",
        )
        _write_heartbeat(daemon_options, state)

        while True:
            if Path(daemon_options.kill_switch_path).exists():
                state = _write_state(
                    daemon_options,
                    status="kill_switch_active",
                    iteration=len(iterations),
                    now=_utc_now(clock()),
                    reason="kill_switch_detected",
                    last_active_window=state.last_active_window,
                )
                return _write_report(daemon_options, state, iterations)

            iteration_number = len(iterations) + 1
            started_at = _utc_now(clock())
            schedule_output_path = _iteration_schedule_path(daemon_options, iteration_number, started_at)
            artifact_root = Path(daemon_options.artifact_root) / f"iteration-{iteration_number:04d}"
            active_session_options = replace(
                session_options,
                submit_orders=bool(daemon_options.submit_orders and session_options.submit_orders),
                artifact_root=str(artifact_root),
            )
            try:
                schedule_report = session_runner(
                    app,
                    active_session_options,
                    now=started_at,
                    schedule_output_path=schedule_output_path,
                    artifact_root=artifact_root,
                )
                ended_at = _utc_now(clock())
                cleanup_report = _run_iteration_cleanup(
                    app,
                    daemon_options,
                    active_session_options,
                    iteration_number,
                    artifact_root,
                    cleanup_runner=cleanup_runner,
                )
                ended_at = _utc_now(clock())
                monitor_report = _run_iteration_monitor(
                    daemon_options,
                    iteration_number,
                    artifact_root,
                    schedule_report,
                    cleanup_report,
                    now=ended_at,
                )
                data_parity_report = _run_iteration_data_parity(
                    app,
                    daemon_options,
                    iteration_number,
                    artifact_root,
                    schedule_report,
                    now=ended_at,
                    parity_runner=parity_runner,
                )
                iteration = _iteration_from_schedule(
                    iteration_number,
                    started_at,
                    ended_at,
                    schedule_report,
                    cleanup_report=cleanup_report,
                    monitor_report=monitor_report,
                    data_parity_report=data_parity_report,
                )
                iterations.append(iteration)
                state = _write_state(
                    daemon_options,
                    status="running",
                    iteration=iteration_number,
                    now=ended_at,
                    reason=iteration.reason,
                    next_run_at=ended_at + timedelta(seconds=daemon_options.interval_seconds),
                    last_active_window=iteration.active_window,
                )
                _write_heartbeat(daemon_options, state)
            except Exception as exc:
                state = _write_state(
                    daemon_options,
                    status="error",
                    iteration=iteration_number,
                    now=_utc_now(clock()),
                    reason="paper_daemon_iteration_error",
                    last_error=str(exc),
                )
                return _write_report(daemon_options, state, iterations)

            if daemon_options.max_iterations is not None and iteration_number >= daemon_options.max_iterations:
                state = _write_state(
                    daemon_options,
                    status="completed",
                    iteration=iteration_number,
                    now=_utc_now(clock()),
                    reason="max_iterations_completed",
                    last_active_window=state.last_active_window,
                )
                return _write_report(daemon_options, state, iterations)

            if Path(daemon_options.kill_switch_path).exists():
                state = _write_state(
                    daemon_options,
                    status="kill_switch_active",
                    iteration=iteration_number,
                    now=_utc_now(clock()),
                    reason="kill_switch_detected_after_iteration",
                    last_active_window=state.last_active_window,
                )
                return _write_report(daemon_options, state, iterations)

            sleep_fn(daemon_options.interval_seconds)
    finally:
        _release_lock(lock)


@dataclass(frozen=True)
class _DaemonLock:
    path: Path
    token: str
    acquired: bool
    reason: str = "lock_acquired"


def _iteration_from_schedule(
    iteration_number: int,
    started_at: datetime,
    ended_at: datetime,
    schedule_report: PaperSessionScheduleReport,
    *,
    cleanup_report: PaperCleanupReport | None = None,
    monitor_report: PaperMonitorReport | None = None,
    data_parity_report: WebsocketRestParityReport | None = None,
) -> PaperTradingDaemonIteration:
    submitted = any(record.submitted for record in schedule_report.records)
    cleanup_artifact_paths = (cleanup_report.artifact_path,) if cleanup_report and cleanup_report.artifact_path else ()
    monitor_artifact_paths = (monitor_report.artifact_path,) if monitor_report and monitor_report.artifact_path else ()
    data_parity_artifact_paths = (
        (data_parity_report.artifact_path,) if data_parity_report and data_parity_report.artifact_path else ()
    )
    artifact_paths = tuple(
        path
        for path in (
            schedule_report.artifact_path,
            *(_record_artifact_paths(schedule_report.records)),
            *cleanup_artifact_paths,
            *monitor_artifact_paths,
            *data_parity_artifact_paths,
        )
        if path
    )
    reason = "passed" if schedule_report.passed else _schedule_reason(schedule_report)
    skipped = schedule_report.active_window is None and reason == "no_active_paper_session_window"
    cleanup_passed = _cleanup_passed(cleanup_report)
    monitor_passed = _monitor_passed(monitor_report)
    data_parity_passed = _data_parity_passed(data_parity_report)
    return PaperTradingDaemonIteration(
        iteration=iteration_number,
        started_at=started_at,
        ended_at=ended_at,
        status="skipped" if skipped else "completed",
        reason=reason,
        active_window=schedule_report.active_window,
        submitted=submitted,
        passed=bool((schedule_report.passed or skipped) and cleanup_passed and monitor_passed and data_parity_passed),
        artifact_paths=artifact_paths,
        cleanup_artifact_path=cleanup_report.artifact_path if cleanup_report else None,
        cleanup_reason=cleanup_report.reason if cleanup_report else None,
        cleanup_planned_orders=len(cleanup_report.planned_orders) if cleanup_report else 0,
        cleanup_submitted_orders=len(cleanup_report.submitted_orders) if cleanup_report else 0,
        monitor_artifact_path=monitor_report.artifact_path if monitor_report else None,
        monitor_passed=monitor_report.passed if monitor_report else None,
        monitor_reason=monitor_report.reason if monitor_report else None,
        monitor_unexpected_symbols=monitor_report.unexpected_symbols if monitor_report else (),
        monitor_missing_symbols=monitor_report.missing_symbols if monitor_report else (),
        monitor_position_mismatches=sum(1 for match in monitor_report.matches if not match.matched) if monitor_report else 0,
        monitor_stale_open_orders=monitor_report.open_orders.stale_orders if monitor_report and monitor_report.open_orders else 0,
        monitor_observed_notional=monitor_report.observed_notional if monitor_report else None,
        data_parity_artifact_path=data_parity_report.artifact_path if data_parity_report else None,
        data_parity_passed=data_parity_report.passed if data_parity_report else None,
        data_parity_reason=data_parity_report.reason if data_parity_report else None,
        data_parity_checks=len(data_parity_report.checks) if data_parity_report else 0,
        data_parity_failed_checks=sum(1 for check in data_parity_report.checks if not check.passed)
        if data_parity_report
        else 0,
    )


def _run_iteration_cleanup(
    app: TradingApplication,
    daemon_options: PaperTradingDaemonOptions,
    session_options: AutonomousPaperSessionOptions,
    iteration_number: int,
    artifact_root: Path,
    *,
    cleanup_runner: CleanupRunner,
) -> PaperCleanupReport | None:
    if not (daemon_options.cleanup_each_iteration or daemon_options.monitor_each_iteration):
        return None
    cleanup_path = _iteration_cleanup_path(daemon_options, iteration_number, artifact_root)
    return cleanup_runner(
        app,
        PaperCleanupOptions(
            submit_orders=bool(daemon_options.cleanup_submit_orders),
            artifact_path=str(cleanup_path),
            approval_options=session_options,
        ),
    )


def _run_iteration_monitor(
    daemon_options: PaperTradingDaemonOptions,
    iteration_number: int,
    artifact_root: Path,
    schedule_report: PaperSessionScheduleReport,
    cleanup_report: PaperCleanupReport | None,
    *,
    now: datetime,
) -> PaperMonitorReport | None:
    if not daemon_options.monitor_each_iteration or cleanup_report is None:
        return None
    monitor_report = build_paper_monitor_report(
        _monitor_portfolio_payload(schedule_report),
        cleanup_report.to_dict(),
        open_order_snapshot={},
        max_open_order_age_minutes=daemon_options.monitor_max_open_order_age_minutes,
        now=now,
    )
    output_path = _iteration_monitor_path(daemon_options, iteration_number, artifact_root)
    artifact_path = write_paper_monitor_report(monitor_report, output_path)
    return replace(monitor_report, artifact_path=artifact_path)


def _run_iteration_data_parity(
    app: TradingApplication,
    daemon_options: PaperTradingDaemonOptions,
    iteration_number: int,
    artifact_root: Path,
    schedule_report: PaperSessionScheduleReport,
    *,
    now: datetime,
    parity_runner: ParityRunner | None,
) -> WebsocketRestParityReport | None:
    if not daemon_options.data_parity_each_iteration:
        return None
    runner = parity_runner or _default_iteration_parity_runner
    parity_report = runner(
        app,
        daemon_options,
        schedule_report=schedule_report,
        now=now,
    )
    output_path = _iteration_data_parity_path(daemon_options, iteration_number, artifact_root)
    artifact_path = write_websocket_rest_parity_report(parity_report, output_path)
    return replace(parity_report, artifact_path=artifact_path)


def _cleanup_passed(cleanup_report: PaperCleanupReport | None) -> bool:
    if cleanup_report is None:
        return True
    if cleanup_report.reason not in {"preview_only", "no_positions_to_flatten", "flatten_orders_submitted"}:
        return False
    if cleanup_report.submit_requested and cleanup_report.reconciliation_clean is False:
        return False
    return True


def _monitor_passed(monitor_report: PaperMonitorReport | None) -> bool:
    return True if monitor_report is None else monitor_report.passed


def _data_parity_passed(data_parity_report: WebsocketRestParityReport | None) -> bool:
    return True if data_parity_report is None else data_parity_report.passed


def _default_iteration_parity_runner(
    app: TradingApplication,
    daemon_options: PaperTradingDaemonOptions,
    *,
    schedule_report: PaperSessionScheduleReport,
    now: datetime,
) -> WebsocketRestParityReport:
    parity_payload = _embedded_data_parity_payload(schedule_report)
    if parity_payload:
        streamed_bars = parity_payload.get("streamed_bars") or parity_payload.get("websocket_bars") or ()
        rest_bars = parity_payload.get("rest_bars") or ()
        return build_websocket_rest_parity_report(
            _mapping_sequence(streamed_bars),
            _mapping_sequence(rest_bars),
            max_close_drift_bps=daemon_options.data_parity_max_close_drift_bps,
        )

    bars = _latest_price_parity_bars(schedule_report, now)
    return build_websocket_rest_parity_report(
        bars,
        bars,
        max_close_drift_bps=daemon_options.data_parity_max_close_drift_bps,
    )


def _embedded_data_parity_payload(schedule_report: PaperSessionScheduleReport) -> Mapping | None:
    for record in schedule_report.records:
        result = record.to_dict().get("result") or {}
        if not isinstance(result, Mapping):
            continue
        for key in ("data_parity", "websocket_rest_parity"):
            payload = result.get(key)
            if isinstance(payload, Mapping):
                return payload
    return None


def _latest_price_parity_bars(schedule_report: PaperSessionScheduleReport, now: datetime) -> tuple[Mapping, ...]:
    bars: list[Mapping] = []
    timestamp = now.isoformat()
    for record in schedule_report.records:
        result = record.to_dict().get("result") or {}
        if not isinstance(result, Mapping):
            continue
        latest_prices = result.get("latest_prices")
        if not isinstance(latest_prices, Mapping):
            latest_prices = _latest_prices_from_candidates(result)
        for symbol, price in latest_prices.items():
            if price in {None, ""}:
                continue
            bars.append({"symbol": str(symbol).upper(), "timestamp": timestamp, "close": float(price)})
    return tuple(bars)


def _latest_prices_from_candidates(result: Mapping) -> Mapping:
    prices: dict[str, float] = {}
    for key in ("candidates", "candidate_results", "portfolio_candidates"):
        candidates = result.get(key)
        if not isinstance(candidates, Sequence) or isinstance(candidates, str):
            continue
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            symbol = str(candidate.get("symbol") or "").upper()
            price = candidate.get("latest_price") or candidate.get("close") or candidate.get("price")
            if symbol and price not in {None, ""}:
                prices[symbol] = float(price)
    return prices


def _mapping_sequence(value: object) -> tuple[Mapping, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _monitor_portfolio_payload(schedule_report: PaperSessionScheduleReport) -> Mapping:
    submitted_orders: list[Mapping] = []
    max_notional = None
    for record in schedule_report.records:
        result = record.to_dict().get("result") or {}
        if not isinstance(result, Mapping):
            continue
        result = _hydrated_session_result(result)
        submission = result.get("submission") if isinstance(result.get("submission"), Mapping) else {}
        submitted_orders.extend(_submitted_order_payloads(result, submission))
        max_notional = max_notional if max_notional is not None else _monitor_notional_budget(result, submission)
    return {
        "submission": {
            "submitted_orders": submitted_orders,
            "notional_budget": {"max_notional": max_notional} if max_notional is not None else {},
        }
    }


def _hydrated_session_result(result: Mapping) -> Mapping:
    report_path = result.get("report_path")
    if not report_path:
        return result
    path = Path(str(report_path))
    if not path.exists():
        return result
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return result
    return payload if isinstance(payload, Mapping) else result


def _submitted_order_payloads(result: Mapping, submission: Mapping) -> tuple[Mapping, ...]:
    for key in ("submitted_orders", "open_orders", "orders"):
        orders = submission.get(key)
        if isinstance(orders, Sequence) and not isinstance(orders, str):
            return tuple(order for order in orders if isinstance(order, Mapping))
    orders = result.get("submitted_orders")
    if isinstance(orders, Sequence) and not isinstance(orders, str):
        return tuple(order for order in orders if isinstance(order, Mapping))
    planned_orders = result.get("planned_orders")
    if bool(result.get("submitted")) and isinstance(planned_orders, Sequence) and not isinstance(planned_orders, str):
        return tuple(order for order in planned_orders if isinstance(order, Mapping))
    return ()


def _monitor_notional_budget(result: Mapping, submission: Mapping) -> float | None:
    budget = submission.get("notional_budget")
    if isinstance(budget, Mapping) and budget.get("max_notional") is not None:
        return float(budget["max_notional"])
    risk_budget = result.get("risk_budget")
    if isinstance(risk_budget, Mapping):
        budget_payload = risk_budget.get("budget")
        if isinstance(budget_payload, Mapping) and budget_payload.get("max_session_notional") is not None:
            return float(budget_payload["max_session_notional"])
    return None


def _record_artifact_paths(records: Sequence) -> tuple[str, ...]:
    paths: list[str] = []
    for record in records:
        result = getattr(record, "result", None)
        report_path = getattr(result, "report_path", None)
        if report_path:
            paths.append(str(report_path))
    return tuple(paths)


def _schedule_reason(schedule_report: PaperSessionScheduleReport) -> str:
    for check in schedule_report.checks:
        if not bool(check.get("passed")):
            return str(check.get("reason", "paper_session_schedule_failed"))
    return "paper_session_schedule_failed"


def _write_state(
    options: PaperTradingDaemonOptions,
    *,
    status: str,
    iteration: int,
    now: datetime,
    reason: str,
    next_run_at: datetime | None = None,
    last_error: str | None = None,
    last_active_window: str | None = None,
) -> PaperTradingDaemonState:
    state = PaperTradingDaemonState(
        status=status,
        iteration=iteration,
        last_heartbeat_at=now,
        kill_switch_path=options.kill_switch_path,
        state_path=options.state_path,
        heartbeat_path=options.heartbeat_path,
        lock_path=options.lock_path,
        next_run_at=next_run_at,
        last_reason=reason,
        last_error=last_error,
        last_active_window=last_active_window,
    )
    state_path = Path(options.state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    return state


def _write_heartbeat(options: PaperTradingDaemonOptions, state: PaperTradingDaemonState) -> None:
    heartbeat_path = Path(options.heartbeat_path)
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def _write_report(
    options: PaperTradingDaemonOptions,
    state: PaperTradingDaemonState,
    iterations: Sequence[PaperTradingDaemonIteration],
) -> PaperTradingDaemonReport:
    report = PaperTradingDaemonReport(options, state, tuple(iterations), artifact_path=options.report_path)
    path = Path(options.report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report


def _acquire_lock(options: PaperTradingDaemonOptions, *, now: datetime) -> _DaemonLock:
    path = Path(options.lock_path)
    token = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{id(options)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "token": token,
        "acquired_at": now.isoformat(),
        "state_path": options.state_path,
        "heartbeat_path": options.heartbeat_path,
    }
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2))
        return _DaemonLock(path=path, token=token, acquired=True)
    except FileExistsError:
        existing = _load_lock_payload(path)
        age_seconds = _lock_age_seconds(existing, now)
        if age_seconds is not None and age_seconds > options.lock_stale_after_seconds:
            path.write_text(json.dumps({**payload, "replaced_stale_lock": existing}, indent=2), encoding="utf-8")
            return _DaemonLock(path=path, token=token, acquired=True, reason="stale_lock_replaced")
        return _DaemonLock(path=path, token=token, acquired=False, reason="paper_daemon_lock_active")


def _release_lock(lock: _DaemonLock) -> None:
    if not lock.acquired or not lock.path.exists():
        return
    payload = _load_lock_payload(lock.path)
    if str(payload.get("token") or "") != lock.token:
        return
    lock.path.unlink()


def _load_lock_payload(path: Path) -> Mapping:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _lock_age_seconds(payload: Mapping, now: datetime) -> float | None:
    acquired_at = payload.get("acquired_at")
    if not acquired_at:
        return None
    try:
        timestamp = datetime.fromisoformat(str(acquired_at))
    except ValueError:
        return None
    return max(0.0, (now - _utc_now(timestamp)).total_seconds())


def _iteration_schedule_path(options: PaperTradingDaemonOptions, iteration: int, now: datetime) -> Path:
    configured = Path(options.schedule_output_path)
    if configured.suffix:
        return configured.with_name(f"{configured.stem}-{now.strftime('%Y%m%dT%H%M%SZ')}-{iteration:04d}{configured.suffix}")
    return configured / f"paper-daemon-schedule-{now.strftime('%Y%m%dT%H%M%SZ')}-{iteration:04d}.json"


def _iteration_cleanup_path(options: PaperTradingDaemonOptions, iteration: int, artifact_root: Path) -> Path:
    configured = Path(options.cleanup_output_path)
    if configured.suffix:
        return configured.with_name(f"{configured.stem}-{iteration:04d}{configured.suffix}")
    return artifact_root / "paper-daemon-cleanup.json"


def _iteration_monitor_path(options: PaperTradingDaemonOptions, iteration: int, artifact_root: Path) -> Path:
    configured = Path(options.monitor_output_path)
    if configured.suffix:
        return configured.with_name(f"{configured.stem}-{iteration:04d}{configured.suffix}")
    return artifact_root / "paper-daemon-monitor.json"


def _iteration_data_parity_path(options: PaperTradingDaemonOptions, iteration: int, artifact_root: Path) -> Path:
    configured = Path(options.data_parity_output_path)
    if configured.suffix:
        return configured.with_name(f"{configured.stem}-{iteration:04d}{configured.suffix}")
    return artifact_root / "paper-daemon-data-parity.json"


def _validate_daemon_paths(options: PaperTradingDaemonOptions) -> None:
    state_path = Path(options.state_path)
    heartbeat_path = Path(options.heartbeat_path)
    kill_switch_path = Path(options.kill_switch_path)
    lock_path = Path(options.lock_path)
    report_path = Path(options.report_path)
    monitor_path = Path(options.monitor_output_path)
    data_parity_path = Path(options.data_parity_output_path)
    if state_path == kill_switch_path:
        raise ValueError("state_path and kill_switch_path must be different.")
    if heartbeat_path == kill_switch_path:
        raise ValueError("heartbeat_path and kill_switch_path must be different.")
    if lock_path in {state_path, heartbeat_path, kill_switch_path}:
        raise ValueError("lock_path must be different from daemon state, heartbeat, and kill-switch paths.")
    if report_path in {state_path, heartbeat_path, kill_switch_path, lock_path}:
        raise ValueError("report_path must be different from daemon state, heartbeat, lock, and kill-switch paths.")
    if monitor_path in {state_path, heartbeat_path, kill_switch_path, lock_path, report_path}:
        raise ValueError("monitor_output_path must be different from daemon state, heartbeat, lock, report, and kill-switch paths.")
    if data_parity_path in {state_path, heartbeat_path, kill_switch_path, lock_path, report_path, monitor_path}:
        raise ValueError(
            "data_parity_output_path must be different from daemon state, heartbeat, lock, report, monitor, and kill-switch paths."
        )


def _utc_now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
