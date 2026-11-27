from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timezone
from pathlib import Path
import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Iterable
from zoneinfo import ZoneInfo

from src.app import TradingApplication
from src.config import load_runtime_config
from src.data import MarketSession, MarketSessionCalendar
from src.operations import clear_paper_daemon_stop, load_paper_daemon_state, request_paper_daemon_stop
from src.reporting import format_backtest_summary


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class GuiCommandConfig:
    mode: str
    provider: str = "sample"
    symbol: str = "SPY"
    strategy: str = "buyHold"
    execution_mode: str = "dry-run"
    paper_profile: str = ""
    submit_orders: bool = False
    daemon_interval_seconds: float = 300.0
    daemon_max_iterations: int | None = None
    output_path: str = ""
    store_dir: str = "runs/gui"
    daemon_state_path: str = "runs/paper-daemon-state.json"
    daemon_heartbeat_path: str = "runs/paper-daemon-heartbeat.json"
    daemon_kill_switch_path: str = "runs/paper-daemon.kill"
    daemon_lock_path: str = "runs/paper-daemon.lock"
    daemon_lock_stale_seconds: float = 1_800.0
    validation_profile: str = "smoke"
    validation_output_path: str = "reports/gui-validation-smoke.json"


@dataclass(frozen=True)
class GuiProfilePreset:
    name: str
    provider: str
    execution_mode: str
    paper_profile: str = ""
    submit_orders: bool = False
    daemon_interval_seconds: float = 300.0
    daemon_max_iterations: int | None = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "provider": self.provider,
            "execution_mode": self.execution_mode,
            "paper_profile": self.paper_profile,
            "submit_orders": self.submit_orders,
            "daemon_interval_seconds": self.daemon_interval_seconds,
            "daemon_max_iterations": self.daemon_max_iterations,
            "description": self.description,
        }


def gui_profile_presets() -> tuple[GuiProfilePreset, ...]:
    return (
        GuiProfilePreset(
            name="Sample dry-run",
            provider="sample",
            execution_mode="dry-run",
            paper_profile="",
            submit_orders=False,
            daemon_interval_seconds=0,
            daemon_max_iterations=1,
            description="Deterministic local preview with no broker routing.",
        ),
        GuiProfilePreset(
            name="Alpaca data-only",
            provider="alpaca",
            execution_mode="dry-run",
            paper_profile="dry-run",
            submit_orders=False,
            daemon_interval_seconds=300,
            daemon_max_iterations=None,
            description="Live Alpaca data with paper submission disabled.",
        ),
        GuiProfilePreset(
            name="Micro paper",
            provider="alpaca",
            execution_mode="paper",
            paper_profile="micro-notional",
            submit_orders=True,
            daemon_interval_seconds=300,
            daemon_max_iterations=None,
            description="Tiny guarded Alpaca paper profile requiring submit confirmation.",
        ),
        GuiProfilePreset(
            name="Full paper rehearsal",
            provider="alpaca",
            execution_mode="paper",
            paper_profile="full-paper-rehearsal",
            submit_orders=True,
            daemon_interval_seconds=300,
            daemon_max_iterations=None,
            description="Full guarded paper rehearsal profile requiring submit confirmation.",
        ),
    )


def apply_gui_profile_preset(config: GuiCommandConfig, preset_name: str) -> GuiCommandConfig:
    presets = {preset.name: preset for preset in gui_profile_presets()}
    if preset_name not in presets:
        raise ValueError(f"Unknown GUI profile preset: {preset_name}")
    preset = presets[preset_name]
    return replace(
        config,
        provider=preset.provider,
        execution_mode=preset.execution_mode,
        paper_profile=preset.paper_profile,
        submit_orders=preset.submit_orders,
        daemon_interval_seconds=preset.daemon_interval_seconds,
        daemon_max_iterations=preset.daemon_max_iterations,
    )


@dataclass(frozen=True)
class GuiDaemonStatus:
    status: str
    heartbeat_state: str
    kill_switch_active: bool
    iteration: int = 0
    heartbeat_age_seconds: float | None = None
    last_heartbeat_at: str | None = None
    next_run_at: str | None = None
    last_reason: str | None = None
    last_active_window: str | None = None
    state_path: str = "runs/paper-daemon-state.json"

    def card_lines(self) -> tuple[str, ...]:
        age = "n/a" if self.heartbeat_age_seconds is None else f"{self.heartbeat_age_seconds:.0f}s"
        return (
            f"Daemon: {self.status}",
            f"Heartbeat: {self.heartbeat_state} ({age})",
            f"Kill switch: {'active' if self.kill_switch_active else 'clear'}",
            f"Iteration: {self.iteration}",
            f"Window: {self.last_active_window or 'none'}",
            f"Reason: {self.last_reason or 'n/a'}",
        )


@dataclass(frozen=True)
class GuiDashboardSummary:
    monitor_status: str = "missing"
    monitor_reason: str = "paper_monitor_missing"
    observed_positions: int = 0
    observed_notional: float | None = None
    open_orders: int = 0
    stale_open_orders: int = 0
    total_unrealized_pnl: float | None = None
    total_market_value: float | None = None
    drawdown_pct: float | None = None
    mark_to_market_equity: float | None = None
    fills_seen: int = 0
    latest_fill: str | None = None
    artifacts_present: tuple[str, ...] = ()
    artifacts_missing: tuple[str, ...] = ()

    def card_lines(self) -> tuple[str, ...]:
        return (
            f"Monitor: {self.monitor_status} ({self.monitor_reason})",
            f"Positions: {self.observed_positions} notional={_format_money(self.observed_notional)}",
            f"Open orders: {self.open_orders} stale={self.stale_open_orders}",
            f"PnL: {_format_money(self.total_unrealized_pnl)} market value={_format_money(self.total_market_value)}",
            f"Drawdown: {_format_pct(self.drawdown_pct)} equity={_format_money(self.mark_to_market_equity)}",
            f"Fills: {self.fills_seen} latest={self.latest_fill or 'none'}",
        )


@dataclass(frozen=True)
class GuiResearchSummary:
    strategy_rows: int = 0
    top_strategy: str | None = None
    top_metric: str | None = None
    benchmark_rows: int = 0
    benchmark_leaders: int = 0
    promotion_candidates: int = 0
    promotion_enabled: int = 0
    artifacts_present: tuple[str, ...] = ()
    artifacts_missing: tuple[str, ...] = ()

    def card_lines(self) -> tuple[str, ...]:
        return (
            f"Research rows: {self.strategy_rows}",
            f"Top strategy: {self.top_strategy or 'n/a'}",
            f"Top metric: {self.top_metric or 'n/a'}",
            f"Benchmark rows: {self.benchmark_rows} leaders={self.benchmark_leaders}",
            f"Promotions: {self.promotion_enabled}/{self.promotion_candidates}",
        )


@dataclass(frozen=True)
class GuiSoakReadinessSummary:
    readiness_status: str = "missing"
    clean_activations: int = 0
    submitted_activations: int = 0
    required_clean_activations: int = 0
    active_windows: tuple[str, ...] = ()
    required_active_windows: int = 0
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    recommended_action: str = "paper_daemon_soak_rollup_missing"
    monitor_status: str = "missing"
    data_parity_status: str = "missing"
    flatten_status: str = "missing"
    stewardship_status: str = "missing"
    observed_notional: float | None = None
    closed_symbols: tuple[str, ...] = ()
    next_capture_window: str | None = None
    next_capture_range: str | None = None
    next_capture_state: str = "none"
    next_capture_market_session: str = "unknown"
    minutes_until_capture_start: float | None = None
    minutes_until_capture_end: float | None = None
    missing_capture_windows: tuple[str, ...] = ()
    next_capture_command: tuple[str, ...] = ()
    artifacts_present: tuple[str, ...] = ()
    artifacts_missing: tuple[str, ...] = ()

    @property
    def ready_for_autonomous_paper(self) -> bool:
        return self.readiness_status == "ready"

    def card_lines(self) -> tuple[str, ...]:
        windows = ", ".join(self.active_windows) if self.active_windows else "none"
        blockers = ", ".join(self.blockers[:2]) if self.blockers else "none"
        timing = _capture_timing_label(
            self.next_capture_state,
            self.minutes_until_capture_start,
            self.minutes_until_capture_end,
        )
        timing_suffix = f" {timing}" if timing else ""
        session = self.next_capture_market_session.lower()
        return (
            f"Autonomy: {self.readiness_status}",
            f"Soak: {self.clean_activations}/{self.required_clean_activations} clean, {self.submitted_activations} submitted",
            f"Windows: {len(self.active_windows)}/{self.required_active_windows} ({windows})",
            f"Ops: monitor={self.monitor_status} parity={self.data_parity_status}",
            f"Closeout: flatten={self.flatten_status} steward={self.stewardship_status}",
            f"Exposure: {_format_money(self.observed_notional)} closed={', '.join(self.closed_symbols) or 'none'}",
            f"Capture: next={self.next_capture_window or 'none'} missing={', '.join(self.missing_capture_windows) or 'none'}",
            f"Capture window: {self.next_capture_range or 'n/a'} state={self.next_capture_state} session={session}{timing_suffix}",
            f"Blockers: {blockers}",
            f"Next: {self.recommended_action}",
        )


@dataclass(frozen=True)
class GuiNextCaptureDecision:
    can_run: bool
    reason: str
    command: tuple[str, ...] = ()
    window: str | None = None
    state: str = "none"

    @property
    def submit_requested(self) -> bool:
        return "--submit-orders" in self.command


@dataclass(frozen=True)
class GuiOperatorSnapshot:
    daemon: GuiDaemonStatus
    dashboard: GuiDashboardSummary
    soak: GuiSoakReadinessSummary
    research: GuiResearchSummary
    next_capture: GuiNextCaptureDecision

    @property
    def status(self) -> str:
        if self.daemon.kill_switch_active:
            return "stopped"
        if self.daemon.heartbeat_state == "stale":
            return "daemon-stale"
        if self.next_capture.can_run:
            return "capture-ready"
        if self.soak.ready_for_autonomous_paper:
            return "autonomy-ready"
        if self.dashboard.monitor_status == "blocked":
            return "monitor-blocked"
        return "operator-review"

    @property
    def reason(self) -> str:
        if self.daemon.kill_switch_active:
            return "kill_switch_active"
        if self.daemon.heartbeat_state == "stale":
            return "daemon_heartbeat_stale"
        if self.next_capture.can_run:
            return "next_capture_window_ready"
        if self.soak.ready_for_autonomous_paper:
            return "soak_readiness_ready"
        if self.dashboard.monitor_status == "blocked":
            return self.dashboard.monitor_reason
        return self.soak.recommended_action

    def card_lines(self) -> tuple[str, ...]:
        return (
            f"Operator: {self.status} ({self.reason})",
            f"Daemon: {self.daemon.status} heartbeat={self.daemon.heartbeat_state} kill={'active' if self.daemon.kill_switch_active else 'clear'}",
            f"Autonomy: {self.soak.readiness_status} clean={self.soak.clean_activations}/{self.soak.required_clean_activations}",
            f"Capture: {self.next_capture.window or 'none'} state={self.next_capture.state} can_run={self.next_capture.can_run}",
            f"Paper: monitor={self.dashboard.monitor_status} positions={self.dashboard.observed_positions} notional={_format_money(self.dashboard.observed_notional)}",
            f"Research: rows={self.research.strategy_rows} promotions={self.research.promotion_enabled}/{self.research.promotion_candidates}",
        )

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "daemon": {
                "status": self.daemon.status,
                "heartbeat_state": self.daemon.heartbeat_state,
                "kill_switch_active": self.daemon.kill_switch_active,
                "iteration": self.daemon.iteration,
                "last_active_window": self.daemon.last_active_window,
            },
            "autonomy": {
                "readiness_status": self.soak.readiness_status,
                "clean_activations": self.soak.clean_activations,
                "required_clean_activations": self.soak.required_clean_activations,
                "active_windows": list(self.soak.active_windows),
                "recommended_action": self.soak.recommended_action,
            },
            "next_capture": {
                "can_run": self.next_capture.can_run,
                "reason": self.next_capture.reason,
                "window": self.next_capture.window,
                "state": self.next_capture.state,
                "submit_requested": self.next_capture.submit_requested,
            },
            "dashboard": {
                "monitor_status": self.dashboard.monitor_status,
                "monitor_reason": self.dashboard.monitor_reason,
                "observed_positions": self.dashboard.observed_positions,
                "observed_notional": self.dashboard.observed_notional,
                "open_orders": self.dashboard.open_orders,
                "stale_open_orders": self.dashboard.stale_open_orders,
            },
            "research": {
                "strategy_rows": self.research.strategy_rows,
                "top_strategy": self.research.top_strategy,
                "promotion_candidates": self.research.promotion_candidates,
                "promotion_enabled": self.research.promotion_enabled,
            },
        }


@dataclass(frozen=True)
class GuiAutonomousReadinessReport:
    status: str
    reason: str
    readiness_pct: float
    blockers: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    snapshot: GuiOperatorSnapshot | None = None

    @property
    def ready_for_unattended_paper(self) -> bool:
        return self.status == "autonomous-ready"

    @property
    def ready_for_operator_managed_paper(self) -> bool:
        return self.status in {"operator-managed-ready", "autonomous-ready"}

    def card_lines(self) -> tuple[str, ...]:
        blockers = ", ".join(self.blockers[:3]) if self.blockers else "none"
        next_steps = ", ".join(self.next_steps[:3]) if self.next_steps else "none"
        return (
            f"Autonomous readiness: {self.status} ({self.reason})",
            f"Progress: {self.readiness_pct:.0%}",
            f"Operator-managed paper: {'ready' if self.ready_for_operator_managed_paper else 'blocked'}",
            f"Unattended paper: {'ready' if self.ready_for_unattended_paper else 'blocked'}",
            f"Blockers: {blockers}",
            f"Next steps: {next_steps}",
        )

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "readiness_pct": self.readiness_pct,
            "ready_for_operator_managed_paper": self.ready_for_operator_managed_paper,
            "ready_for_unattended_paper": self.ready_for_unattended_paper,
            "blockers": list(self.blockers),
            "next_steps": list(self.next_steps),
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
        }


def build_gui_research_summary(
    *,
    bulk_path: str | Path = "reports/bulk-backtest-summary.json",
    benchmark_path: str | Path = "reports/benchmark-relative-summary.json",
    promotion_path: str | Path = "reports/paper-candidates.json",
) -> GuiResearchSummary:
    present: list[str] = []
    missing: list[str] = []
    bulk = _load_json_artifact(bulk_path, present, missing, "bulk")
    benchmark = _load_json_artifact(benchmark_path, present, missing, "benchmark")
    promotion = _load_json_artifact(promotion_path, present, missing, "promotion")
    strategy_rows = _summary_rows(bulk, ("strategy_summary", "summary", "rows", "records"))
    benchmark_rows = _summary_rows(benchmark, ("strategy_summary", "selection", "rows", "records"))
    promotion_candidates, promotion_enabled = _promotion_counts(promotion)
    top = _top_strategy_row(bulk)
    return GuiResearchSummary(
        strategy_rows=len(strategy_rows),
        top_strategy=_strategy_label(top),
        top_metric=_metric_label(top),
        benchmark_rows=len(benchmark_rows),
        benchmark_leaders=sum(1 for row in benchmark_rows if _row_selected(row)),
        promotion_candidates=promotion_candidates,
        promotion_enabled=promotion_enabled,
        artifacts_present=tuple(present),
        artifacts_missing=tuple(missing),
    )


def build_gui_autonomous_readiness_report(
    snapshot: GuiOperatorSnapshot | None = None,
) -> GuiAutonomousReadinessReport:
    observed = snapshot or build_gui_operator_snapshot()
    blockers: list[str] = []
    next_steps: list[str] = []
    score = 0.0

    if observed.daemon.kill_switch_active:
        blockers.append("kill_switch_active")
        next_steps.append("clear_kill_switch_when_ready")
    else:
        score += 0.15

    if observed.daemon.heartbeat_state == "fresh":
        score += 0.15
    elif observed.daemon.heartbeat_state == "stale":
        blockers.append("daemon_heartbeat_stale")
        next_steps.append("restart_or_inspect_paper_daemon")
    else:
        next_steps.append("start_or_refresh_paper_daemon")

    if observed.dashboard.monitor_status == "passed":
        score += 0.15
    elif observed.dashboard.monitor_status == "blocked":
        blockers.append(observed.dashboard.monitor_reason)
        next_steps.append("resolve_paper_monitor_blocker")
    else:
        next_steps.append("run_paper_monitor")

    if observed.dashboard.stale_open_orders:
        blockers.append("stale_open_orders_present")
        next_steps.append("cancel_or_reconcile_stale_open_orders")
    if observed.dashboard.observed_positions and observed.soak.readiness_status != "ready":
        blockers.append("open_positions_before_soak_ready")
        next_steps.append("flatten_or_steward_paper_positions")

    required_clean = max(1, observed.soak.required_clean_activations)
    clean_ratio = min(1.0, observed.soak.clean_activations / required_clean)
    score += 0.25 * clean_ratio
    if observed.soak.clean_activations < observed.soak.required_clean_activations:
        blockers.append("insufficient_clean_daemon_activations")
        next_steps.append("collect_more_clean_submitted_daemon_windows")

    required_windows = max(1, observed.soak.required_active_windows)
    window_ratio = min(1.0, len(observed.soak.active_windows) / required_windows)
    score += 0.20 * window_ratio
    if len(observed.soak.active_windows) < observed.soak.required_active_windows:
        blockers.append("insufficient_active_window_coverage")
        next_steps.append("capture_missing_market_open_or_close_window")

    if observed.soak.monitor_status == "passed" and observed.soak.data_parity_status == "passed":
        score += 0.05
    else:
        if observed.soak.monitor_status != "passed":
            blockers.append("daemon_monitor_not_passing")
        if observed.soak.data_parity_status != "passed":
            blockers.append("daemon_data_parity_not_passing")
        next_steps.append("rerun_soak_rollup_after_monitor_and_parity")

    if observed.soak.flatten_status == "passed" and observed.soak.stewardship_status == "passed":
        score += 0.05
    else:
        if observed.soak.flatten_status != "passed":
            blockers.append("flatten_drill_not_passing")
        if observed.soak.stewardship_status != "passed":
            blockers.append("position_stewardship_not_passing")
        next_steps.append("prove_flatten_and_position_stewardship")

    if observed.next_capture.can_run:
        status = "capture-ready"
        reason = "next_capture_window_ready"
    elif observed.soak.ready_for_autonomous_paper and not blockers:
        status = "autonomous-ready"
        reason = "all_gui_autonomy_gates_passed"
    elif observed.soak.ready_for_autonomous_paper:
        status = "operator-managed-ready"
        reason = "soak_ready_with_operator_controls_required"
    else:
        status = "blocked"
        reason = blockers[0] if blockers else observed.soak.recommended_action

    return GuiAutonomousReadinessReport(
        status=status,
        reason=reason,
        readiness_pct=min(1.0, score),
        blockers=tuple(dict.fromkeys(blockers)),
        next_steps=tuple(dict.fromkeys(next_steps)),
        snapshot=observed,
    )


def write_gui_autonomous_readiness_report(
    report: GuiAutonomousReadinessReport | None = None,
    path: str | Path = "reports/gui-autonomous-readiness.json",
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    observed = report or build_gui_autonomous_readiness_report()
    output_path.write_text(json.dumps(observed.to_dict(), indent=2), encoding="utf-8")
    return output_path


def build_gui_operator_snapshot(
    *,
    daemon_status: GuiDaemonStatus | None = None,
    dashboard_summary: GuiDashboardSummary | None = None,
    soak_summary: GuiSoakReadinessSummary | None = None,
    research_summary: GuiResearchSummary | None = None,
) -> GuiOperatorSnapshot:
    daemon = daemon_status or build_gui_daemon_status()
    dashboard = dashboard_summary or build_gui_dashboard_summary()
    soak = soak_summary or build_gui_soak_readiness_summary()
    research = research_summary or build_gui_research_summary()
    return GuiOperatorSnapshot(
        daemon=daemon,
        dashboard=dashboard,
        soak=soak,
        research=research,
        next_capture=build_gui_next_capture_decision(soak),
    )


def build_gui_soak_readiness_summary(
    *,
    rollup_path: str | Path = "reports/paper-daemon-soak-rollup.json",
    capture_plan_path: str | Path = "reports/paper-daemon-window-capture-plan.json",
    use_latest_fallback: bool = True,
    now: datetime | None = None,
    capture_calendar: MarketSessionCalendar | None = None,
    capture_market_session: str | MarketSession | None = None,
) -> GuiSoakReadinessSummary:
    present: list[str] = []
    missing: list[str] = []
    rollup = _load_json_artifact_with_latest(
        rollup_path,
        present,
        missing,
        "soak_rollup",
        latest_pattern="reports/paper-daemon-soak-rollup*.json",
        use_latest_fallback=use_latest_fallback,
    )
    capture_plan = _load_json_artifact_with_latest(
        capture_plan_path,
        present,
        missing,
        "window_capture_plan",
        latest_pattern="reports/paper-daemon-window-capture-plan*.json",
        use_latest_fallback=use_latest_fallback,
    )
    if not rollup:
        return GuiSoakReadinessSummary(
            artifacts_present=tuple(present),
            artifacts_missing=tuple(missing),
        )

    evidence = rollup.get("evidence") if isinstance(rollup.get("evidence"), dict) else {}
    checks = rollup.get("checks") if isinstance(rollup.get("checks"), dict) else {}
    status = "ready" if bool(rollup.get("passed")) else "blocked"
    next_target = _next_capture_target(capture_plan)
    capture_timing = _capture_window_timing(
        next_target,
        now=now,
        calendar=capture_calendar,
        market_session=capture_market_session,
    )
    return GuiSoakReadinessSummary(
        readiness_status=status,
        clean_activations=_int_value(evidence.get("clean_activations")),
        submitted_activations=_int_value(evidence.get("submitted_activations")),
        required_clean_activations=_int_value(evidence.get("required_clean_activations")),
        active_windows=tuple(str(window) for window in _as_sequence(evidence.get("active_windows")) if window),
        required_active_windows=_int_value(evidence.get("required_active_windows")),
        blockers=tuple(str(blocker) for blocker in _as_sequence(rollup.get("blockers")) if blocker),
        warnings=tuple(str(warning) for warning in _as_sequence(rollup.get("warnings")) if warning),
        recommended_action=str(rollup.get("recommended_action") or "review_paper_daemon_soak_rollup"),
        monitor_status=_check_status(checks, "monitor_passed"),
        data_parity_status=_check_status(checks, "data_parity_passed"),
        flatten_status=_check_status(checks, "flatten_drill_passed"),
        stewardship_status=_check_status(checks, "stewardship_passed"),
        observed_notional=_optional_float(evidence.get("observed_notional")),
        closed_symbols=tuple(str(symbol).upper() for symbol in _as_sequence(evidence.get("closed_symbols")) if symbol),
        next_capture_window=_target_name(next_target),
        next_capture_range=_target_range(next_target),
        next_capture_state=str(capture_timing["state"]),
        next_capture_market_session=str(capture_timing["market_session"]),
        minutes_until_capture_start=_optional_float(capture_timing.get("minutes_until_start")),
        minutes_until_capture_end=_optional_float(capture_timing.get("minutes_until_end")),
        missing_capture_windows=tuple(str(window) for window in _as_sequence((capture_plan or {}).get("missing_windows")) if window),
        next_capture_command=_target_command(next_target),
        artifacts_present=tuple(present),
        artifacts_missing=tuple(missing),
    )


def build_gui_next_capture_command(
    *,
    capture_plan_path: str | Path = "reports/paper-daemon-window-capture-plan.json",
    use_latest_fallback: bool = True,
) -> tuple[str, ...]:
    present: list[str] = []
    missing: list[str] = []
    capture_plan = _load_json_artifact_with_latest(
        capture_plan_path,
        present,
        missing,
        "window_capture_plan",
        latest_pattern="reports/paper-daemon-window-capture-plan*.json",
        use_latest_fallback=use_latest_fallback,
    )
    return _next_capture_command(capture_plan)


def build_gui_next_capture_decision(
    summary: GuiSoakReadinessSummary | None = None,
) -> GuiNextCaptureDecision:
    summary = summary or build_gui_soak_readiness_summary()
    if not summary.next_capture_command:
        return GuiNextCaptureDecision(
            can_run=False,
            reason="no_pending_capture_command",
            window=summary.next_capture_window,
            state=summary.next_capture_state,
        )
    if summary.next_capture_state != "active":
        return GuiNextCaptureDecision(
            can_run=False,
            reason="capture_window_not_active",
            command=summary.next_capture_command,
            window=summary.next_capture_window,
            state=summary.next_capture_state,
        )
    return GuiNextCaptureDecision(
        can_run=True,
        reason="ready_to_run_next_capture",
        command=summary.next_capture_command,
        window=summary.next_capture_window,
        state=summary.next_capture_state,
    )


def build_gui_dashboard_summary(
    *,
    monitor_path: str | Path = "reports/paper-monitor-report.json",
    pnl_path: str | Path = "reports/paper-pnl-attribution-report.json",
    drawdown_path: str | Path = "reports/paper-drawdown-report.json",
    fills_path: str | Path = "runs/fills.jsonl",
) -> GuiDashboardSummary:
    present: list[str] = []
    missing: list[str] = []
    monitor = _load_json_artifact(monitor_path, present, missing, "monitor")
    pnl = _load_json_artifact(pnl_path, present, missing, "pnl")
    drawdown = _load_json_artifact(drawdown_path, present, missing, "drawdown")
    fills = _load_jsonl_artifact(fills_path, present, missing, "fills")
    open_orders = _open_order_payloads(monitor)
    fills_seen = len(fills)
    latest_fill = _latest_fill_label(fills[-1]) if fills else None
    return GuiDashboardSummary(
        monitor_status=_status_from_payload(monitor),
        monitor_reason=str((monitor or {}).get("reason") or "paper_monitor_missing"),
        observed_positions=_position_count(monitor),
        observed_notional=_optional_float((monitor or {}).get("observed_notional")),
        open_orders=len(open_orders),
        stale_open_orders=sum(1 for order in open_orders if bool(order.get("stale"))),
        total_unrealized_pnl=_optional_float((pnl or {}).get("total_unrealized_pnl")),
        total_market_value=_optional_float((pnl or {}).get("total_market_value")),
        drawdown_pct=_optional_float((drawdown or {}).get("drawdown_pct")),
        mark_to_market_equity=_optional_float((drawdown or {}).get("mark_to_market_equity")),
        fills_seen=fills_seen,
        latest_fill=latest_fill,
        artifacts_present=tuple(present),
        artifacts_missing=tuple(missing),
    )


def build_gui_daemon_status(
    *,
    state_path: str | Path = "runs/paper-daemon-state.json",
    kill_switch_path: str | Path = "runs/paper-daemon.kill",
    stale_after_seconds: float = 900.0,
    now: datetime | None = None,
) -> GuiDaemonStatus:
    now = _utc_now(now)
    state = dict(load_paper_daemon_state(state_path))
    kill_switch_active = Path(kill_switch_path).exists()
    last_heartbeat_at = state.get("last_heartbeat_at")
    heartbeat_age = _heartbeat_age_seconds(last_heartbeat_at, now)
    if state.get("status") == "missing" or heartbeat_age is None:
        heartbeat_state = "missing"
    elif heartbeat_age > stale_after_seconds:
        heartbeat_state = "stale"
    else:
        heartbeat_state = "fresh"
    return GuiDaemonStatus(
        status=str(state.get("status", "missing")),
        heartbeat_state=heartbeat_state,
        kill_switch_active=kill_switch_active,
        iteration=int(state.get("iteration") or 0),
        heartbeat_age_seconds=heartbeat_age,
        last_heartbeat_at=str(last_heartbeat_at) if last_heartbeat_at else None,
        next_run_at=str(state.get("next_run_at")) if state.get("next_run_at") else None,
        last_reason=str(state.get("last_reason") or state.get("reason") or ""),
        last_active_window=str(state.get("last_active_window") or ""),
        state_path=str(state_path),
    )


def build_cli_command(
    config: GuiCommandConfig,
    *,
    python_executable: str | None = None,
    main_path: str | Path | None = None,
) -> list[str]:
    command = [python_executable or sys.executable, str(main_path or ROOT_DIR / "main.py"), config.mode]
    if config.mode in {"paper-daemon-stop", "paper-daemon-clear-stop", "paper-daemon-status"}:
        return command
    if config.mode not in {"paper-daemon-stop", "paper-daemon-clear-stop", "paper-daemon-status"}:
        command.extend(["--provider", config.provider, "--symbol", config.symbol, "--strategy", config.strategy])
    if config.execution_mode:
        command.extend(["--execution-mode", config.execution_mode])
    if config.submit_orders:
        command.append("--submit-orders")
    if config.store_dir:
        command.extend(["--store-dir", config.store_dir])
    if config.paper_profile:
        command.extend(["--paper-profile", config.paper_profile])
    if config.mode == "backtest" and config.output_path:
        command.extend(["--output", config.output_path])
    if config.mode == "validate-profile":
        command.extend(["--validation-profile", config.validation_profile])
        if config.validation_output_path:
            command.extend(["--validation-profile-output", config.validation_output_path])
    if config.mode == "paper-daemon":
        command.extend(["--paper-daemon-interval-seconds", str(config.daemon_interval_seconds)])
        if config.daemon_max_iterations is not None:
            command.extend(["--paper-daemon-max-iterations", str(config.daemon_max_iterations)])
        command.extend(
            [
                "--paper-daemon-state-output",
                config.daemon_state_path,
                "--paper-daemon-heartbeat-output",
                config.daemon_heartbeat_path,
                "--paper-daemon-kill-switch",
                config.daemon_kill_switch_path,
                "--paper-daemon-lock-path",
                config.daemon_lock_path,
                "--paper-daemon-lock-stale-seconds",
                str(config.daemon_lock_stale_seconds),
            ]
        )
    return command


class TradingBotDesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TradingBot")
        self.root.geometry("1180x760")
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self.chart_frame: ttk.Frame | None = None
        self.figure_canvas = None

        self.provider = tk.StringVar(value="sample")
        self.symbol = tk.StringVar(value="SPY")
        self.strategy = tk.StringVar(value="buyHold")
        self.execution_mode = tk.StringVar(value="dry-run")
        self.paper_profile = tk.StringVar(value="")
        self.gui_profile_preset = tk.StringVar(value="Sample dry-run")
        self.validation_profile = tk.StringVar(value="smoke")
        self.submit_orders = tk.BooleanVar(value=False)
        self.daemon_interval = tk.StringVar(value="300")
        self.daemon_iterations = tk.StringVar(value="")
        self.output_path = tk.StringVar(value=str(ROOT_DIR / "reports" / "gui-backtest.json"))
        self.store_dir = tk.StringVar(value=str(ROOT_DIR / "runs" / "gui"))
        self.status_text = tk.StringVar(value="Idle")
        self.daemon_card_text = tk.StringVar(value="Daemon: unknown\nHeartbeat: unknown\nKill switch: unknown")
        self.dashboard_card_text = tk.StringVar(value="Monitor: unknown\nPositions: unknown\nOpen orders: unknown")
        self.soak_card_text = tk.StringVar(value="Autonomy: unknown\nSoak: unknown\nNext: unknown")
        self.research_card_text = tk.StringVar(value="Research rows: unknown\nTop strategy: unknown")

        self._build_layout()
        self.refresh_daemon_cards()
        self.refresh_dashboard_cards()
        self.refresh_soak_cards()
        self.refresh_research_cards()
        self._poll_output()

    def _build_layout(self) -> None:
        self._configure_style()
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        control = ttk.Frame(self.root, padding=12)
        control.grid(row=0, column=0, sticky="ns")
        control.columnconfigure(1, weight=1)

        ttk.Label(control, text="Provider").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(control, textvariable=self.provider, values=("sample", "yfinance", "alpaca"), width=18).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(control, text="Symbol").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(control, textvariable=self.symbol, width=20).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(control, text="Strategy").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(control, textvariable=self.strategy, width=20).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(control, text="Execution").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(control, textvariable=self.execution_mode, values=("dry-run", "paper"), width=18).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(control, text="Submit paper orders", variable=self.submit_orders).grid(row=4, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(control, text="Paper profile").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Combobox(control, textvariable=self.paper_profile, values=("", "dry-run", "micro-notional", "full-paper-rehearsal"), width=18).grid(row=5, column=1, sticky="ew", pady=3)
        ttk.Label(control, text="GUI preset").grid(row=6, column=0, sticky="w", pady=3)
        ttk.Combobox(control, textvariable=self.gui_profile_preset, values=tuple(preset.name for preset in gui_profile_presets()), width=18).grid(row=6, column=1, sticky="ew", pady=3)
        ttk.Button(control, text="Apply Preset", command=self.apply_selected_preset).grid(row=7, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Label(control, text="Store dir").grid(row=8, column=0, sticky="w", pady=3)
        ttk.Entry(control, textvariable=self.store_dir, width=20).grid(row=8, column=1, sticky="ew", pady=3)

        ttk.Separator(control).grid(row=9, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Button(control, text="Run Backtest", command=self.run_backtest).grid(row=10, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Run Paper Session", command=lambda: self.run_cli_mode("paper-session")).grid(row=11, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Run Paper Schedule", command=lambda: self.run_cli_mode("paper-session-schedule")).grid(row=12, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Paper Monitor", command=lambda: self.run_cli_mode("paper-monitor")).grid(row=13, column=0, columnspan=2, sticky="ew", pady=3)

        ttk.Separator(control).grid(row=14, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(control, text="Validation").grid(row=15, column=0, sticky="w", pady=3)
        ttk.Combobox(control, textvariable=self.validation_profile, values=("smoke", "fast", "paper-dry-run", "paper-submit", "release", "live-gate"), width=18).grid(row=15, column=1, sticky="ew", pady=3)
        ttk.Button(control, text="Run Validation", command=self.run_validation_profile).grid(row=16, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Release Checklist", command=lambda: self.run_cli_mode("release-checklist")).grid(row=17, column=0, columnspan=2, sticky="ew", pady=3)

        ttk.Separator(control).grid(row=18, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(control, text="Daemon interval").grid(row=19, column=0, sticky="w", pady=3)
        ttk.Entry(control, textvariable=self.daemon_interval, width=20).grid(row=19, column=1, sticky="ew", pady=3)
        ttk.Label(control, text="Max loops").grid(row=20, column=0, sticky="w", pady=3)
        ttk.Entry(control, textvariable=self.daemon_iterations, width=20).grid(row=20, column=1, sticky="ew", pady=3)
        ttk.Button(control, text="Start Daemon", command=self.run_daemon).grid(row=21, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Run Next Capture", command=self.run_next_capture_window).grid(row=22, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Refresh Daemon", command=self.refresh_daemon_cards).grid(row=23, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Kill Switch", command=self.request_daemon_stop).grid(row=24, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Clear Kill Switch", command=self.clear_daemon_stop).grid(row=25, column=0, columnspan=2, sticky="ew", pady=3)

        ttk.Separator(control).grid(row=26, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Button(control, text="Refresh All Status", command=self.refresh_all_cards).grid(row=27, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Print Snapshot", command=self.print_operator_snapshot).grid(row=28, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Print Readiness", command=self.print_autonomous_readiness).grid(row=29, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(control, text="Save Readiness", command=self.save_autonomous_readiness).grid(row=30, column=0, columnspan=2, sticky="ew", pady=3)
        daemon_frame = ttk.LabelFrame(control, text="Daemon")
        daemon_frame.grid(row=31, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(daemon_frame, textvariable=self.daemon_card_text, wraplength=260, justify="left").pack(fill="x", padx=8, pady=6)
        soak_frame = ttk.LabelFrame(control, text="Autonomy Readiness")
        soak_frame.grid(row=32, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(soak_frame, textvariable=self.soak_card_text, wraplength=260, justify="left").pack(fill="x", padx=8, pady=6)
        dashboard_frame = ttk.LabelFrame(control, text="Paper Dashboard")
        dashboard_frame.grid(row=33, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(dashboard_frame, textvariable=self.dashboard_card_text, wraplength=260, justify="left").pack(fill="x", padx=8, pady=6)
        research_frame = ttk.LabelFrame(control, text="Research")
        research_frame.grid(row=34, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(research_frame, textvariable=self.research_card_text, wraplength=260, justify="left").pack(fill="x", padx=8, pady=6)
        ttk.Button(control, text="Open Artifact", command=self.open_artifact).grid(row=35, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Label(control, textvariable=self.status_text, wraplength=260).grid(row=36, column=0, columnspan=2, sticky="ew", pady=8)

        main = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main.grid(row=0, column=1, sticky="nsew")
        self.chart_frame = ttk.Frame(main, padding=8)
        main.add(self.chart_frame, weight=2)

        output_frame = ttk.Frame(main, padding=8)
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        self.output = tk.Text(output_frame, height=16, wrap="word")
        self.output.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(output_frame, command=self.output.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=scrollbar.set)
        main.add(output_frame, weight=1)

        self._draw_empty_chart()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TFrame", background="#f6f7f8")
        style.configure("TLabelframe", background="#f6f7f8", borderwidth=1)
        style.configure("TLabelframe.Label", font=("Segoe UI", 9, "bold"))
        style.configure("TButton", padding=(8, 5))

    def current_config(self, mode: str) -> GuiCommandConfig:
        iterations = self.daemon_iterations.get().strip()
        return GuiCommandConfig(
            mode=mode,
            provider=self.provider.get().strip() or "sample",
            symbol=self.symbol.get().strip().upper() or "SPY",
            strategy=self.strategy.get().strip() or "buyHold",
            execution_mode=self.execution_mode.get().strip() or "dry-run",
            paper_profile=self.paper_profile.get().strip(),
            submit_orders=bool(self.submit_orders.get()),
            daemon_interval_seconds=float(self.daemon_interval.get().strip() or 300),
            daemon_max_iterations=int(iterations) if iterations else None,
            output_path=self.output_path.get().strip(),
            store_dir=self.store_dir.get().strip() or str(ROOT_DIR / "runs" / "gui"),
            validation_profile=self.validation_profile.get().strip() or "smoke",
            validation_output_path=str(ROOT_DIR / "reports" / f"gui-validation-{self.validation_profile.get().strip() or 'smoke'}.json"),
        )

    def apply_selected_preset(self) -> None:
        try:
            config = apply_gui_profile_preset(self.current_config("backtest"), self.gui_profile_preset.get())
        except Exception as exc:
            messagebox.showerror("TradingBot", str(exc))
            return
        self.provider.set(config.provider)
        self.execution_mode.set(config.execution_mode)
        self.paper_profile.set(config.paper_profile)
        self.submit_orders.set(config.submit_orders)
        self.daemon_interval.set(str(config.daemon_interval_seconds))
        self.daemon_iterations.set("" if config.daemon_max_iterations is None else str(config.daemon_max_iterations))
        self.status_text.set(f"Applied preset: {self.gui_profile_preset.get()}")

    def run_backtest(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("TradingBot", "A task is already running.")
            return
        self._clear_output()
        self.status_text.set("Running backtest")
        self.worker = threading.Thread(target=self._run_backtest_worker, daemon=True)
        self.worker.start()

    def _run_backtest_worker(self) -> None:
        try:
            config = self.current_config("backtest")
            runtime = load_runtime_config(
                {
                    "provider": config.provider,
                    "symbol": config.symbol,
                    "strategy": config.strategy,
                    "execution_mode": config.execution_mode,
                }
            )
            app = TradingApplication(runtime)
            data = app.load_data()
            strategy = app.create_strategy()
            result = app.run_backtest(data, strategy)
            self.output_queue.put(format_backtest_summary(result) + "\n")
            self.root.after(0, lambda: self._draw_backtest_chart(data, result))
            self.root.after(0, lambda: self.status_text.set("Backtest complete"))
        except Exception as exc:
            self.output_queue.put(f"ERROR: {exc}\n")
            self.root.after(0, lambda: self.status_text.set("Backtest failed"))

    def run_daemon(self) -> None:
        self.run_cli_mode("paper-daemon")

    def run_next_capture_window(self) -> None:
        summary = build_gui_soak_readiness_summary()
        decision = build_gui_next_capture_decision(summary)
        self.soak_card_text.set("\n".join(summary.card_lines()))
        if not decision.can_run:
            messagebox.showinfo(
                "TradingBot",
                _next_capture_blocked_message(decision),
            )
            return
        if decision.submit_requested and not messagebox.askyesno("TradingBot", "Run the next guarded paper capture and submit paper orders if all guards pass?"):
            return
        self._run_prebuilt_command(list(decision.command), "next-capture")

    def run_validation_profile(self) -> None:
        self.run_cli_mode("validate-profile")

    def refresh_daemon_cards(self) -> None:
        status = build_gui_daemon_status()
        self.daemon_card_text.set("\n".join(status.card_lines()))
        self.status_text.set(f"Daemon status refreshed: {status.status}")

    def refresh_dashboard_cards(self) -> None:
        summary = build_gui_dashboard_summary()
        self.dashboard_card_text.set("\n".join(summary.card_lines()))
        self.status_text.set(f"Dashboard refreshed: {summary.monitor_status}")

    def refresh_soak_cards(self) -> None:
        summary = build_gui_soak_readiness_summary()
        self.soak_card_text.set("\n".join(summary.card_lines()))
        self.status_text.set(f"Autonomy readiness refreshed: {summary.readiness_status}")

    def refresh_research_cards(self) -> None:
        summary = build_gui_research_summary()
        self.research_card_text.set("\n".join(summary.card_lines()))
        self.status_text.set(f"Research refreshed: {summary.strategy_rows} rows")

    def refresh_all_cards(self) -> None:
        self.refresh_daemon_cards()
        self.refresh_dashboard_cards()
        self.refresh_soak_cards()
        self.refresh_research_cards()
        self.status_text.set("Status cards refreshed")

    def print_operator_snapshot(self) -> None:
        snapshot = build_gui_operator_snapshot()
        self.output_queue.put(json.dumps(snapshot.to_dict(), indent=2) + "\n")
        self.status_text.set(f"Operator snapshot: {snapshot.status}")

    def print_autonomous_readiness(self) -> None:
        report = build_gui_autonomous_readiness_report()
        self.output_queue.put(json.dumps(report.to_dict(), indent=2) + "\n")
        self.status_text.set(f"Autonomous readiness: {report.status}")

    def save_autonomous_readiness(self) -> None:
        path = write_gui_autonomous_readiness_report()
        self.output_queue.put(f"Autonomous readiness report written: {path}\n")
        self.status_text.set(f"Saved readiness: {path}")

    def request_daemon_stop(self) -> None:
        if not messagebox.askyesno("TradingBot", "Activate the paper daemon kill switch?"):
            return
        path = request_paper_daemon_stop()
        self.output_queue.put(f"Paper daemon kill switch written: {path}\n")
        self.refresh_daemon_cards()

    def clear_daemon_stop(self) -> None:
        if not messagebox.askyesno("TradingBot", "Clear the paper daemon kill switch?"):
            return
        removed = clear_paper_daemon_stop()
        self.output_queue.put(f"Paper daemon kill switch {'cleared' if removed else 'not present'}.\n")
        self.refresh_daemon_cards()

    def run_cli_mode(self, mode: str) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("TradingBot", "A task is already running.")
            return
        if mode in {"paper-session", "paper-session-schedule", "paper-daemon"} and self.submit_orders.get():
            if not messagebox.askyesno("TradingBot", "Submit paper orders if all guards pass?"):
                return
        self._clear_output()
        config = self.current_config(mode)
        command = build_cli_command(config)
        self.output_queue.put("$ " + " ".join(_quote_part(part) for part in command) + "\n")
        self.status_text.set(f"Running {mode}")
        self.worker = threading.Thread(target=self._run_command_worker, args=(command, mode), daemon=True)
        self.worker.start()

    def _run_prebuilt_command(self, command: list[str], mode: str) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("TradingBot", "A task is already running.")
            return
        self._clear_output()
        self.output_queue.put("$ " + " ".join(_quote_part(part) for part in command) + "\n")
        self.status_text.set(f"Running {mode}")
        self.worker = threading.Thread(target=self._run_command_worker, args=(command, mode), daemon=True)
        self.worker.start()

    def _run_command_worker(self, command: list[str], mode: str) -> None:
        try:
            self.process = subprocess.Popen(
                command,
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.output_queue.put(line)
            return_code = self.process.wait()
            self.root.after(0, lambda: self.status_text.set(f"{mode} exited with code {return_code}"))
        except Exception as exc:
            self.output_queue.put(f"ERROR: {exc}\n")
            self.root.after(0, lambda: self.status_text.set(f"{mode} failed"))
        finally:
            self.process = None
            self.root.after(0, self.refresh_daemon_cards)
            self.root.after(0, self.refresh_dashboard_cards)
            self.root.after(0, self.refresh_soak_cards)
            self.root.after(0, self.refresh_research_cards)

    def _draw_empty_chart(self) -> None:
        self._draw_chart([], [], "Run a backtest to display price and equity")

    def _draw_backtest_chart(self, data, result) -> None:
        equity = result.equity
        self._draw_chart(
            [(str(index), float(value)) for index, value in data["Close"].items()],
            [(str(index), float(value)) for index, value in equity.items()],
            "Backtest Price and Equity",
        )

    def _draw_chart(self, close_points: Iterable[tuple[str, float]], equity_points: Iterable[tuple[str, float]], title: str) -> None:
        assert self.chart_frame is not None
        for child in self.chart_frame.winfo_children():
            child.destroy()
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except Exception as exc:
            ttk.Label(self.chart_frame, text=f"Chart unavailable: {exc}").pack(fill="both", expand=True)
            return

        close_points = list(close_points)
        equity_points = list(equity_points)
        fig = Figure(figsize=(8, 4.5), dpi=100)
        price_ax = fig.add_subplot(211)
        equity_ax = fig.add_subplot(212)
        fig.suptitle(title)
        if close_points:
            price_ax.plot(range(len(close_points)), [point[1] for point in close_points], color="#147c78", linewidth=1.4)
            price_ax.set_ylabel("Close")
        else:
            price_ax.text(0.5, 0.5, "No chart data yet", ha="center", va="center")
        if equity_points:
            equity_ax.plot(range(len(equity_points)), [point[1] for point in equity_points], color="#5b4bb2", linewidth=1.4)
            equity_ax.set_ylabel("Equity")
        else:
            equity_ax.text(0.5, 0.5, "Equity will appear here", ha="center", va="center")
        equity_ax.set_xlabel("Bars")
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.figure_canvas = canvas

    def open_artifact(self) -> None:
        path = filedialog.askopenfilename(initialdir=str(ROOT_DIR), title="Open report or artifact")
        if not path:
            return
        try:
            payload = Path(path).read_text(encoding="utf-8")
            if path.lower().endswith(".json"):
                payload = json.dumps(json.loads(payload), indent=2)
            self._clear_output()
            self.output_queue.put(payload)
            self.status_text.set(f"Opened {path}")
        except Exception as exc:
            messagebox.showerror("TradingBot", str(exc))

    def _clear_output(self) -> None:
        self.output.delete("1.0", tk.END)

    def _poll_output(self) -> None:
        try:
            while True:
                self.output.insert(tk.END, self.output_queue.get_nowait())
                self.output.see(tk.END)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_output)


def _quote_part(part: str) -> str:
    if " " not in part:
        return part
    return f'"{part}"'


def _heartbeat_age_seconds(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        heartbeat = datetime.fromisoformat(value)
    except ValueError:
        return None
    heartbeat = _utc_now(heartbeat)
    return max(0.0, (now - heartbeat).total_seconds())


def _load_json_artifact(path: str | Path, present: list[str], missing: list[str], label: str) -> dict | None:
    artifact = Path(path)
    if not artifact.exists():
        missing.append(label)
        return None
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception:
        missing.append(f"{label}:invalid")
        return None
    present.append(label)
    return payload if isinstance(payload, dict) else None


def _load_json_artifact_with_latest(
    path: str | Path,
    present: list[str],
    missing: list[str],
    label: str,
    *,
    latest_pattern: str,
    use_latest_fallback: bool,
) -> dict | None:
    artifact = Path(path)
    if not artifact.exists() and use_latest_fallback:
        artifact = _latest_matching_artifact(latest_pattern) or artifact
    return _load_json_artifact(artifact, present, missing, label)


def _latest_matching_artifact(pattern: str) -> Path | None:
    matches = [path for path in Path().glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _load_jsonl_artifact(path: str | Path, present: list[str], missing: list[str], label: str) -> list[dict]:
    artifact = Path(path)
    if not artifact.exists():
        missing.append(label)
        return []
    rows: list[dict] = []
    try:
        for line in artifact.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    except Exception:
        missing.append(f"{label}:invalid")
        return []
    present.append(label)
    return rows


def _status_from_payload(payload: dict | None) -> str:
    if not payload:
        return "missing"
    if bool(payload.get("passed")):
        return "passed"
    if payload.get("passed") is False:
        return "failed"
    return str(payload.get("status") or "unknown")


def _position_count(payload: dict | None) -> int:
    if not payload:
        return 0
    observed = payload.get("observed_positions")
    if isinstance(observed, dict):
        return sum(1 for quantity in observed.values() if _optional_float(quantity) not in {None, 0.0})
    positions_seen = payload.get("positions_seen")
    if isinstance(positions_seen, list):
        return len(positions_seen)
    return 0


def _open_order_payloads(payload: dict | None) -> tuple[dict, ...]:
    if not payload:
        return ()
    source = payload.get("open_orders")
    if isinstance(source, dict):
        orders = source.get("orders") or source.get("open_orders") or ()
    else:
        orders = payload.get("open_orders") or ()
    return tuple(order for order in orders if isinstance(order, dict))


def _check_status(checks: dict, name: str) -> str:
    if name not in checks:
        return "missing"
    return "passed" if bool(checks.get(name)) else "blocked"


def _next_capture_window(capture_plan: dict | None) -> str | None:
    return _target_name(_next_capture_target(capture_plan))


def _next_capture_target(capture_plan: dict | None) -> dict | None:
    if not capture_plan:
        return None
    for target in _as_sequence(capture_plan.get("targets")):
        if isinstance(target, dict) and target.get("action") == "capture_next":
            return target
    return None


def _next_capture_command(capture_plan: dict | None) -> tuple[str, ...]:
    return _target_command(_next_capture_target(capture_plan))


def _next_capture_blocked_message(decision: GuiNextCaptureDecision) -> str:
    if decision.reason == "no_pending_capture_command":
        return "No pending capture command found."
    window = decision.window or "unknown"
    if decision.state == "market_closed":
        return f"The next capture window ({window}) is inside a closed market session."
    if decision.state == "upcoming":
        return f"The next capture window ({window}) is not active yet."
    if decision.state == "missed_today":
        return f"The next capture window ({window}) has already passed for today."
    return f"The next capture window ({window}) is not active."


def _target_name(target: dict | None) -> str | None:
    if not target:
        return None
    return str(target.get("name") or "") or None


def _target_range(target: dict | None) -> str | None:
    if not target:
        return None
    start = str(target.get("start_time") or "")
    end = str(target.get("end_time") or "")
    if not start or not end or "unknown" in {start.lower(), end.lower()}:
        return None
    return f"{start}-{end} CT"


def _target_command(target: dict | None) -> tuple[str, ...]:
    if not target:
        return ()
    return tuple(str(part) for part in _as_sequence(target.get("command")) if part)


def _capture_window_timing(
    target: dict | None,
    *,
    now: datetime | None = None,
    calendar: MarketSessionCalendar | None = None,
    market_session: str | MarketSession | None = None,
) -> dict[str, float | str | None]:
    if not target:
        return {"state": "none", "market_session": "unknown", "minutes_until_start": None, "minutes_until_end": None}
    start = _parse_hhmm(target.get("start_time"))
    end = _parse_hhmm(target.get("end_time"))
    if start is None or end is None:
        return {"state": "unknown", "market_session": "unknown", "minutes_until_start": None, "minutes_until_end": None}
    local_now = _central_now(now)
    session = _capture_market_session(local_now, calendar=calendar, market_session=market_session)
    if session == "closed":
        return {
            "state": "market_closed",
            "market_session": session,
            "minutes_until_start": None,
            "minutes_until_end": None,
        }
    current = local_now.timetz().replace(tzinfo=None)
    if current < start:
        return {
            "state": "upcoming",
            "market_session": session,
            "minutes_until_start": _minutes_between(current, start),
            "minutes_until_end": _minutes_between(current, end),
        }
    if start <= current <= end:
        return {
            "state": "active",
            "market_session": session,
            "minutes_until_start": 0.0,
            "minutes_until_end": _minutes_between(current, end),
        }
    return {"state": "missed_today", "market_session": session, "minutes_until_start": None, "minutes_until_end": None}


def _capture_timing_label(
    state: str,
    minutes_until_start: float | None,
    minutes_until_end: float | None,
) -> str:
    if state == "active" and minutes_until_end is not None:
        return f"ends_in={minutes_until_end:.0f}m"
    if state == "upcoming" and minutes_until_start is not None:
        return f"starts_in={minutes_until_start:.0f}m"
    return ""


def _capture_market_session(
    now: datetime,
    *,
    calendar: MarketSessionCalendar | None = None,
    market_session: str | MarketSession | None = None,
) -> str:
    if market_session is not None:
        return _normalize_market_session(market_session)
    session_calendar = calendar or MarketSessionCalendar()
    return _normalize_market_session(session_calendar.session_at(now))


def _normalize_market_session(session: str | MarketSession) -> str:
    value = session.value if isinstance(session, MarketSession) else str(session)
    return value.lower()


def _parse_hhmm(value) -> time | None:
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _central_now(value: datetime | None = None) -> datetime:
    zone = ZoneInfo("America/Chicago")
    if value is None:
        return datetime.now(zone)
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def _minutes_between(start: time, end: time) -> float:
    start_minutes = start.hour * 60 + start.minute + start.second / 60
    end_minutes = end.hour * 60 + end.minute + end.second / 60
    return max(0.0, end_minutes - start_minutes)


def _as_sequence(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _int_value(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _summary_rows(payload: dict | None, keys: tuple[str, ...]) -> tuple[dict, ...]:
    if not payload:
        return ()
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return tuple(item for item in value if isinstance(item, dict))
        if isinstance(value, dict):
            nested = _summary_rows(value, keys)
            if nested:
                return nested
    return ()


def _top_strategy_row(payload: dict | None) -> dict | None:
    rows = _summary_rows(payload, ("strategy_summary", "rows", "records", "summary"))
    if not rows:
        return None
    return max(rows, key=_row_score)


def _row_score(row: dict) -> float:
    for key in ("score", "average_excess_return", "average_return", "avg_return", "total_return", "return"):
        value = _optional_float(row.get(key))
        if value is not None:
            return value
    return 0.0


def _strategy_label(row: dict | None) -> str | None:
    if not row:
        return None
    return str(row.get("strategy") or row.get("strategy_name") or row.get("name") or row.get("profile") or "unknown")


def _metric_label(row: dict | None) -> str | None:
    if not row:
        return None
    for key in ("score", "average_excess_return", "average_return", "avg_return", "total_return", "return"):
        value = _optional_float(row.get(key))
        if value is not None:
            return f"{key}={value:.4f}"
    return None


def _row_selected(row: dict) -> bool:
    if row.get("selected") is not None:
        return bool(row.get("selected"))
    if row.get("enabled") is not None:
        return bool(row.get("enabled"))
    value = _optional_float(row.get("average_excess_return") or row.get("excess_return"))
    return bool(value is not None and value > 0)


def _promotion_counts(payload: dict | None) -> tuple[int, int]:
    if not payload:
        return 0, 0
    candidate_count = payload.get("candidate_count")
    enabled_count = payload.get("enabled_count")
    if candidate_count is not None or enabled_count is not None:
        return int(candidate_count or 0), int(enabled_count or 0)
    candidates = payload.get("candidates") or payload.get("promotion_candidates") or payload.get("rows") or ()
    if not isinstance(candidates, list):
        return 0, 0
    rows = tuple(item for item in candidates if isinstance(item, dict))
    return len(rows), sum(1 for row in rows if bool(row.get("enabled") or row.get("selected")))


def _latest_fill_label(payload: dict) -> str:
    symbol = str(payload.get("symbol") or "").upper() or "?"
    side = str(payload.get("side") or "").upper() or "?"
    quantity = payload.get("quantity") or payload.get("qty") or "?"
    price = payload.get("price") or payload.get("average_fill_price") or "?"
    return f"{symbol} {side} {quantity} @ {price}"


def _optional_float(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}"


def _utc_now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def main() -> None:
    root = tk.Tk()
    TradingBotDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
