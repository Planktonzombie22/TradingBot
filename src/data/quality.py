from dataclasses import dataclass, field
from typing import List

import pandas as pd


@dataclass(frozen=True)
class DataQualityIssue:
    severity: str
    code: str
    message: str


@dataclass
class DataQualityReport:
    issues: List[DataQualityIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "ERROR" for issue in self.issues)

    def add(self, severity: str, code: str, message: str) -> None:
        self.issues.append(DataQualityIssue(severity, code, message))


@dataclass(frozen=True)
class DataQualityValidator:
    max_gap_multiplier: float = 3.0
    split_spike_threshold: float = 0.40

    def validate_ohlcv(self, data: pd.DataFrame) -> DataQualityReport:
        report = DataQualityReport()
        required = {"Open", "High", "Low", "Close"}
        missing = required.difference(data.columns)
        if missing:
            report.add("ERROR", "MISSING_COLUMNS", f"Missing OHLC columns: {sorted(missing)}")
            return report

        if data.empty:
            report.add("ERROR", "EMPTY_DATA", "Data frame is empty.")
            return report

        if not data.index.is_monotonic_increasing:
            report.add("ERROR", "UNSORTED_INDEX", "Data index must be sorted ascending.")

        if data.index.has_duplicates:
            report.add("ERROR", "DUPLICATE_INDEX", "Data index contains duplicate timestamps.")

        null_counts = data[list(required)].isna().sum()
        if null_counts.any():
            report.add("ERROR", "MISSING_BARS", f"OHLC data contains null values: {null_counts.to_dict()}")

        invalid_ohlc = (data["High"] < data[["Open", "Close", "Low"]].max(axis=1)) | (
            data["Low"] > data[["Open", "Close", "High"]].min(axis=1)
        )
        if invalid_ohlc.any():
            report.add("ERROR", "INVALID_OHLC", "High/low bounds are inconsistent with open/close.")

        self._check_time_gaps(data, report)
        self._check_split_spikes(data, report)
        return report

    def _check_time_gaps(self, data: pd.DataFrame, report: DataQualityReport) -> None:
        if len(data.index) < 3 or not isinstance(data.index, pd.DatetimeIndex):
            return
        diffs = data.index.to_series().diff().dropna()
        median_gap = diffs.median()
        if median_gap <= pd.Timedelta(0):
            return
        large_gaps = diffs[diffs > median_gap * self.max_gap_multiplier]
        if not large_gaps.empty:
            report.add("WARNING", "TIME_GAPS", f"Detected {len(large_gaps)} unusually large timestamp gaps.")

    def _check_split_spikes(self, data: pd.DataFrame, report: DataQualityReport) -> None:
        returns = data["Close"].pct_change().abs().dropna()
        spikes = returns[returns > self.split_spike_threshold]
        if not spikes.empty:
            report.add("WARNING", "SPLIT_SPIKE", f"Detected {len(spikes)} large close-to-close jumps.")
