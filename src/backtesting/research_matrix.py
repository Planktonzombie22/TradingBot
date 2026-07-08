import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd

from src.storage import JsonlStore

from .bulk import BulkBacktestReport, run_bulk_backtests
from .types import BacktestConfig

ResearchDataLoaderFactory = Callable[["ResearchMatrixJob"], Callable[[str], pd.DataFrame]]


@dataclass(frozen=True)
class ResearchWindow:
    name: str
    start: str | None = None
    end: str | None = None
    period: str | None = None


@dataclass(frozen=True)
class ResearchAssetGroup:
    name: str
    asset_class: str
    symbols: tuple[str, ...]
    provider: str = "yfinance"
    intervals: tuple[str, ...] = ("1d",)
    windows: tuple[ResearchWindow, ...] = (ResearchWindow("default", period="2y"),)
    notes: str = ""


@dataclass(frozen=True)
class ResearchMatrixConfig:
    name: str
    groups: tuple[ResearchAssetGroup, ...]


@dataclass(frozen=True)
class ResearchMatrixJob:
    matrix_name: str
    group_name: str
    asset_class: str
    provider: str
    interval: str
    window: ResearchWindow
    symbols: tuple[str, ...]

    @property
    def key(self) -> str:
        return _slug(f"{self.matrix_name}-{self.group_name}-{self.interval}-{self.window.name}")

    def to_dict(self) -> dict:
        return {
            "matrix_name": self.matrix_name,
            "group_name": self.group_name,
            "asset_class": self.asset_class,
            "provider": self.provider,
            "interval": self.interval,
            "window": {
                "name": self.window.name,
                "start": self.window.start,
                "end": self.window.end,
                "period": self.window.period,
            },
            "symbols": list(self.symbols),
            "key": self.key,
        }


@dataclass(frozen=True)
class ResearchMatrixJobResult:
    job: ResearchMatrixJob
    report: BulkBacktestReport

    def to_dict(self) -> dict:
        return {
            "job": self.job.to_dict(),
            "completed": self.report.completed,
            "failed": self.report.failed,
            "strategy_summary": self.report.strategy_summary(),
            "errors": [error.to_dict() for error in self.report.errors],
        }


@dataclass
class ResearchMatrixReport:
    matrix_name: str
    job_results: list[ResearchMatrixJobResult] = field(default_factory=list)

    @property
    def completed(self) -> int:
        return sum(result.report.completed for result in self.job_results)

    @property
    def failed(self) -> int:
        return sum(result.report.failed for result in self.job_results)

    def asset_class_summary(self) -> list[dict]:
        grouped: dict[str, list[ResearchMatrixJobResult]] = {}
        for result in self.job_results:
            grouped.setdefault(result.job.asset_class, []).append(result)
        summary = []
        for asset_class, results in sorted(grouped.items()):
            completed = sum(result.report.completed for result in results)
            failed = sum(result.report.failed for result in results)
            summary.append(
                {
                    "asset_class": asset_class,
                    "jobs": len(results),
                    "completed": completed,
                    "failed": failed,
                }
            )
        return summary

    def to_dict(self) -> dict:
        return {
            "matrix_name": self.matrix_name,
            "completed": self.completed,
            "failed": self.failed,
            "asset_class_summary": self.asset_class_summary(),
            "jobs": [result.to_dict() for result in self.job_results],
        }


def load_research_matrix(path: str | Path) -> ResearchMatrixConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return research_matrix_from_dict(payload)


def research_matrix_from_dict(payload: Mapping[str, object]) -> ResearchMatrixConfig:
    groups = []
    for raw_group in payload.get("groups", []):
        group = dict(raw_group)
        windows = tuple(_window_from_dict(item) for item in group.get("windows", [{"name": "default", "period": group.get("period", "2y")}]))
        groups.append(
            ResearchAssetGroup(
                name=str(group["name"]),
                asset_class=str(group.get("asset_class", group["name"])),
                symbols=tuple(str(symbol).upper() for symbol in group.get("symbols", [])),
                provider=str(group.get("provider", "yfinance")),
                intervals=tuple(str(interval) for interval in group.get("intervals", ["1d"])),
                windows=windows,
                notes=str(group.get("notes", "")),
            )
        )
    return ResearchMatrixConfig(name=str(payload.get("name", "research_matrix")), groups=tuple(groups))


def expand_research_matrix(config: ResearchMatrixConfig, max_symbols_per_group: int | None = None) -> list[ResearchMatrixJob]:
    jobs = []
    for group in config.groups:
        symbols = group.symbols[:max_symbols_per_group] if max_symbols_per_group else group.symbols
        for interval in group.intervals:
            for window in group.windows:
                jobs.append(
                    ResearchMatrixJob(
                        matrix_name=config.name,
                        group_name=group.name,
                        asset_class=group.asset_class,
                        provider=group.provider,
                        interval=interval,
                        window=window,
                        symbols=symbols,
                    )
                )
    return jobs


def run_research_matrix(
    config: ResearchMatrixConfig,
    strategies: Sequence[str],
    data_loader_factory: ResearchDataLoaderFactory,
    strategy_params: Mapping[str, Mapping[str, object]] | None = None,
    backtest_config: BacktestConfig | None = None,
    store: JsonlStore | None = None,
    max_symbols_per_group: int | None = None,
) -> ResearchMatrixReport:
    store = store or JsonlStore("runs")
    report = ResearchMatrixReport(matrix_name=config.name)
    for job in expand_research_matrix(config, max_symbols_per_group=max_symbols_per_group):
        bulk_report = run_bulk_backtests(
            symbols=job.symbols,
            strategies=strategies,
            data_loader=data_loader_factory(job),
            strategy_params=strategy_params,
            config=backtest_config or BacktestConfig(),
            store=store,
        )
        result = ResearchMatrixJobResult(job=job, report=bulk_report)
        report.job_results.append(result)
        store.append("matrix-results", result.to_dict())
    return report


def _window_from_dict(payload: Mapping[str, object]) -> ResearchWindow:
    return ResearchWindow(
        name=str(payload.get("name", "default")),
        start=_optional_str(payload.get("start")),
        end=_optional_str(payload.get("end")),
        period=_optional_str(payload.get("period")),
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value not in {None, ""} else None


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
