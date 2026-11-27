from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .paper_daemon import load_paper_daemon_state


@dataclass(frozen=True)
class PaperCommandCenterReport:
    generated_at: datetime
    provider: str
    symbol: str
    strategy: str
    execution_mode: str
    paper_profile: str | None
    daemon_status: str
    heartbeat_state: str
    kill_switch_active: bool
    iteration: int
    active_window: str | None
    last_reason: str
    next_run_at: str | None
    monitor_status: str
    monitor_reason: str
    observed_positions: int
    observed_notional: float | None
    open_orders: int
    stale_open_orders: int
    data_parity_status: str
    data_parity_reason: str
    data_parity_failed_checks: int
    total_unrealized_pnl: float | None
    total_market_value: float | None
    drawdown_pct: float | None
    mark_to_market_equity: float | None
    fills_seen: int
    latest_fill: str | None
    artifacts_present: tuple[str, ...]
    artifacts_missing: tuple[str, ...]
    last_artifacts: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_action: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "generated_at": self.generated_at.isoformat(),
            "provider": self.provider,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "execution_mode": self.execution_mode,
            "paper_profile": self.paper_profile,
            "daemon": {
                "status": self.daemon_status,
                "heartbeat_state": self.heartbeat_state,
                "kill_switch_active": self.kill_switch_active,
                "iteration": self.iteration,
                "active_window": self.active_window,
                "last_reason": self.last_reason,
                "next_run_at": self.next_run_at,
            },
            "paper": {
                "monitor_status": self.monitor_status,
                "monitor_reason": self.monitor_reason,
                "observed_positions": self.observed_positions,
                "observed_notional": self.observed_notional,
                "open_orders": self.open_orders,
                "stale_open_orders": self.stale_open_orders,
                "data_parity_status": self.data_parity_status,
                "data_parity_reason": self.data_parity_reason,
                "data_parity_failed_checks": self.data_parity_failed_checks,
                "total_unrealized_pnl": self.total_unrealized_pnl,
                "total_market_value": self.total_market_value,
                "drawdown_pct": self.drawdown_pct,
                "mark_to_market_equity": self.mark_to_market_equity,
                "fills_seen": self.fills_seen,
                "latest_fill": self.latest_fill,
            },
            "artifacts_present": list(self.artifacts_present),
            "artifacts_missing": list(self.artifacts_missing),
            "last_artifacts": list(self.last_artifacts),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
            "artifact_path": self.artifact_path,
        }

    def summary_lines(self) -> tuple[str, ...]:
        return (
            f"Daemon: {self.daemon_status} heartbeat={self.heartbeat_state} kill_switch={'active' if self.kill_switch_active else 'clear'}",
            f"Run: {self.provider}/{self.symbol} strategy={self.strategy} mode={self.execution_mode} profile={self.paper_profile or 'none'}",
            f"Window: {self.active_window or 'none'} iteration={self.iteration} reason={self.last_reason}",
            f"Monitor: {self.monitor_status} positions={self.observed_positions} notional={_money(self.observed_notional)} open_orders={self.open_orders} stale={self.stale_open_orders}",
            f"Data parity: {self.data_parity_status} reason={self.data_parity_reason} failed_checks={self.data_parity_failed_checks}",
            f"Risk: pnl={_money(self.total_unrealized_pnl)} drawdown={_pct(self.drawdown_pct)} equity={_money(self.mark_to_market_equity)}",
            f"Fills: {self.fills_seen} latest={self.latest_fill or 'none'}",
            f"Action: {self.recommended_action}",
        )


def build_paper_command_center_report(
    *,
    provider: str = "sample",
    symbol: str = "SPY",
    strategy: str = "buyHold",
    execution_mode: str = "dry-run",
    paper_profile: str | None = None,
    state_path: str | Path = "runs/paper-daemon-state.json",
    kill_switch_path: str | Path = "runs/paper-daemon.kill",
    daemon_report_path: str | Path = "reports/paper-daemon-report.json",
    monitor_path: str | Path = "reports/paper-monitor-report.json",
    pnl_path: str | Path = "reports/paper-pnl-attribution-report.json",
    drawdown_path: str | Path = "reports/paper-drawdown-report.json",
    fills_path: str | Path = "runs/fills.jsonl",
    stale_after_seconds: float = 900.0,
    now: datetime | None = None,
) -> PaperCommandCenterReport:
    now = _utc_now(now)
    present: list[str] = []
    missing: list[str] = []
    state = dict(load_paper_daemon_state(state_path))
    _track_path(state_path, present, missing, "daemon_state")
    daemon_report = _load_json_artifact(daemon_report_path, present, missing, "daemon_report")
    monitor = _load_json_artifact(monitor_path, present, missing, "monitor")
    pnl = _load_json_artifact(pnl_path, present, missing, "pnl")
    drawdown = _load_json_artifact(drawdown_path, present, missing, "drawdown")
    fills = _load_jsonl_artifact(fills_path, present, missing, "fills")
    latest_iteration = _latest_iteration(daemon_report)
    open_orders = _open_order_payloads(monitor)
    data_parity_status = _data_parity_status(latest_iteration)
    data_parity_reason = str(latest_iteration.get("data_parity_reason") or "data_parity_missing")
    heartbeat_age = _heartbeat_age_seconds(state.get("last_heartbeat_at"), now)
    heartbeat_state = _heartbeat_state(state, heartbeat_age, stale_after_seconds)
    kill_switch_active = Path(kill_switch_path).exists()
    warnings = _command_center_warnings(
        daemon_status=str(state.get("status") or "missing"),
        heartbeat_state=heartbeat_state,
        kill_switch_active=kill_switch_active,
        monitor_status=_status_from_payload(monitor),
        stale_open_orders=sum(1 for order in open_orders if bool(order.get("stale"))),
        data_parity_status=data_parity_status,
        artifacts_missing=tuple(missing),
    )
    return PaperCommandCenterReport(
        generated_at=now,
        provider=provider,
        symbol=symbol.upper(),
        strategy=strategy,
        execution_mode=execution_mode,
        paper_profile=paper_profile,
        daemon_status=str(state.get("status") or "missing"),
        heartbeat_state=heartbeat_state,
        kill_switch_active=kill_switch_active,
        iteration=_int_value(state.get("iteration")),
        active_window=_optional_str(state.get("last_active_window")),
        last_reason=str(state.get("last_reason") or state.get("reason") or "unknown"),
        next_run_at=_optional_str(state.get("next_run_at")),
        monitor_status=_status_from_payload(monitor),
        monitor_reason=str((monitor or {}).get("reason") or "paper_monitor_missing"),
        observed_positions=_position_count(monitor),
        observed_notional=_optional_float((monitor or {}).get("observed_notional")),
        open_orders=len(open_orders),
        stale_open_orders=sum(1 for order in open_orders if bool(order.get("stale"))),
        data_parity_status=data_parity_status,
        data_parity_reason=data_parity_reason,
        data_parity_failed_checks=_int_value(latest_iteration.get("data_parity_failed_checks")),
        total_unrealized_pnl=_optional_float((pnl or {}).get("total_unrealized_pnl")),
        total_market_value=_optional_float((pnl or {}).get("total_market_value")),
        drawdown_pct=_optional_float((drawdown or {}).get("drawdown_pct")),
        mark_to_market_equity=_optional_float((drawdown or {}).get("mark_to_market_equity")),
        fills_seen=len(fills),
        latest_fill=_latest_fill_label(fills[-1]) if fills else None,
        artifacts_present=tuple(present),
        artifacts_missing=tuple(missing),
        last_artifacts=_last_artifacts(daemon_report, monitor, pnl, drawdown),
        warnings=warnings,
        recommended_action=_recommended_action(warnings, str(state.get("status") or "missing")),
    )


def write_paper_command_center_report(report: PaperCommandCenterReport, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def _command_center_warnings(
    *,
    daemon_status: str,
    heartbeat_state: str,
    kill_switch_active: bool,
    monitor_status: str,
    stale_open_orders: int,
    data_parity_status: str,
    artifacts_missing: tuple[str, ...],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if daemon_status in {"missing", "error", "lock_active"}:
        warnings.append(f"daemon_{daemon_status}")
    if heartbeat_state == "stale":
        warnings.append("daemon_heartbeat_stale")
    if kill_switch_active:
        warnings.append("kill_switch_active")
    if monitor_status == "failed":
        warnings.append("paper_monitor_failed")
    if stale_open_orders:
        warnings.append("stale_open_orders_present")
    if data_parity_status == "failed":
        warnings.append("data_parity_failed")
    if "daemon_state" in artifacts_missing:
        warnings.append("daemon_state_missing")
    return tuple(dict.fromkeys(warnings))


def _recommended_action(warnings: Sequence[str], daemon_status: str) -> str:
    warning_set = set(warnings)
    if "kill_switch_active" in warning_set:
        return "clear_kill_switch_before_resuming_daemon"
    if daemon_status == "error":
        return "review_daemon_error_and_reconcile_broker_state"
    if "daemon_heartbeat_stale" in warning_set or daemon_status == "missing":
        return "start_or_recover_paper_daemon"
    if warning_set & {"paper_monitor_failed", "stale_open_orders_present", "data_parity_failed"}:
        return "review_paper_risk_artifacts_before_next_submit"
    if daemon_status == "running":
        return "continue_monitoring_current_daemon"
    return "resume_daemon_when_next_paper_window_is_ready"


def _latest_iteration(daemon_report: Mapping[str, Any] | None) -> Mapping[str, Any]:
    iterations = _sequence((daemon_report or {}).get("iterations"))
    if not iterations:
        return {}
    latest = iterations[-1]
    return latest if isinstance(latest, Mapping) else {}


def _last_artifacts(
    daemon_report: Mapping[str, Any] | None,
    monitor: Mapping[str, Any] | None,
    pnl: Mapping[str, Any] | None,
    drawdown: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    paths: list[str] = []
    latest = _latest_iteration(daemon_report)
    for value in _sequence(latest.get("artifact_paths")):
        if value:
            paths.append(str(value))
    for payload in (daemon_report, monitor, pnl, drawdown):
        artifact = (payload or {}).get("artifact_path")
        if artifact:
            paths.append(str(artifact))
    return tuple(dict.fromkeys(paths))


def _open_order_payloads(monitor: Mapping[str, Any] | None) -> tuple[Mapping[str, Any], ...]:
    open_orders = (monitor or {}).get("open_orders")
    if isinstance(open_orders, Mapping):
        orders = open_orders.get("orders") or open_orders.get("open_orders") or ()
        return tuple(order for order in _sequence(orders) if isinstance(order, Mapping))
    return ()


def _position_count(monitor: Mapping[str, Any] | None) -> int:
    positions = (monitor or {}).get("observed_positions")
    if isinstance(positions, Mapping):
        return sum(1 for quantity in positions.values() if abs(float(quantity or 0.0)) > 1e-12)
    return 0


def _data_parity_status(iteration: Mapping[str, Any]) -> str:
    if iteration.get("data_parity_passed") is True:
        return "passed"
    if iteration.get("data_parity_passed") is False:
        return "failed"
    return "missing"


def _status_from_payload(payload: Mapping[str, Any] | None) -> str:
    if payload is None:
        return "missing"
    return "passed" if bool(payload.get("passed")) else "failed"


def _load_json_artifact(path: str | Path, present: list[str], missing: list[str], label: str) -> Mapping[str, Any] | None:
    artifact = Path(path)
    if not artifact.exists():
        missing.append(label)
        return None
    present.append(label)
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception:
        return {"passed": False, "reason": "artifact_invalid_json", "artifact_path": str(artifact)}
    return payload if isinstance(payload, Mapping) else {"passed": False, "reason": "artifact_not_mapping", "artifact_path": str(artifact)}


def _load_jsonl_artifact(path: str | Path, present: list[str], missing: list[str], label: str) -> tuple[Mapping[str, Any], ...]:
    artifact = Path(path)
    if not artifact.exists():
        missing.append(label)
        return ()
    present.append(label)
    rows: list[Mapping[str, Any]] = []
    for line in artifact.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, Mapping):
            rows.append(payload)
    return tuple(rows)


def _track_path(path: str | Path, present: list[str], missing: list[str], label: str) -> None:
    if Path(path).exists():
        present.append(label)
    else:
        missing.append(label)


def _heartbeat_state(state: Mapping[str, Any], heartbeat_age: float | None, stale_after_seconds: float) -> str:
    if state.get("status") == "missing" or heartbeat_age is None:
        return "missing"
    return "stale" if heartbeat_age > stale_after_seconds else "fresh"


def _heartbeat_age_seconds(value: Any, now: datetime) -> float | None:
    timestamp = _parse_datetime(value)
    if timestamp is None:
        return None
    return max(0.0, (now - timestamp).total_seconds())


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc_now(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return _utc_now(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _latest_fill_label(fill: Mapping[str, Any]) -> str:
    symbol = str(fill.get("symbol") or "").upper()
    side = str(fill.get("side") or "").upper()
    quantity = fill.get("quantity") or fill.get("qty") or "?"
    price = fill.get("price") or fill.get("average_fill_price") or "?"
    return f"{symbol} {side} {quantity} @ {price}".strip()


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _int_value(value: Any) -> int:
    if value in {None, ""}:
        return 0
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def _utc_now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.2f}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"
