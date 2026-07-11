from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

import pandas as pd

from .normalization import OHLCV_COLUMNS, normalize_ohlcv_frame
from .validation import DataQualityValidator


@dataclass(frozen=True)
class DataSourceSnapshot:
    provider: str
    symbol: str
    data: pd.DataFrame
    adjustment_mode: str = "unknown"
    captured_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def normalized(self) -> pd.DataFrame:
        normalized = normalize_ohlcv_frame(self.data)
        if normalized.empty:
            return normalized
        index = pd.DatetimeIndex(normalized.index)
        if index.tz is None:
            index = index.tz_localize(timezone.utc)
        else:
            index = index.tz_convert(timezone.utc)
        normalized.index = index
        return normalized


@dataclass(frozen=True)
class DataDriftPolicy:
    max_close_drift_bps: float = 20.0
    max_ohlc_drift_bps: float = 50.0
    max_staleness_seconds: float | None = None
    adjusted_price_warning_bps: float = 10.0
    corporate_action_ratio_tolerance: float = 0.03
    require_overlap: bool = True


@dataclass(frozen=True)
class DataDriftIssue:
    severity: str
    code: str
    message: str
    provider: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class DataDriftReport:
    symbol: str
    primary_provider: str
    comparison_provider: str
    overlap_count: int
    max_close_drift_bps: float
    max_ohlc_drift_bps: float
    issues: tuple[DataDriftIssue, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "ERROR" for issue in self.issues)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "primary_provider": self.primary_provider,
            "comparison_provider": self.comparison_provider,
            "overlap_count": self.overlap_count,
            "max_close_drift_bps": self.max_close_drift_bps,
            "max_ohlc_drift_bps": self.max_ohlc_drift_bps,
            "passed": self.passed,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def compare_live_data_sources(
    primary: DataSourceSnapshot,
    comparison: DataSourceSnapshot,
    policy: DataDriftPolicy | None = None,
    now: datetime | None = None,
) -> DataDriftReport:
    policy = policy or DataDriftPolicy()
    now = _utc(now or datetime.now(timezone.utc))
    primary_data = primary.normalized()
    comparison_data = comparison.normalized()
    issues: list[DataDriftIssue] = []

    _append_quality_issues(primary, primary_data, issues)
    _append_quality_issues(comparison, comparison_data, issues)
    _append_staleness_issue(primary, primary_data, policy, now, issues)
    _append_staleness_issue(comparison, comparison_data, policy, now, issues)
    _append_adjustment_issue(primary, comparison, issues)

    overlap = primary_data.index.intersection(comparison_data.index)
    if overlap.empty:
        if policy.require_overlap:
            issues.append(
                DataDriftIssue(
                    "ERROR",
                    "NO_OVERLAP",
                    "No overlapping timestamps between provider snapshots.",
                )
            )
        return DataDriftReport(
            symbol=primary.symbol,
            primary_provider=primary.provider,
            comparison_provider=comparison.provider,
            overlap_count=0,
            max_close_drift_bps=0.0,
            max_ohlc_drift_bps=0.0,
            issues=tuple(issues),
        )

    primary_overlap = primary_data.loc[overlap]
    comparison_overlap = comparison_data.loc[overlap]
    close_drift = _drift_bps(primary_overlap["Close"], comparison_overlap["Close"])
    ohlc_drift = pd.concat(
        [_drift_bps(primary_overlap[column], comparison_overlap[column]) for column in ("Open", "High", "Low", "Close")],
        axis=1,
    ).max(axis=1)
    max_close = float(close_drift.max()) if not close_drift.empty else 0.0
    max_ohlc = float(ohlc_drift.max()) if not ohlc_drift.empty else 0.0

    _append_threshold_issues(close_drift, "CLOSE_DRIFT", policy.max_close_drift_bps, primary, comparison, issues)
    _append_threshold_issues(ohlc_drift, "OHLC_DRIFT", policy.max_ohlc_drift_bps, primary, comparison, issues)
    _append_corporate_action_issue(primary_overlap, comparison_overlap, primary, comparison, policy, issues)

    return DataDriftReport(
        symbol=primary.symbol,
        primary_provider=primary.provider,
        comparison_provider=comparison.provider,
        overlap_count=len(overlap),
        max_close_drift_bps=max_close,
        max_ohlc_drift_bps=max_ohlc,
        issues=tuple(issues),
    )


def compare_many_live_data_sources(
    primary: DataSourceSnapshot,
    comparisons: list[DataSourceSnapshot],
    policy: DataDriftPolicy | None = None,
    now: datetime | None = None,
) -> list[DataDriftReport]:
    return [compare_live_data_sources(primary, comparison, policy, now) for comparison in comparisons]


def _append_quality_issues(snapshot: DataSourceSnapshot, data: pd.DataFrame, issues: list[DataDriftIssue]) -> None:
    report = DataQualityValidator().validate_ohlcv(data)
    for issue in report.issues:
        issues.append(
            DataDriftIssue(
                issue.severity,
                f"{snapshot.provider}_{issue.code}",
                issue.message,
                provider=snapshot.provider,
            )
        )


def _append_staleness_issue(
    snapshot: DataSourceSnapshot,
    data: pd.DataFrame,
    policy: DataDriftPolicy,
    now: datetime,
    issues: list[DataDriftIssue],
) -> None:
    if policy.max_staleness_seconds is None or data.empty:
        return
    last_timestamp = _utc(data.index.max().to_pydatetime())
    age = (now - last_timestamp).total_seconds()
    if age > policy.max_staleness_seconds:
        issues.append(
            DataDriftIssue(
                "ERROR",
                "STALE_PROVIDER",
                f"{snapshot.provider} latest bar is stale by {round(age, 2)} seconds.",
                provider=snapshot.provider,
                timestamp=last_timestamp.isoformat(),
            )
        )


def _append_adjustment_issue(
    primary: DataSourceSnapshot,
    comparison: DataSourceSnapshot,
    issues: list[DataDriftIssue],
) -> None:
    if primary.adjustment_mode == comparison.adjustment_mode:
        return
    issues.append(
        DataDriftIssue(
            "WARNING",
            "ADJUSTMENT_MODE_MISMATCH",
            f"{primary.provider} uses {primary.adjustment_mode} prices while {comparison.provider} uses {comparison.adjustment_mode}.",
        )
    )


def _append_threshold_issues(
    drift: pd.Series,
    code: str,
    threshold: float,
    primary: DataSourceSnapshot,
    comparison: DataSourceSnapshot,
    issues: list[DataDriftIssue],
) -> None:
    breached = drift[drift > threshold]
    for timestamp, value in breached.items():
        issues.append(
            DataDriftIssue(
                "ERROR",
                code,
                f"{primary.provider} and {comparison.provider} drift is {round(float(value), 2)} bps.",
                timestamp=pd.Timestamp(timestamp).isoformat(),
            )
        )


def _append_corporate_action_issue(
    primary: pd.DataFrame,
    comparison: pd.DataFrame,
    primary_snapshot: DataSourceSnapshot,
    comparison_snapshot: DataSourceSnapshot,
    policy: DataDriftPolicy,
    issues: list[DataDriftIssue],
) -> None:
    ratios = primary["Close"] / comparison["Close"].replace(0, pd.NA)
    candidate_ratios = (0.25, 0.333333, 0.5, 2.0, 3.0, 4.0)
    for timestamp, ratio in ratios.dropna().items():
        value = float(ratio)
        if any(abs(value - candidate) / candidate <= policy.corporate_action_ratio_tolerance for candidate in candidate_ratios):
            issues.append(
                DataDriftIssue(
                    "ERROR",
                    "POSSIBLE_CORPORATE_ACTION_MISMATCH",
                    f"{primary_snapshot.provider} and {comparison_snapshot.provider} close prices differ by a split-like ratio.",
                    timestamp=pd.Timestamp(timestamp).isoformat(),
                )
            )


def _drift_bps(primary: pd.Series, comparison: pd.Series) -> pd.Series:
    denominator = primary.abs().replace(0, pd.NA)
    return ((primary - comparison).abs() / denominator * 10_000).fillna(0.0)


def _utc(timestamp: datetime) -> datetime:
    return timestamp.astimezone(timezone.utc) if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
