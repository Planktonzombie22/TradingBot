from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import status_blocking, status_passed, to_float, utc_timestamp, write_json_payload


@dataclass(frozen=True)
class ChartSeriesPoint:
    series: str
    x: str
    y: float
    metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict:
        return {"series": self.series, "x": self.x, "y": self.y, "metadata": dict(self.metadata or {})}


@dataclass(frozen=True)
class SlippageFillQualityReport:
    generated_at: str
    fills: tuple[Mapping[str, Any], ...] = ()

    @property
    def average_slippage_bps(self) -> float:
        return _average(row.get("slippage_bps") for row in self.fills)

    @property
    def chart_points(self) -> tuple[ChartSeriesPoint, ...]:
        return tuple(
            ChartSeriesPoint(
                series=_series_key(row, ("strategy", "symbol", "order_type")),
                x=str(row.get("timestamp") or row.get("time_of_day") or ""),
                y=to_float(row.get("slippage_bps")),
                metadata={key: row.get(key) for key in ("symbol", "strategy", "order_type", "side", "quantity", "effective_spread_bps")},
            )
            for row in self.fills
        )

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "summary": {
                "fills": len(self.fills),
                "average_slippage_bps": self.average_slippage_bps,
                "max_slippage_bps": max((to_float(row.get("slippage_bps")) for row in self.fills), default=0.0),
                "symbols": sorted({str(row.get("symbol", "unknown")) for row in self.fills}),
                "strategies": sorted({str(row.get("strategy", "unknown")) for row in self.fills}),
            },
            "fills": [dict(row) for row in self.fills],
            "chart_points": [point.to_dict() for point in self.chart_points],
        }


@dataclass(frozen=True)
class DataDriftChartReport:
    generated_at: str
    rows: tuple[Mapping[str, Any], ...] = ()
    max_close_diff_bps: float = 10.0

    @property
    def breaches(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.rows if abs(to_float(row.get("close_diff_bps"))) > self.max_close_diff_bps or status_blocking(row.get("status")))

    @property
    def chart_points(self) -> tuple[ChartSeriesPoint, ...]:
        return tuple(
            ChartSeriesPoint(
                series=_series_key(row, ("provider", "symbol")),
                x=str(row.get("timestamp", "")),
                y=to_float(row.get("close_diff_bps")),
                metadata={key: row.get(key) for key in ("provider", "comparison_provider", "symbol", "volume_diff_pct", "status")},
            )
            for row in self.rows
        )

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "summary": {
                "rows": len(self.rows),
                "breaches": len(self.breaches),
                "max_close_diff_bps": max((abs(to_float(row.get("close_diff_bps"))) for row in self.rows), default=0.0),
                "providers": sorted({str(row.get("provider", "unknown")) for row in self.rows}),
            },
            "rows": [dict(row) for row in self.rows],
            "chart_points": [point.to_dict() for point in self.chart_points],
        }


@dataclass(frozen=True)
class ReadinessTrendReport:
    generated_at: str
    snapshots: tuple[Mapping[str, Any], ...] = ()

    @property
    def latest(self) -> Mapping[str, Any] | None:
        return self.snapshots[-1] if self.snapshots else None

    @property
    def trend(self) -> str:
        if len(self.snapshots) < 2:
            return "flat"
        first = to_float(self.snapshots[0].get("readiness_score"))
        latest = to_float(self.snapshots[-1].get("readiness_score"))
        if latest > first:
            return "improving"
        if latest < first:
            return "regressing"
        return "flat"

    def to_dict(self) -> dict:
        latest = dict(self.latest or {})
        return {
            "generated_at": self.generated_at,
            "summary": {
                "snapshots": len(self.snapshots),
                "trend": self.trend,
                "latest_score": to_float(latest.get("readiness_score")),
                "latest_missing": len(latest.get("missing_required", [])),
                "latest_failed": len(latest.get("failed_required", [])),
                "latest_stale": len(latest.get("stale_check_ids", [])),
            },
            "snapshots": [dict(row) for row in self.snapshots],
            "chart_points": [
                ChartSeriesPoint("readiness_score", str(row.get("timestamp", "")), to_float(row.get("readiness_score"))).to_dict()
                for row in self.snapshots
            ],
        }


@dataclass(frozen=True)
class PaperPnlAttributionChartReport:
    generated_at: str
    rows: tuple[Mapping[str, Any], ...] = ()

    @property
    def grouped_totals(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for row in self.rows:
            key = _series_key(row, ("strategy", "regime", "symbol", "holding_period"))
            totals[key] = totals.get(key, 0.0) + to_float(row.get("pnl"))
        return totals

    def to_dict(self) -> dict:
        totals = self.grouped_totals
        return {
            "generated_at": self.generated_at,
            "summary": {
                "rows": len(self.rows),
                "total_pnl": sum(totals.values()),
                "positive_groups": sum(1 for value in totals.values() if value > 0),
                "negative_groups": sum(1 for value in totals.values() if value < 0),
            },
            "rows": [dict(row) for row in self.rows],
            "grouped_totals": totals,
            "chart_points": [ChartSeriesPoint(key, key, value).to_dict() for key, value in sorted(totals.items())],
        }


@dataclass(frozen=True)
class PaperReviewSummaryReport:
    generated_at: str
    period: str
    reports: tuple[Mapping[str, Any], ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def blocking_reports(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.reports if status_blocking(row.get("status")) or row.get("blocked"))

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "period": self.period,
            "summary": {
                "reports": len(self.reports),
                "blocking_reports": len(self.blocking_reports),
                "orders_submitted": sum(int(to_float(row.get("orders_submitted"))) for row in self.reports),
                "warnings": sum(len(row.get("warnings", [])) for row in self.reports),
            },
            "reports": [dict(row) for row in self.reports],
            "blocking_reports": [dict(row) for row in self.blocking_reports],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class AnomalyHighlightReport:
    generated_at: str
    anomalies: tuple[Mapping[str, Any], ...] = ()

    @property
    def blocking_anomalies(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.anomalies if str(row.get("severity", "")).lower() in {"critical", "high"} or status_blocking(row.get("status")))

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "summary": {"anomalies": len(self.anomalies), "blocking_anomalies": len(self.blocking_anomalies)},
            "anomalies": [dict(row) for row in self.anomalies],
            "blocking_anomalies": [dict(row) for row in self.blocking_anomalies],
        }


@dataclass(frozen=True)
class OperatorDecisionLogReport:
    generated_at: str
    decisions: tuple[Mapping[str, Any], ...] = ()

    @property
    def approvals(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.decisions if bool(row.get("approved")))

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "summary": {"decisions": len(self.decisions), "approvals": len(self.approvals)},
            "decisions": [dict(row) for row in self.decisions],
        }


@dataclass(frozen=True)
class ReleaseCandidateSignoffReport:
    generated_at: str
    code_version: str
    config_hash: str
    checks: tuple[Mapping[str, Any], ...] = ()
    operator_approved: bool = False

    @property
    def blockers(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.checks if not status_passed(row.get("status")))

    @property
    def ready_for_release(self) -> bool:
        return self.operator_approved and not self.blockers

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "code_version": self.code_version,
            "config_hash": self.config_hash,
            "summary": {
                "ready_for_release": self.ready_for_release,
                "operator_approved": self.operator_approved,
                "checks": len(self.checks),
                "blockers": len(self.blockers),
            },
            "checks": [dict(row) for row in self.checks],
            "blockers": [dict(row) for row in self.blockers],
        }


@dataclass(frozen=True)
class WhyNoLiveYetReport:
    generated_at: str
    gates: tuple[Mapping[str, Any], ...] = ()

    @property
    def blockers(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.gates if not status_passed(row.get("status")))

    @property
    def live_unlocked(self) -> bool:
        return not self.blockers and bool(self.gates)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "summary": {"live_unlocked": self.live_unlocked, "gates": len(self.gates), "blockers": len(self.blockers)},
            "gates": [dict(row) for row in self.gates],
            "blockers": [dict(row) for row in self.blockers],
            "message": "live_ready" if self.live_unlocked else "live remains locked until every blocker has current real evidence",
        }


@dataclass(frozen=True)
class LiveReadinessScoreReport:
    generated_at: str
    gates: tuple[Mapping[str, Any], ...] = ()

    @property
    def live_evidence_gates(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.gates if str(row.get("evidence_type", "")).lower() == "live")

    @property
    def satisfied_live_gates(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(row for row in self.live_evidence_gates if status_passed(row.get("status")))

    @property
    def score(self) -> float:
        if not self.gates:
            return 0.0
        return len(self.satisfied_live_gates) / len(self.gates)

    @property
    def ready(self) -> bool:
        return bool(self.gates) and len(self.satisfied_live_gates) == len(self.gates)

    def to_dict(self) -> dict:
        simulated_only = [dict(row) for row in self.gates if str(row.get("evidence_type", "")).lower() != "live" and status_passed(row.get("status"))]
        return {
            "generated_at": self.generated_at,
            "summary": {
                "score": self.score,
                "ready": self.ready,
                "gates": len(self.gates),
                "satisfied_live_gates": len(self.satisfied_live_gates),
                "simulated_only_passes": len(simulated_only),
            },
            "gates": [dict(row) for row in self.gates],
            "simulated_only_passes": simulated_only,
            "blockers": [dict(row) for row in self.gates if row not in self.satisfied_live_gates],
        }


def build_slippage_fill_quality_report(fills: Sequence[Mapping[str, Any]] = (), generated_at: str | datetime | None = None) -> SlippageFillQualityReport:
    return SlippageFillQualityReport(utc_timestamp(generated_at), tuple(dict(row) for row in fills))


def build_data_drift_chart_report(rows: Sequence[Mapping[str, Any]] = (), max_close_diff_bps: float = 10.0, generated_at: str | datetime | None = None) -> DataDriftChartReport:
    return DataDriftChartReport(utc_timestamp(generated_at), tuple(dict(row) for row in rows), max_close_diff_bps)


def build_readiness_trend_report(snapshots: Sequence[Mapping[str, Any]] = (), generated_at: str | datetime | None = None) -> ReadinessTrendReport:
    return ReadinessTrendReport(utc_timestamp(generated_at), tuple(dict(row) for row in snapshots))


def build_paper_pnl_attribution_chart_report(rows: Sequence[Mapping[str, Any]] = (), generated_at: str | datetime | None = None) -> PaperPnlAttributionChartReport:
    return PaperPnlAttributionChartReport(utc_timestamp(generated_at), tuple(dict(row) for row in rows))


def build_paper_review_summary_report(period: str, reports: Sequence[Mapping[str, Any]] = (), notes: Sequence[str] = (), generated_at: str | datetime | None = None) -> PaperReviewSummaryReport:
    return PaperReviewSummaryReport(utc_timestamp(generated_at), period, tuple(dict(row) for row in reports), tuple(str(note) for note in notes))


def build_anomaly_highlight_report(anomalies: Sequence[Mapping[str, Any]] = (), generated_at: str | datetime | None = None) -> AnomalyHighlightReport:
    return AnomalyHighlightReport(utc_timestamp(generated_at), tuple(dict(row) for row in anomalies))


def build_operator_decision_log_report(decisions: Sequence[Mapping[str, Any]] = (), generated_at: str | datetime | None = None) -> OperatorDecisionLogReport:
    return OperatorDecisionLogReport(utc_timestamp(generated_at), tuple(dict(row) for row in decisions))


def build_release_candidate_signoff_report(
    code_version: str,
    config_hash: str,
    checks: Sequence[Mapping[str, Any]] = (),
    operator_approved: bool = False,
    generated_at: str | datetime | None = None,
) -> ReleaseCandidateSignoffReport:
    return ReleaseCandidateSignoffReport(utc_timestamp(generated_at), code_version, config_hash, tuple(dict(row) for row in checks), operator_approved)


def build_why_no_live_yet_report(gates: Sequence[Mapping[str, Any]] = (), generated_at: str | datetime | None = None) -> WhyNoLiveYetReport:
    return WhyNoLiveYetReport(utc_timestamp(generated_at), tuple(dict(row) for row in gates))


def build_live_readiness_score_report(gates: Sequence[Mapping[str, Any]] = (), generated_at: str | datetime | None = None) -> LiveReadinessScoreReport:
    return LiveReadinessScoreReport(utc_timestamp(generated_at), tuple(dict(row) for row in gates))


def write_slippage_fill_quality_report(report: SlippageFillQualityReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_data_drift_chart_report(report: DataDriftChartReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_readiness_trend_report(report: ReadinessTrendReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_paper_pnl_attribution_chart_report(report: PaperPnlAttributionChartReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_paper_review_summary_report(report: PaperReviewSummaryReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_anomaly_highlight_report(report: AnomalyHighlightReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_operator_decision_log_report(report: OperatorDecisionLogReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_release_candidate_signoff_report(report: ReleaseCandidateSignoffReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_why_no_live_yet_report(report: WhyNoLiveYetReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def write_live_readiness_score_report(report: LiveReadinessScoreReport, path: str | Path) -> Path:
    return write_json_payload(report.to_dict(), path)


def _series_key(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    return "|".join(str(row.get(key, "unknown")) for key in keys)


def _average(values: Sequence[Any]) -> float:
    numbers = [to_float(value) for value in values]
    return sum(numbers) / len(numbers) if numbers else 0.0
