import json
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode

from src.config import AlpacaConfig
from src.data.runtime.calendar import MarketSessionCalendar, MarketSessionPolicy
from src.utils.alpaca_rest import AlpacaRestClient


ASSET_CLASS_CALENDAR = {
    "crypto": "crypto_24_7",
    "equity": "us_equity_regular",
    "stock": "us_equity_regular",
    "etf": "us_equity_regular",
    "bond": "us_fixed_income_regular",
    "fund": "fund_regular",
}


@dataclass(frozen=True)
class LiveMarketSnapshot:
    symbol: str
    provider: str
    latest_trade_price: float | None = None
    latest_trade_timestamp: str | None = None
    bid_price: float | None = None
    ask_price: float | None = None
    quote_timestamp: str | None = None

    @property
    def mid_price(self) -> float | None:
        if self.bid_price is None or self.ask_price is None:
            return None
        return (self.bid_price + self.ask_price) / 2.0

    @property
    def spread(self) -> float | None:
        if self.bid_price is None or self.ask_price is None:
            return None
        return self.ask_price - self.bid_price

    @property
    def spread_bps(self) -> float | None:
        if self.spread is None or not self.mid_price:
            return None
        return (self.spread / self.mid_price) * 10_000.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "provider": self.provider,
            "latest_trade_price": self.latest_trade_price,
            "latest_trade_timestamp": self.latest_trade_timestamp,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "quote_timestamp": self.quote_timestamp,
            "mid_price": self.mid_price,
            "spread": self.spread,
            "spread_bps": self.spread_bps,
        }


@dataclass(frozen=True)
class LiveMarketSnapshotReport:
    snapshots: tuple[LiveMarketSnapshot, ...]
    observed_at: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(snapshot.latest_trade_price is not None or snapshot.mid_price is not None for snapshot in self.snapshots)

    @property
    def reason(self) -> str:
        return "market_snapshots_captured" if self.passed else "missing_market_snapshot_prices"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "observed_at": self.observed_at,
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class QuoteSpreadExecutionAnalysis:
    symbol: str
    side: str
    fill_price: float | None
    reference_mid_price: float | None
    spread_bps: float | None
    effective_spread_bps: float | None
    adverse_selection_bps: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "fill_price": self.fill_price,
            "reference_mid_price": self.reference_mid_price,
            "spread_bps": self.spread_bps,
            "effective_spread_bps": self.effective_spread_bps,
            "adverse_selection_bps": self.adverse_selection_bps,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QuoteSpreadReport:
    analyses: tuple[QuoteSpreadExecutionAnalysis, ...]
    max_spread_bps: float = 25.0
    max_effective_spread_bps: float = 35.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(analysis.passed for analysis in self.analyses)

    @property
    def reason(self) -> str:
        if self.passed:
            return "quote_spread_checks_passed"
        return next(analysis.reason for analysis in self.analyses if not analysis.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_spread_bps": self.max_spread_bps,
            "max_effective_spread_bps": self.max_effective_spread_bps,
            "analyses": [analysis.to_dict() for analysis in self.analyses],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class DataFreshnessStatus:
    symbol: str
    source: str
    timestamp: str | None
    age_seconds: float | None
    max_age_seconds: float
    asset_class: str = "equity"

    @property
    def passed(self) -> bool:
        return self.age_seconds is not None and self.age_seconds <= self.max_age_seconds

    @property
    def reason(self) -> str:
        if self.timestamp is None:
            return "missing_timestamp"
        return "fresh" if self.passed else "stale_data"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "timestamp": self.timestamp,
            "age_seconds": self.age_seconds,
            "max_age_seconds": self.max_age_seconds,
            "asset_class": self.asset_class,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DataFreshnessReport:
    statuses: tuple[DataFreshnessStatus, ...]
    observed_at: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(status.passed for status in self.statuses)

    @property
    def reason(self) -> str:
        if self.passed:
            return "data_freshness_passed"
        return next(status.reason for status in self.statuses if not status.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "observed_at": self.observed_at,
            "statuses": [status.to_dict() for status in self.statuses],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class DataSourceCandidate:
    provider: str
    freshness_passed: bool
    schema_passed: bool
    drift_bps: float | None = None
    available: bool = True

    @property
    def passed(self) -> bool:
        return self.available and self.freshness_passed and self.schema_passed

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "available": self.available,
            "freshness_passed": self.freshness_passed,
            "schema_passed": self.schema_passed,
            "drift_bps": self.drift_bps,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class DataSourceArbitrationReport:
    symbol: str
    selected_provider: str | None
    candidates: tuple[DataSourceCandidate, ...]
    max_drift_bps: float = 50.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.selected_provider is not None

    @property
    def reason(self) -> str:
        return "data_source_selected" if self.passed else "no_viable_data_source"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "symbol": self.symbol,
            "selected_provider": self.selected_provider,
            "max_drift_bps": self.max_drift_bps,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class AssetClassMetadata:
    symbol: str
    asset_class: str
    calendar_policy: str
    fractional_trading: bool = False
    tradable: bool = False
    shortable: bool = False
    easy_to_borrow: bool = False
    marginable: bool = False
    maintenance_margin: float | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "calendar_policy": self.calendar_policy,
            "fractional_trading": self.fractional_trading,
            "tradable": self.tradable,
            "shortable": self.shortable,
            "easy_to_borrow": self.easy_to_borrow,
            "marginable": self.marginable,
            "maintenance_margin": self.maintenance_margin,
        }


@dataclass(frozen=True)
class AssetClassMetadataReport:
    assets: tuple[AssetClassMetadata, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(asset.tradable for asset in self.assets)

    @property
    def reason(self) -> str:
        return "asset_metadata_ready" if self.passed else "non_tradable_assets_present"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "assets": [asset.to_dict() for asset in self.assets],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class SymbolCapabilityGate:
    symbol: str
    tradable: bool
    fractional_allowed: bool
    short_allowed: bool
    margin_allowed: bool
    reason: str = "passed"

    @property
    def passed(self) -> bool:
        return self.tradable and self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "passed": self.passed,
            "tradable": self.tradable,
            "fractional_allowed": self.fractional_allowed,
            "short_allowed": self.short_allowed,
            "margin_allowed": self.margin_allowed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SymbolCapabilityReport:
    gates: tuple[SymbolCapabilityGate, ...]
    require_fractional: bool = False
    require_short: bool = False
    require_margin: bool = False
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def reason(self) -> str:
        if self.passed:
            return "symbol_capabilities_passed"
        return next(gate.reason for gate in self.gates if not gate.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "require_fractional": self.require_fractional,
            "require_short": self.require_short,
            "require_margin": self.require_margin,
            "gates": [gate.to_dict() for gate in self.gates],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class MultiTimeframeDataStatus:
    symbol: str
    timeframe: str
    rows: int
    required_rows: int
    last_timestamp: str | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "rows": self.rows,
            "required_rows": self.required_rows,
            "last_timestamp": self.last_timestamp,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MultiTimeframeDataReport:
    statuses: tuple[MultiTimeframeDataStatus, ...]
    required_timeframes: tuple[str, ...]
    observed_at: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(status.passed for status in self.statuses)

    @property
    def reason(self) -> str:
        if self.passed:
            return "multi_timeframe_data_ready"
        return next(status.reason for status in self.statuses if not status.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "observed_at": self.observed_at,
            "required_timeframes": list(self.required_timeframes),
            "statuses": [status.to_dict() for status in self.statuses],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class CorporateActionReplayCase:
    symbol: str
    action_type: str
    raw_price: float | None
    adjusted_price: float | None
    raw_quantity: float | None
    adjusted_quantity: float | None
    expected_ratio: float | None
    dividend_amount: float | None
    paper_quantity: float | None
    backtest_quantity: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action_type": self.action_type,
            "raw_price": self.raw_price,
            "adjusted_price": self.adjusted_price,
            "raw_quantity": self.raw_quantity,
            "adjusted_quantity": self.adjusted_quantity,
            "expected_ratio": self.expected_ratio,
            "dividend_amount": self.dividend_amount,
            "paper_quantity": self.paper_quantity,
            "backtest_quantity": self.backtest_quantity,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CorporateActionReplayReport:
    cases: tuple[CorporateActionReplayCase, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(case.passed for case in self.cases)

    @property
    def reason(self) -> str:
        if self.passed:
            return "corporate_action_replay_passed"
        return next(case.reason for case in self.cases if not case.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "cases": [case.to_dict() for case in self.cases],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class MarketCalendarRegressionCase:
    name: str
    timestamp: str
    expected_session: str
    actual_session: str
    expected_tradable: bool
    actual_tradable: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "expected_session": self.expected_session,
            "actual_session": self.actual_session,
            "expected_tradable": self.expected_tradable,
            "actual_tradable": self.actual_tradable,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MarketCalendarRegressionReport:
    cases: tuple[MarketCalendarRegressionCase, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(case.passed for case in self.cases)

    @property
    def reason(self) -> str:
        if self.passed:
            return "market_calendar_regressions_passed"
        return next(case.reason for case in self.cases if not case.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "cases": [case.to_dict() for case in self.cases],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class DataOutageSimulationReport:
    historical_available: bool
    live_trade_available: bool
    live_quote_available: bool
    cached_snapshot_available: bool = False
    allow_cached_fallback: bool = False
    submission_allowed: bool = False
    downgraded_to_cached_data: bool = False
    reason: str = "live_data_unavailable_submission_blocked"
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        live_ready = self.live_trade_available and self.live_quote_available
        if live_ready:
            return self.submission_allowed and not self.downgraded_to_cached_data
        if self.allow_cached_fallback and self.cached_snapshot_available:
            return self.submission_allowed and self.downgraded_to_cached_data
        return not self.submission_allowed

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "historical_available": self.historical_available,
            "live_trade_available": self.live_trade_available,
            "live_quote_available": self.live_quote_available,
            "cached_snapshot_available": self.cached_snapshot_available,
            "allow_cached_fallback": self.allow_cached_fallback,
            "submission_allowed": self.submission_allowed,
            "downgraded_to_cached_data": self.downgraded_to_cached_data,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class WebsocketRestParityCheck:
    symbol: str
    timestamp: str
    streamed_close: float | None
    rest_close: float | None
    close_drift_bps: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "streamed_close": self.streamed_close,
            "rest_close": self.rest_close,
            "close_drift_bps": self.close_drift_bps,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WebsocketRestParityReport:
    checks: tuple[WebsocketRestParityCheck, ...]
    max_close_drift_bps: float = 5.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "websocket_rest_parity_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_close_drift_bps": self.max_close_drift_bps,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class LatencyHistogram:
    name: str
    samples: int
    p50_seconds: float | None
    p95_seconds: float | None
    max_seconds: float | None
    buckets: dict[str, int]
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "samples": self.samples,
            "p50_seconds": self.p50_seconds,
            "p95_seconds": self.p95_seconds,
            "max_seconds": self.max_seconds,
            "buckets": dict(self.buckets),
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DataLatencyHistogramReport:
    histograms: tuple[LatencyHistogram, ...]
    max_p95_seconds_by_name: dict[str, float]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(histogram.passed for histogram in self.histograms)

    @property
    def reason(self) -> str:
        if self.passed:
            return "data_latency_histograms_passed"
        return next(histogram.reason for histogram in self.histograms if not histogram.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_p95_seconds_by_name": dict(self.max_p95_seconds_by_name),
            "histograms": [histogram.to_dict() for histogram in self.histograms],
            "artifact_path": self.artifact_path,
        }


def build_live_market_snapshot_report(
    snapshots: Sequence[Mapping[str, Any]],
    observed_at: datetime | None = None,
    provider: str = "unknown",
) -> LiveMarketSnapshotReport:
    timestamp = observed_at or datetime.now(timezone.utc)
    return LiveMarketSnapshotReport(
        snapshots=tuple(_snapshot_from_payload(payload, provider) for payload in snapshots),
        observed_at=timestamp.isoformat(),
    )


def fetch_alpaca_live_market_snapshots(config: AlpacaConfig, symbols: Sequence[str]) -> LiveMarketSnapshotReport:
    client = AlpacaRestClient(config)
    snapshots = []
    for symbol in symbols:
        trade = client.request("GET", f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest")
        quote = client.request("GET", f"https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest")
        snapshots.append(_alpaca_snapshot_payload(symbol, trade, quote))
    return build_live_market_snapshot_report(snapshots, provider="alpaca")


def build_quote_spread_report(
    snapshots: Sequence[LiveMarketSnapshot],
    executions: Sequence[Mapping[str, Any]],
    max_spread_bps: float = 25.0,
    max_effective_spread_bps: float = 35.0,
) -> QuoteSpreadReport:
    by_symbol = {snapshot.symbol.upper(): snapshot for snapshot in snapshots}
    analyses = tuple(
        _execution_analysis(execution, by_symbol, max_spread_bps, max_effective_spread_bps)
        for execution in executions
    )
    return QuoteSpreadReport(analyses=analyses, max_spread_bps=max_spread_bps, max_effective_spread_bps=max_effective_spread_bps)


def build_data_freshness_report(
    rows: Sequence[Mapping[str, Any]],
    observed_at: datetime | None = None,
    max_age_seconds_by_asset_class: Mapping[str, float] | None = None,
) -> DataFreshnessReport:
    now = observed_at or datetime.now(timezone.utc)
    max_age = dict(max_age_seconds_by_asset_class or {"equity": 900.0, "etf": 900.0, "crypto": 120.0, "bond": 3600.0})
    statuses = tuple(_freshness_status(row, now, max_age) for row in rows)
    return DataFreshnessReport(statuses=statuses, observed_at=now.isoformat())


def arbitrate_data_source(
    symbol: str,
    candidates: Sequence[Mapping[str, Any]],
    max_drift_bps: float = 50.0,
) -> DataSourceArbitrationReport:
    parsed = tuple(
        DataSourceCandidate(
            provider=str(candidate.get("provider")),
            freshness_passed=bool(candidate.get("freshness_passed")),
            schema_passed=bool(candidate.get("schema_passed")),
            drift_bps=_optional_float(candidate.get("drift_bps")),
            available=bool(candidate.get("available", True)),
        )
        for candidate in candidates
    )
    selected = next(
        (
            candidate.provider
            for candidate in parsed
            if candidate.passed and (candidate.drift_bps is None or abs(candidate.drift_bps) <= max_drift_bps)
        ),
        None,
    )
    return DataSourceArbitrationReport(symbol=symbol.upper(), selected_provider=selected, candidates=parsed, max_drift_bps=max_drift_bps)


def build_asset_class_metadata_report(assets: Sequence[Mapping[str, Any]]) -> AssetClassMetadataReport:
    return AssetClassMetadataReport(assets=tuple(_asset_metadata(asset) for asset in assets))


def build_symbol_capability_report(
    assets: Sequence[AssetClassMetadata],
    require_fractional: bool = False,
    require_short: bool = False,
    require_margin: bool = False,
) -> SymbolCapabilityReport:
    gates = tuple(_capability_gate(asset, require_fractional, require_short, require_margin) for asset in assets)
    return SymbolCapabilityReport(
        gates=gates,
        require_fractional=require_fractional,
        require_short=require_short,
        require_margin=require_margin,
    )


def build_multi_timeframe_data_report(
    frames_by_symbol: Mapping[str, Mapping[str, Any]],
    required_timeframes: Sequence[str] = ("1d", "15m"),
    required_rows_by_timeframe: Mapping[str, int] | None = None,
    observed_at: datetime | None = None,
) -> MultiTimeframeDataReport:
    required_rows = {
        "1m": 200,
        "5m": 200,
        "15m": 120,
        "30m": 100,
        "1h": 90,
        "1d": 60,
        "1wk": 52,
        **dict(required_rows_by_timeframe or {}),
    }
    statuses: list[MultiTimeframeDataStatus] = []
    for symbol, frames in frames_by_symbol.items():
        for timeframe in required_timeframes:
            frame = frames.get(timeframe)
            minimum = int(required_rows.get(timeframe, 1))
            statuses.append(_multi_timeframe_status(symbol, timeframe, frame, minimum))
    observed = observed_at or datetime.now(timezone.utc)
    return MultiTimeframeDataReport(
        statuses=tuple(statuses),
        required_timeframes=tuple(required_timeframes),
        observed_at=observed.isoformat(),
    )


def build_corporate_action_replay_report(cases: Sequence[Mapping[str, Any]], tolerance: float = 1e-6) -> CorporateActionReplayReport:
    return CorporateActionReplayReport(cases=tuple(_corporate_action_replay_case(case, tolerance) for case in cases))


def build_market_calendar_regression_report(
    cases: Sequence[Mapping[str, Any]],
    calendar: MarketSessionCalendar | None = None,
    policy: MarketSessionPolicy | None = None,
) -> MarketCalendarRegressionReport:
    calendar = calendar or MarketSessionCalendar()
    policy = policy or MarketSessionPolicy()
    return MarketCalendarRegressionReport(
        cases=tuple(_market_calendar_regression_case(case, calendar, policy) for case in cases)
    )


def simulate_data_outage(
    historical_available: bool,
    live_trade_available: bool,
    live_quote_available: bool,
    cached_snapshot_available: bool = False,
    allow_cached_fallback: bool = False,
) -> DataOutageSimulationReport:
    live_ready = live_trade_available and live_quote_available
    downgraded = bool(not live_ready and allow_cached_fallback and cached_snapshot_available)
    submission_allowed = bool(historical_available and (live_ready or downgraded))
    if not historical_available:
        reason = "historical_data_unavailable_submission_blocked"
    elif live_ready:
        reason = "live_data_available_submission_allowed"
    elif downgraded:
        reason = "live_data_unavailable_downgraded_to_cached_snapshot"
    else:
        reason = "live_data_unavailable_submission_blocked"
    return DataOutageSimulationReport(
        historical_available=historical_available,
        live_trade_available=live_trade_available,
        live_quote_available=live_quote_available,
        cached_snapshot_available=cached_snapshot_available,
        allow_cached_fallback=allow_cached_fallback,
        submission_allowed=submission_allowed,
        downgraded_to_cached_data=downgraded,
        reason=reason,
    )


def build_websocket_rest_parity_report(
    streamed_bars: Sequence[Mapping[str, Any]],
    rest_bars: Sequence[Mapping[str, Any]],
    max_close_drift_bps: float = 5.0,
) -> WebsocketRestParityReport:
    rest_by_key = {_bar_key(bar): bar for bar in rest_bars}
    checks = tuple(
        _websocket_rest_parity_check(streamed, rest_by_key.get(_bar_key(streamed)), max_close_drift_bps)
        for streamed in streamed_bars
    )
    return WebsocketRestParityReport(checks=checks, max_close_drift_bps=max_close_drift_bps)


def build_data_latency_histogram_report(
    samples: Sequence[Mapping[str, Any]],
    buckets: Sequence[float] = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
    max_p95_seconds_by_name: Mapping[str, float] | None = None,
) -> DataLatencyHistogramReport:
    limits = dict(
        {
            "websocket_event": 0.5,
            "rest_call": 2.0,
            "strategy_decision": 1.0,
            "order_submission": 2.0,
            "fill_polling": 5.0,
        }
        | dict(max_p95_seconds_by_name or {})
    )
    grouped: dict[str, list[float]] = {}
    for sample in samples:
        name = str(sample.get("name") or sample.get("source") or "unknown")
        latency = _optional_float(sample.get("latency_seconds") or sample.get("duration_seconds") or sample.get("seconds"))
        if latency is not None:
            grouped.setdefault(name, []).append(latency)
    histograms = tuple(_latency_histogram(name, values, buckets, limits.get(name)) for name, values in sorted(grouped.items()))
    return DataLatencyHistogramReport(histograms=histograms, max_p95_seconds_by_name=limits)


def fetch_alpaca_asset_metadata(config: AlpacaConfig, symbols: Sequence[str]) -> AssetClassMetadataReport:
    client = AlpacaRestClient(config)
    query = urlencode({"status": "active"})
    raw_assets = client.request("GET", f"{config.base_url}/v2/assets?{query}")
    wanted = {symbol.upper() for symbol in symbols}
    assets = [asset for asset in raw_assets if str(asset.get("symbol", "")).upper() in wanted]
    return build_asset_class_metadata_report(assets)


def write_live_market_snapshot_report(report: LiveMarketSnapshotReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_quote_spread_report(report: QuoteSpreadReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_data_freshness_report(report: DataFreshnessReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_data_source_arbitration_report(report: DataSourceArbitrationReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_asset_class_metadata_report(report: AssetClassMetadataReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_symbol_capability_report(report: SymbolCapabilityReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_multi_timeframe_data_report(report: MultiTimeframeDataReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_corporate_action_replay_report(report: CorporateActionReplayReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_market_calendar_regression_report(report: MarketCalendarRegressionReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_data_outage_simulation_report(report: DataOutageSimulationReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_websocket_rest_parity_report(report: WebsocketRestParityReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_data_latency_histogram_report(report: DataLatencyHistogramReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def _snapshot_from_payload(payload: Mapping[str, Any], provider: str) -> LiveMarketSnapshot:
    return LiveMarketSnapshot(
        symbol=str(payload.get("symbol") or "").upper(),
        provider=str(payload.get("provider") or provider),
        latest_trade_price=_optional_float(payload.get("latest_trade_price") or payload.get("price")),
        latest_trade_timestamp=payload.get("latest_trade_timestamp") or payload.get("trade_timestamp"),
        bid_price=_optional_float(payload.get("bid_price") or payload.get("bid")),
        ask_price=_optional_float(payload.get("ask_price") or payload.get("ask")),
        quote_timestamp=payload.get("quote_timestamp"),
    )


def _alpaca_snapshot_payload(symbol: str, trade_payload: Mapping[str, Any], quote_payload: Mapping[str, Any]) -> dict:
    trade = trade_payload.get("trade") or {}
    quote = quote_payload.get("quote") or {}
    return {
        "symbol": symbol.upper(),
        "provider": "alpaca",
        "latest_trade_price": trade.get("p"),
        "latest_trade_timestamp": trade.get("t"),
        "bid_price": quote.get("bp"),
        "ask_price": quote.get("ap"),
        "quote_timestamp": quote.get("t"),
    }


def _execution_analysis(
    execution: Mapping[str, Any],
    snapshots: Mapping[str, LiveMarketSnapshot],
    max_spread_bps: float,
    max_effective_spread_bps: float,
) -> QuoteSpreadExecutionAnalysis:
    symbol = str(execution.get("symbol") or "").upper()
    side = str(execution.get("side") or "").upper()
    fill_price = _optional_float(execution.get("average_fill_price") or execution.get("fill_price"))
    snapshot = snapshots.get(symbol)
    if snapshot is None:
        return QuoteSpreadExecutionAnalysis(symbol, side, fill_price, None, None, None, None, "missing_quote_snapshot")
    effective = _effective_spread_bps(side, fill_price, snapshot.mid_price)
    adverse = _adverse_selection_bps(side, fill_price, snapshot.latest_trade_price)
    reason = "passed"
    if snapshot.spread_bps is None:
        reason = "missing_spread"
    elif snapshot.spread_bps > max_spread_bps:
        reason = "quote_spread_too_wide"
    elif effective is not None and effective > max_effective_spread_bps:
        reason = "effective_spread_too_wide"
    return QuoteSpreadExecutionAnalysis(
        symbol=symbol,
        side=side,
        fill_price=fill_price,
        reference_mid_price=snapshot.mid_price,
        spread_bps=snapshot.spread_bps,
        effective_spread_bps=effective,
        adverse_selection_bps=adverse,
        reason=reason,
    )


def _effective_spread_bps(side: str, fill_price: float | None, mid_price: float | None) -> float | None:
    if fill_price is None or not mid_price:
        return None
    signed = fill_price - mid_price if side == "BUY" else mid_price - fill_price
    return max(0.0, (2.0 * signed / mid_price) * 10_000.0)


def _adverse_selection_bps(side: str, fill_price: float | None, latest_trade_price: float | None) -> float | None:
    if fill_price is None or not latest_trade_price:
        return None
    signed = latest_trade_price - fill_price if side == "BUY" else fill_price - latest_trade_price
    return (signed / fill_price) * 10_000.0


def _freshness_status(row: Mapping[str, Any], observed_at: datetime, max_age_by_asset: Mapping[str, float]) -> DataFreshnessStatus:
    asset_class = str(row.get("asset_class") or "equity").lower()
    timestamp = row.get("timestamp")
    parsed = _parse_datetime(timestamp)
    age = (observed_at - parsed).total_seconds() if parsed is not None else None
    return DataFreshnessStatus(
        symbol=str(row.get("symbol") or "").upper(),
        source=str(row.get("source") or "unknown"),
        timestamp=parsed.isoformat() if parsed else None,
        age_seconds=age,
        max_age_seconds=float(max_age_by_asset.get(asset_class, max_age_by_asset.get("equity", 900.0))),
        asset_class=asset_class,
    )


def _asset_metadata(payload: Mapping[str, Any]) -> AssetClassMetadata:
    asset_class = str(payload.get("asset_class") or payload.get("class") or "equity").lower()
    return AssetClassMetadata(
        symbol=str(payload.get("symbol") or "").upper(),
        asset_class=asset_class,
        calendar_policy=str(payload.get("calendar_policy") or ASSET_CLASS_CALENDAR.get(asset_class, "unknown")),
        fractional_trading=bool(payload.get("fractionable") or payload.get("fractional_trading")),
        tradable=bool(payload.get("tradable", True)),
        shortable=bool(payload.get("shortable", False)),
        easy_to_borrow=bool(payload.get("easy_to_borrow", False)),
        marginable=bool(payload.get("marginable", False)),
        maintenance_margin=_optional_float(payload.get("maintenance_margin")),
    )


def _capability_gate(
    asset: AssetClassMetadata,
    require_fractional: bool,
    require_short: bool,
    require_margin: bool,
) -> SymbolCapabilityGate:
    reason = "passed"
    if not asset.tradable:
        reason = "symbol_not_tradable"
    elif require_fractional and not asset.fractional_trading:
        reason = "fractional_trading_not_supported"
    elif require_short and not (asset.shortable and asset.easy_to_borrow):
        reason = "shorting_not_supported"
    elif require_margin and not asset.marginable:
        reason = "margin_not_supported"
    return SymbolCapabilityGate(
        symbol=asset.symbol,
        tradable=asset.tradable,
        fractional_allowed=asset.fractional_trading,
        short_allowed=asset.shortable and asset.easy_to_borrow,
        margin_allowed=asset.marginable,
        reason=reason,
    )


def _multi_timeframe_status(symbol: str, timeframe: str, frame: Any, required_rows: int) -> MultiTimeframeDataStatus:
    if frame is None:
        return MultiTimeframeDataStatus(symbol.upper(), timeframe, 0, required_rows, None, "missing_timeframe")
    rows = _frame_row_count(frame)
    last_timestamp = _frame_last_timestamp(frame)
    reason = "passed"
    if rows < required_rows:
        reason = "insufficient_rows"
    elif last_timestamp is None:
        reason = "missing_latest_timestamp"
    return MultiTimeframeDataStatus(symbol.upper(), timeframe, rows, required_rows, last_timestamp, reason)


def _corporate_action_replay_case(case: Mapping[str, Any], tolerance: float) -> CorporateActionReplayCase:
    action_type = str(case.get("action_type") or case.get("type") or "").lower()
    raw_price = _optional_float(case.get("raw_price") or case.get("price_before"))
    adjusted_price = _optional_float(case.get("adjusted_price") or case.get("price_after"))
    raw_quantity = _optional_float(case.get("raw_quantity") or case.get("quantity_before"))
    adjusted_quantity = _optional_float(case.get("adjusted_quantity") or case.get("quantity_after"))
    expected_ratio = _optional_float(case.get("expected_ratio") or case.get("ratio"))
    dividend_amount = _optional_float(case.get("dividend_amount") or case.get("amount"))
    paper_quantity = _optional_float(case.get("paper_quantity") or case.get("paper_quantity_after"))
    backtest_quantity = _optional_float(case.get("backtest_quantity") or case.get("backtest_quantity_after"))
    reason = "passed"
    if action_type == "split":
        if not expected_ratio:
            reason = "missing_split_ratio"
        elif raw_price is not None and adjusted_price is not None and abs(adjusted_price - (raw_price / expected_ratio)) > tolerance:
            reason = "split_price_adjustment_mismatch"
        elif raw_quantity is not None and adjusted_quantity is not None and abs(adjusted_quantity - (raw_quantity * expected_ratio)) > tolerance:
            reason = "split_quantity_adjustment_mismatch"
    elif action_type == "dividend":
        if dividend_amount is None or dividend_amount <= 0:
            reason = "missing_dividend_amount"
    else:
        reason = "unsupported_corporate_action"
    if reason == "passed" and paper_quantity is not None and backtest_quantity is not None:
        if abs(paper_quantity - backtest_quantity) > tolerance:
            reason = "paper_backtest_quantity_mismatch"
    return CorporateActionReplayCase(
        symbol=str(case.get("symbol") or "").upper(),
        action_type=action_type,
        raw_price=raw_price,
        adjusted_price=adjusted_price,
        raw_quantity=raw_quantity,
        adjusted_quantity=adjusted_quantity,
        expected_ratio=expected_ratio,
        dividend_amount=dividend_amount,
        paper_quantity=paper_quantity,
        backtest_quantity=backtest_quantity,
        reason=reason,
    )


def _market_calendar_regression_case(
    case: Mapping[str, Any],
    calendar: MarketSessionCalendar,
    policy: MarketSessionPolicy,
) -> MarketCalendarRegressionCase:
    timestamp = _parse_datetime(case.get("timestamp"))
    if timestamp is None:
        actual_session = "UNKNOWN"
        actual_tradable = False
        timestamp_text = ""
    else:
        actual_session = calendar.session_at(timestamp).value
        actual_tradable = calendar.is_tradable_at(timestamp, policy)
        timestamp_text = timestamp.isoformat()
    expected_session = str(case.get("expected_session") or actual_session).upper()
    expected_tradable = bool(case.get("expected_tradable", actual_tradable))
    reason = "passed"
    if timestamp is None:
        reason = "missing_timestamp"
    elif actual_session != expected_session:
        reason = "session_mismatch"
    elif actual_tradable != expected_tradable:
        reason = "tradable_window_mismatch"
    return MarketCalendarRegressionCase(
        name=str(case.get("name") or timestamp_text),
        timestamp=timestamp_text,
        expected_session=expected_session,
        actual_session=actual_session,
        expected_tradable=expected_tradable,
        actual_tradable=actual_tradable,
        reason=reason,
    )


def _websocket_rest_parity_check(
    streamed: Mapping[str, Any],
    rest: Mapping[str, Any] | None,
    max_close_drift_bps: float,
) -> WebsocketRestParityCheck:
    symbol = str(streamed.get("symbol") or "").upper()
    timestamp = str(streamed.get("timestamp") or streamed.get("t") or "")
    streamed_close = _optional_float(streamed.get("close") or streamed.get("c"))
    rest_close = _optional_float((rest or {}).get("close") or (rest or {}).get("c"))
    drift = None
    reason = "passed"
    if rest is None:
        reason = "missing_rest_bar"
    elif streamed_close is None or rest_close is None:
        reason = "missing_close_price"
    elif rest_close == 0:
        reason = "invalid_rest_close"
    else:
        drift = abs(streamed_close - rest_close) / rest_close * 10_000.0
        if drift > max_close_drift_bps:
            reason = "close_drift_above_threshold"
    return WebsocketRestParityCheck(symbol, timestamp, streamed_close, rest_close, drift, reason)


def _latency_histogram(name: str, values: Sequence[float], buckets: Sequence[float], max_p95: float | None) -> LatencyHistogram:
    sorted_values = sorted(values)
    p50 = _percentile(sorted_values, 0.50)
    p95 = _percentile(sorted_values, 0.95)
    bucket_counts: dict[str, int] = {}
    previous = 0.0
    for bucket in buckets:
        label = f"{previous:.2f}-{bucket:.2f}s"
        bucket_counts[label] = sum(1 for value in sorted_values if previous <= value < bucket)
        previous = bucket
    bucket_counts[f">={previous:.2f}s"] = sum(1 for value in sorted_values if value >= previous)
    reason = "passed"
    if not sorted_values:
        reason = "missing_latency_samples"
    elif max_p95 is not None and p95 is not None and p95 > max_p95:
        reason = "p95_latency_above_threshold"
    return LatencyHistogram(name, len(sorted_values), p50, p95, max(sorted_values) if sorted_values else None, bucket_counts, reason)


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, round((len(values) - 1) * percentile)))
    return values[index]


def _bar_key(bar: Mapping[str, Any]) -> tuple[str, str]:
    return (str(bar.get("symbol") or "").upper(), str(bar.get("timestamp") or bar.get("t") or ""))


def _frame_row_count(frame: Any) -> int:
    if isinstance(frame, Mapping):
        if "rows" in frame:
            return int(frame["rows"])
        if "data" in frame and isinstance(frame["data"], Sequence):
            return len(frame["data"])
    shape = getattr(frame, "shape", None)
    if shape:
        return int(shape[0])
    try:
        return len(frame)
    except TypeError:
        return 0


def _frame_last_timestamp(frame: Any) -> str | None:
    if isinstance(frame, Mapping):
        value = frame.get("last_timestamp") or frame.get("timestamp")
        parsed = _parse_datetime(value)
        return parsed.isoformat() if parsed else None
    index = getattr(frame, "index", None)
    if index is not None and len(index) > 0:
        parsed = _parse_datetime(index[-1])
        return parsed.isoformat() if parsed else str(index[-1])
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _write_report(payload: dict, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)
