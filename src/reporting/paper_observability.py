from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import BLOCKING_STATUSES, status_passed, to_float, utc_timestamp, write_json_payload, write_text_payload


@dataclass(frozen=True)
class PaperDashboardExposureRow:
    symbol: str
    expected_quantity: float
    broker_quantity: float
    notional: float = 0.0
    tolerance: float = 0.0

    @property
    def drift_quantity(self) -> float:
        return self.broker_quantity - self.expected_quantity

    @property
    def status(self) -> str:
        return "matched" if abs(self.drift_quantity) <= self.tolerance else "mismatch"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "expected_quantity": self.expected_quantity,
            "broker_quantity": self.broker_quantity,
            "drift_quantity": self.drift_quantity,
            "notional": self.notional,
            "tolerance": self.tolerance,
            "status": self.status,
        }


@dataclass(frozen=True)
class PaperDashboardMonitorStatus:
    name: str
    status: str
    reason: str = ""
    source_artifact: str | None = None

    @property
    def passed(self) -> bool:
        return status_passed(self.status)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "passed": self.passed,
            "reason": self.reason,
            "source_artifact": self.source_artifact,
        }


@dataclass(frozen=True)
class PaperDashboardStrategyStatus:
    name: str
    enabled: bool
    state: str = "unknown"
    current_signal: str = "HOLD"
    scorecard_status: str = "unknown"
    latest_artifact: str | None = None

    @property
    def active(self) -> bool:
        return self.enabled and self.state.lower() not in {"disabled", "paused", "blocked"}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "active": self.active,
            "state": self.state,
            "current_signal": self.current_signal,
            "scorecard_status": self.scorecard_status,
            "latest_artifact": self.latest_artifact,
        }


@dataclass(frozen=True)
class PaperTradingDashboardReport:
    generated_at: str
    exposures: tuple[PaperDashboardExposureRow, ...] = ()
    monitors: tuple[PaperDashboardMonitorStatus, ...] = ()
    strategies: tuple[PaperDashboardStrategyStatus, ...] = ()
    open_orders: tuple[Mapping[str, Any], ...] = ()
    pnl: Mapping[str, Any] | None = None
    risk_state: Mapping[str, Any] | None = None
    next_action: Mapping[str, Any] | None = None

    @property
    def exposure_mismatches(self) -> tuple[PaperDashboardExposureRow, ...]:
        return tuple(row for row in self.exposures if row.status != "matched")

    @property
    def failing_monitors(self) -> tuple[PaperDashboardMonitorStatus, ...]:
        return tuple(monitor for monitor in self.monitors if not monitor.passed)

    @property
    def active_strategies(self) -> tuple[PaperDashboardStrategyStatus, ...]:
        return tuple(strategy for strategy in self.strategies if strategy.active)

    @property
    def risk_status(self) -> str:
        return str((self.risk_state or {}).get("status", "unknown"))

    @property
    def ready_for_next_action(self) -> bool:
        risk_status = self.risk_status.lower()
        return not self.exposure_mismatches and not self.failing_monitors and risk_status not in BLOCKING_STATUSES

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "summary": {
                "ready_for_next_action": self.ready_for_next_action,
                "exposures": len(self.exposures),
                "exposure_mismatches": len(self.exposure_mismatches),
                "monitors": len(self.monitors),
                "failing_monitors": len(self.failing_monitors),
                "active_strategies": len(self.active_strategies),
                "open_orders": len(self.open_orders),
                "risk_status": self.risk_status,
                "next_action": (self.next_action or {}).get("name"),
            },
            "exposures": [row.to_dict() for row in self.exposures],
            "monitors": [monitor.to_dict() for monitor in self.monitors],
            "strategies": [strategy.to_dict() for strategy in self.strategies],
            "open_orders": [dict(order) for order in self.open_orders],
            "pnl": dict(self.pnl or {}),
            "risk_state": dict(self.risk_state or {}),
            "next_action": dict(self.next_action or {}),
        }


@dataclass(frozen=True)
class StrategyReviewPageReport:
    strategy_name: str
    enabled: bool
    state: str = "unknown"
    research_evidence: tuple[Mapping[str, Any], ...] = ()
    latest_trades: tuple[Mapping[str, Any], ...] = ()
    paper_scorecards: tuple[Mapping[str, Any], ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def failed_scorecards(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(card for card in self.paper_scorecards if str(card.get("status", "")).lower() in BLOCKING_STATUSES)

    @property
    def ready_for_enablement(self) -> bool:
        return self.enabled and self.state.lower() not in {"blocked", "quarantined"} and not self.failed_scorecards

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "enabled": self.enabled,
            "state": self.state,
            "summary": {
                "ready_for_enablement": self.ready_for_enablement,
                "research_evidence": len(self.research_evidence),
                "latest_trades": len(self.latest_trades),
                "paper_scorecards": len(self.paper_scorecards),
                "failed_scorecards": len(self.failed_scorecards),
            },
            "research_evidence": [dict(item) for item in self.research_evidence],
            "latest_trades": [dict(item) for item in self.latest_trades],
            "paper_scorecards": [dict(item) for item in self.paper_scorecards],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class LifecycleTimelineEvent:
    timestamp: str
    stage: str
    status: str
    description: str = ""
    evidence_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.status.lower() not in BLOCKING_STATUSES

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "status": self.status,
            "passed": self.passed,
            "description": self.description,
            "evidence_path": self.evidence_path,
        }


@dataclass(frozen=True)
class OrderLifecycleTimelineReport:
    order_id: str
    symbol: str
    side: str
    events: tuple[LifecycleTimelineEvent, ...] = ()

    @property
    def stages_seen(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(event.stage for event in self.events))

    @property
    def complete(self) -> bool:
        stages = set(self.stages_seen)
        return {"intent", "reconcile"}.issubset(stages) and all(event.passed for event in self.events)

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "summary": {
                "complete": self.complete,
                "events": len(self.events),
                "stages_seen": list(self.stages_seen),
                "failed_events": sum(1 for event in self.events if not event.passed),
            },
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True)
class PositionLifecycleTimelineReport:
    position_id: str
    symbol: str
    strategy: str
    events: tuple[LifecycleTimelineEvent, ...] = ()

    @property
    def open(self) -> bool:
        return not any(event.stage == "exit" and event.passed for event in self.events)

    @property
    def clean(self) -> bool:
        return all(event.passed for event in self.events)

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "summary": {
                "open": self.open,
                "clean": self.clean,
                "events": len(self.events),
                "failed_events": sum(1 for event in self.events if not event.passed),
            },
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True)
class PaperRunComparisonReport:
    generated_at: str
    runs: tuple[Mapping[str, Any], ...] = ()
    metric: str = "total_pnl"

    @property
    def ranked_runs(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            sorted(
                (dict(run) for run in self.runs),
                key=lambda run: to_float(run.get(self.metric)),
                reverse=True,
            )
        )

    @property
    def best_run(self) -> Mapping[str, Any] | None:
        return self.ranked_runs[0] if self.ranked_runs else None

    def to_dict(self) -> dict:
        best = self.best_run
        return {
            "generated_at": self.generated_at,
            "metric": self.metric,
            "summary": {
                "runs": len(self.runs),
                "best_run_id": best.get("run_id") if best else None,
                "best_metric_value": to_float(best.get(self.metric)) if best else None,
                "strategies": sorted({str(run.get("strategy", "unknown")) for run in self.runs}),
            },
            "runs": [dict(run) for run in self.ranked_runs],
        }


def build_paper_dashboard_report(
    exposures: Sequence[Mapping[str, Any]] = (),
    monitors: Sequence[Mapping[str, Any]] = (),
    strategies: Sequence[Mapping[str, Any]] = (),
    open_orders: Sequence[Mapping[str, Any]] = (),
    pnl: Mapping[str, Any] | None = None,
    risk_state: Mapping[str, Any] | None = None,
    next_action: Mapping[str, Any] | None = None,
    generated_at: str | datetime | None = None,
) -> PaperTradingDashboardReport:
    return PaperTradingDashboardReport(
        generated_at=utc_timestamp(generated_at),
        exposures=tuple(_exposure_row(row) for row in exposures),
        monitors=tuple(_monitor_status(row) for row in monitors),
        strategies=tuple(_strategy_status(row) for row in strategies),
        open_orders=tuple(dict(order) for order in open_orders),
        pnl=dict(pnl or {}),
        risk_state=dict(risk_state or {}),
        next_action=dict(next_action or {}),
    )


def build_strategy_review_report(
    strategy_name: str,
    enabled: bool,
    state: str = "unknown",
    research_evidence: Sequence[Mapping[str, Any]] = (),
    latest_trades: Sequence[Mapping[str, Any]] = (),
    paper_scorecards: Sequence[Mapping[str, Any]] = (),
    notes: Sequence[str] = (),
) -> StrategyReviewPageReport:
    return StrategyReviewPageReport(
        strategy_name=strategy_name,
        enabled=bool(enabled),
        state=state,
        research_evidence=tuple(dict(item) for item in research_evidence),
        latest_trades=tuple(dict(item) for item in latest_trades),
        paper_scorecards=tuple(dict(item) for item in paper_scorecards),
        notes=tuple(str(note) for note in notes),
    )


def build_order_lifecycle_timeline(
    order_id: str,
    symbol: str,
    side: str,
    events: Sequence[Mapping[str, Any]] = (),
) -> OrderLifecycleTimelineReport:
    return OrderLifecycleTimelineReport(
        order_id=order_id,
        symbol=symbol,
        side=side,
        events=tuple(_timeline_event(event) for event in events),
    )


def build_position_lifecycle_timeline(
    position_id: str,
    symbol: str,
    strategy: str,
    events: Sequence[Mapping[str, Any]] = (),
) -> PositionLifecycleTimelineReport:
    return PositionLifecycleTimelineReport(
        position_id=position_id,
        symbol=symbol,
        strategy=strategy,
        events=tuple(_timeline_event(event) for event in events),
    )


def build_paper_run_comparison_report(
    runs: Sequence[Mapping[str, Any]] = (),
    metric: str = "total_pnl",
    generated_at: str | datetime | None = None,
) -> PaperRunComparisonReport:
    return PaperRunComparisonReport(
        generated_at=utc_timestamp(generated_at),
        runs=tuple(dict(run) for run in runs),
        metric=metric,
    )


def render_paper_dashboard_html(report: PaperTradingDashboardReport) -> str:
    payload = report.to_dict()
    summary = payload["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Paper Trading Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #17202a; background: #f7f9fb; }}
    main {{ max-width: 1180px; margin: 0 auto; }}
    section {{ background: white; border: 1px solid #d8dee8; border-radius: 6px; padding: 16px; margin-bottom: 16px; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }}
    .metric {{ border: 1px solid #e2e7ef; border-radius: 4px; padding: 12px; background: #fbfcfe; }}
    .label {{ color: #5d6d7e; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e6ebf2; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f2f5f9; }}
    .pass {{ color: #127a36; font-weight: 700; }}
    .fail {{ color: #a12828; font-weight: 700; }}
    code {{ font-family: Consolas, monospace; font-size: 12px; }}
  </style>
</head>
<body>
<main>
  <h1>Paper Trading Dashboard</h1>
  <section>
    <div class="grid">
      {_metric("Ready", summary["ready_for_next_action"])}
      {_metric("Exposure Mismatches", summary["exposure_mismatches"])}
      {_metric("Failing Monitors", summary["failing_monitors"])}
      {_metric("Active Strategies", summary["active_strategies"])}
      {_metric("Open Orders", summary["open_orders"])}
      {_metric("Risk", summary["risk_status"])}
      {_metric("Next", summary.get("next_action") or "n/a")}
    </div>
  </section>
  <section><h2>Exposure</h2>{_table(payload["exposures"], ("symbol", "expected_quantity", "broker_quantity", "drift_quantity", "notional", "status"))}</section>
  <section><h2>Monitors</h2>{_table(payload["monitors"], ("name", "status", "reason", "source_artifact"))}</section>
  <section><h2>Strategies</h2>{_table(payload["strategies"], ("name", "enabled", "state", "current_signal", "scorecard_status"))}</section>
  <section><h2>Open Orders</h2>{_table(payload["open_orders"], ("symbol", "side", "quantity", "status", "submitted_at"))}</section>
</main>
</body>
</html>"""


def render_strategy_review_html(report: StrategyReviewPageReport) -> str:
    payload = report.to_dict()
    summary = payload["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(report.strategy_name)} Strategy Review</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #17202a; background: #f7f9fb; }}
    main {{ max-width: 1060px; margin: 0 auto; }}
    section {{ background: white; border: 1px solid #d8dee8; border-radius: 6px; padding: 16px; margin-bottom: 16px; }}
    h1, h2 {{ margin: 0 0 12px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e6ebf2; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f2f5f9; }}
  </style>
</head>
<body>
<main>
  <h1>{escape(report.strategy_name)} Strategy Review</h1>
  <section>
    <p>State: <strong>{escape(report.state)}</strong></p>
    <p>Ready for enablement: <strong>{escape(str(summary["ready_for_enablement"]))}</strong></p>
  </section>
  <section><h2>Research Evidence</h2>{_table(payload["research_evidence"], ("artifact", "status", "metric", "value"))}</section>
  <section><h2>Latest Trades</h2>{_table(payload["latest_trades"], ("timestamp", "symbol", "side", "quantity", "pnl"))}</section>
  <section><h2>Paper Scorecards</h2>{_table(payload["paper_scorecards"], ("artifact", "status", "reason"))}</section>
</main>
</body>
</html>"""


def write_paper_dashboard_report(report: PaperTradingDashboardReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_paper_dashboard_html(report: PaperTradingDashboardReport, path: str | Path) -> Path:
    return write_text_payload(render_paper_dashboard_html(report), path)


def write_strategy_review_report(report: StrategyReviewPageReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_strategy_review_html(report: StrategyReviewPageReport, path: str | Path) -> Path:
    return write_text_payload(render_strategy_review_html(report), path)


def write_order_lifecycle_timeline(report: OrderLifecycleTimelineReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_position_lifecycle_timeline(report: PositionLifecycleTimelineReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_paper_run_comparison_report(report: PaperRunComparisonReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def _exposure_row(row: Mapping[str, Any]) -> PaperDashboardExposureRow:
    return PaperDashboardExposureRow(
        symbol=str(row.get("symbol", "")),
        expected_quantity=to_float(row.get("expected_quantity", row.get("expected_qty", 0.0))),
        broker_quantity=to_float(row.get("broker_quantity", row.get("broker_qty", row.get("quantity", 0.0)))),
        notional=to_float(row.get("notional", row.get("market_value", 0.0))),
        tolerance=to_float(row.get("tolerance", 0.0)),
    )


def _monitor_status(row: Mapping[str, Any]) -> PaperDashboardMonitorStatus:
    return PaperDashboardMonitorStatus(
        name=str(row.get("name", row.get("check_id", ""))),
        status=str(row.get("status", "unknown")),
        reason=str(row.get("reason", "")),
        source_artifact=row.get("source_artifact") or row.get("artifact"),
    )


def _strategy_status(row: Mapping[str, Any]) -> PaperDashboardStrategyStatus:
    return PaperDashboardStrategyStatus(
        name=str(row.get("name", row.get("strategy", ""))),
        enabled=bool(row.get("enabled", False)),
        state=str(row.get("state", "unknown")),
        current_signal=str(row.get("current_signal", row.get("signal", "HOLD"))),
        scorecard_status=str(row.get("scorecard_status", row.get("status", "unknown"))),
        latest_artifact=row.get("latest_artifact") or row.get("artifact"),
    )


def _timeline_event(row: Mapping[str, Any]) -> LifecycleTimelineEvent:
    return LifecycleTimelineEvent(
        timestamp=str(row.get("timestamp", row.get("time", ""))),
        stage=str(row.get("stage", "")),
        status=str(row.get("status", "unknown")),
        description=str(row.get("description", row.get("reason", ""))),
        evidence_path=row.get("evidence_path") or row.get("artifact"),
    )


def _metric(label: str, value: Any) -> str:
    return f'<div class="metric"><div class="label">{escape(str(label))}</div><div class="value">{escape(str(value))}</div></div>'


def _table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return "<p>No records.</p>"
    header = "".join(f"<th>{escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body = []
    for row in rows:
        body.append(
            "<tr>"
            + "".join(f"<td>{escape(str(row.get(column, '')))}</td>" for column in columns)
            + "</tr>"
        )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"
