import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from src.strategies import get_strategy
from src.strategies.buy_hold import BuyAndHoldStrategy

from ..core.engine import BacktestEngine
from ..core.types import BacktestConfig
from ..core.validation import validate_backtest_result
from ..execution.costs import BpsCommissionModel, NoSlippageModel, UnlimitedLiquidityModel
from ..execution.model import BarExecutionModel


@dataclass(frozen=True)
class ReplicationReference:
    name: str
    strategy: str
    params: Mapping[str, object]
    published_return_pct: float
    published_trades: int | None = None
    published_win_rate_pct: float | None = None
    published_max_drawdown_pct: float | None = None
    published_buy_hold_pct: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class ReplicationProfile:
    name: str
    margin_ratio: float = 1.0
    commission_bps: float = 0.0
    execution_price_column: str = "Close"
    allow_fractional_shares: bool = False
    force_flat_at_end: bool = True


@dataclass(frozen=True)
class ReplicationSuite:
    name: str
    data_source: str
    symbol: str
    references: tuple[ReplicationReference, ...]
    profiles: tuple[ReplicationProfile, ...]
    source_url: str = ""
    notes: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class ReplicationRunResult:
    reference: ReplicationReference
    profile: ReplicationProfile
    result_summary: Mapping[str, object]
    buy_hold_summary: Mapping[str, object]

    def to_dict(self) -> dict:
        published = {
            "return_pct": self.reference.published_return_pct,
            "trades": self.reference.published_trades,
            "win_rate_pct": self.reference.published_win_rate_pct,
            "max_drawdown_pct": self.reference.published_max_drawdown_pct,
            "buy_hold_pct": self.reference.published_buy_hold_pct,
        }
        ours = dict(self.result_summary)
        return {
            "name": self.reference.name,
            "strategy": self.reference.strategy,
            "params": dict(self.reference.params),
            "profile": self.profile.name,
            "published": published,
            "ours": ours,
            "buy_hold_ours": dict(self.buy_hold_summary),
            "diff_return_pct": _diff(ours.get("return_pct"), self.reference.published_return_pct),
            "diff_trades": _diff(ours.get("trades"), self.reference.published_trades),
            "diff_win_rate_pct": _diff(ours.get("win_rate_pct"), self.reference.published_win_rate_pct),
            "diff_max_drawdown_pct": _diff(ours.get("max_drawdown_pct"), self.reference.published_max_drawdown_pct),
            "notes": self.reference.notes,
        }


@dataclass
class ReplicationReport:
    suite: ReplicationSuite
    results: list[ReplicationRunResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.suite.name,
            "data_source": self.suite.data_source,
            "symbol": self.suite.symbol,
            "source_url": self.suite.source_url,
            "notes": list(self.suite.notes),
            "rows": [result.to_dict() for result in self.results],
        }


def load_replication_suite(path: str | Path) -> ReplicationSuite:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return replication_suite_from_dict(payload)


def replication_suite_from_dict(payload: Mapping[str, object]) -> ReplicationSuite:
    references = tuple(_reference_from_dict(item) for item in payload.get("references", []))
    profiles = tuple(_profile_from_dict(item) for item in payload.get("profiles", [{"name": "default"}]))
    return ReplicationSuite(
        name=str(payload.get("name", "published_strategy_replication")),
        data_source=str(payload["data_source"]),
        symbol=str(payload["symbol"]),
        references=references,
        profiles=profiles,
        source_url=str(payload.get("source_url", "")),
        notes=tuple(str(note) for note in payload.get("notes", [])),
    )


def run_replication_suite(suite: ReplicationSuite) -> ReplicationReport:
    data = _load_ohlcv_csv(suite.data_source)
    report = ReplicationReport(suite=suite)
    for profile in suite.profiles:
        buy_hold_summary = _run_buy_hold(suite.symbol, data, profile)
        for reference in suite.references:
            strategy_cls = get_strategy(reference.strategy)
            params = dict(reference.params)
            params.setdefault("commission_bps", profile.commission_bps)
            strategy = strategy_cls(suite.symbol, **params)
            result = _engine_for_profile(profile).run(strategy, data)
            report.results.append(
                ReplicationRunResult(
                    reference=reference,
                    profile=profile,
                    result_summary=_summarize_result(result),
                    buy_hold_summary=buy_hold_summary,
                )
            )
    return report


def write_replication_report(report: ReplicationReport, output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return destination


def _reference_from_dict(payload: Mapping[str, object]) -> ReplicationReference:
    return ReplicationReference(
        name=str(payload["name"]),
        strategy=str(payload["strategy"]),
        params=dict(payload.get("params", {})),
        published_return_pct=float(payload["published_return_pct"]),
        published_trades=_optional_int(payload.get("published_trades")),
        published_win_rate_pct=_optional_float(payload.get("published_win_rate_pct")),
        published_max_drawdown_pct=_optional_float(payload.get("published_max_drawdown_pct")),
        published_buy_hold_pct=_optional_float(payload.get("published_buy_hold_pct")),
        notes=str(payload.get("notes", "")),
    )


def _profile_from_dict(payload: Mapping[str, object]) -> ReplicationProfile:
    return ReplicationProfile(
        name=str(payload["name"]),
        margin_ratio=float(payload.get("margin_ratio", 1.0)),
        commission_bps=float(payload.get("commission_bps", 0.0)),
        execution_price_column=str(payload.get("execution_price_column", "Close")),
        allow_fractional_shares=bool(payload.get("allow_fractional_shares", False)),
        force_flat_at_end=bool(payload.get("force_flat_at_end", True)),
    )


def _load_ohlcv_csv(path_or_url: str) -> pd.DataFrame:
    data = pd.read_csv(path_or_url, index_col=0, parse_dates=True)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Replication data is missing columns: {missing}")
    return data[required].sort_index()


def _run_buy_hold(symbol: str, data: pd.DataFrame, profile: ReplicationProfile) -> Mapping[str, object]:
    result = _engine_for_profile(profile).run(BuyAndHoldStrategy(symbol), data)
    return _summarize_result(result)


def _engine_for_profile(profile: ReplicationProfile) -> BacktestEngine:
    return BacktestEngine(
        config=BacktestConfig(
            initial_cash=10_000,
            margin_ratio=profile.margin_ratio,
            allow_fractional_shares=profile.allow_fractional_shares,
            execution_price_column=profile.execution_price_column,
            force_flat_at_end=profile.force_flat_at_end,
        ),
        execution_model=BarExecutionModel(
            slippage_model=NoSlippageModel(),
            commission_model=BpsCommissionModel(profile.commission_bps),
            liquidity_model=UnlimitedLiquidityModel(),
            price_column=profile.execution_price_column,
        ),
    )


def _summarize_result(result) -> Mapping[str, object]:
    trades = list(result.trades)
    wins = [trade for trade in trades if (trade.pnl or 0.0) > 0]
    validation = validate_backtest_result(result)
    return {
        "return_pct": float(result.total_pnl_pct * 100),
        "max_drawdown_pct": float(result.metrics.get("max_drawdown", 0.0) * 100),
        "trades": len(trades),
        "fills": len(result.fills),
        "rejections": len(result.rejections),
        "win_rate_pct": float(len(wins) / len(trades) * 100) if trades else 0.0,
        "ending_equity": float(result.equity.iloc[-1]),
        "valid": validation.passed,
        "validation_issues": [issue.code for issue in validation.issues],
    }


def _diff(left: object, right: object) -> float | int | None:
    if left is None or right is None:
        return None
    return left - right


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None
