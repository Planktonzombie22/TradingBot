from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional

import pandas as pd

from ..streams.events import MarketDataEvent


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
    extreme_range_threshold: float = 0.50
    ohlc_tolerance_bps: float = 50.0
    stale_seconds: Optional[float] = None

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

        non_positive = (data[list(required)] <= 0).any(axis=1)
        if non_positive.any():
            report.add("ERROR", "NON_POSITIVE_PRICE", f"Detected {int(non_positive.sum())} bars with non-positive OHLC prices.")

        if "Volume" in data.columns and (data["Volume"] < 0).any():
            report.add("ERROR", "NEGATIVE_VOLUME", "Volume cannot be negative.")

        high_required = data[["Open", "Close", "Low"]].max(axis=1)
        low_required = data[["Open", "Close", "High"]].min(axis=1)
        upper_gap = (high_required - data["High"]) / data["Close"].abs()
        lower_gap = (data["Low"] - low_required) / data["Close"].abs()
        bound_gap = pd.concat([upper_gap, lower_gap], axis=1).max(axis=1).fillna(0.0)
        invalid_ohlc = bound_gap > 0
        material_invalid_ohlc = bound_gap > (self.ohlc_tolerance_bps / 10_000)
        if material_invalid_ohlc.any():
            report.add("ERROR", "INVALID_OHLC", "High/low bounds are materially inconsistent with open/close.")
        elif invalid_ohlc.any():
            report.add("WARNING", "ADJUSTED_OHLC_DRIFT", f"Detected {int(invalid_ohlc.sum())} bars with minor adjusted OHLC bound drift.")

        extreme_range = ((data["High"] - data["Low"]) / data["Close"].abs()) > self.extreme_range_threshold
        if extreme_range.any():
            report.add("WARNING", "EXTREME_RANGE", f"Detected {int(extreme_range.sum())} bars with unusually wide high/low ranges.")

        self._check_time_gaps(data, report)
        self._check_split_spikes(data, report)
        return report

    def validate_events(self, events: Iterable[MarketDataEvent], now: Optional[datetime] = None) -> DataQualityReport:
        report = DataQualityReport()
        now = now or datetime.now(timezone.utc)
        last_timestamp_by_symbol: dict[str, datetime] = {}

        for event in events:
            if event.bar is None:
                continue
            bar_report = self.validate_ohlcv(
                pd.DataFrame(
                    {
                        "Open": [event.bar.open],
                        "High": [event.bar.high],
                        "Low": [event.bar.low],
                        "Close": [event.bar.close],
                        "Volume": [event.bar.volume],
                    },
                    index=pd.DatetimeIndex([pd.Timestamp(event.timestamp)]),
                )
            )
            for issue in bar_report.issues:
                report.add(issue.severity, issue.code, f"{event.symbol}: {issue.message}")

            previous = last_timestamp_by_symbol.get(event.symbol)
            if previous is not None and event.timestamp <= previous:
                report.add("ERROR", "OUT_OF_ORDER_EVENT", f"{event.symbol} event timestamp is not increasing.")
            last_timestamp_by_symbol[event.symbol] = event.timestamp

            if self.stale_seconds is not None:
                event_timestamp = event.timestamp.astimezone(timezone.utc) if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
                if (now - event_timestamp).total_seconds() > self.stale_seconds:
                    report.add("ERROR", "STALE_EVENT", f"{event.symbol} event is stale.")

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
