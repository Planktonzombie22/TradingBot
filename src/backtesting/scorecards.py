from dataclasses import dataclass, field
from typing import Mapping, Sequence

import pandas as pd

from .activation import activate_strategies_for_regime
from .bulk import BulkBacktestRecord
from .filters import ResearchFilterSnapshot, evaluate_research_filters
from .regime import MarketRegimeProfile, classify_market_regime
from .selection import StrategySelectionPolicy, select_strategies_against_benchmark


@dataclass(frozen=True)
class StrategyScorecardEntry:
    strategy: str
    observations: int
    best_return: float
    average_return: float
    benchmark_return: float
    best_excess_return: float
    average_drawdown: float
    parameter_sensitivity: float
    trade_efficiency: float
    robustness_score: float

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "observations": self.observations,
            "best_return": self.best_return,
            "average_return": self.average_return,
            "benchmark_return": self.benchmark_return,
            "best_excess_return": self.best_excess_return,
            "average_drawdown": self.average_drawdown,
            "parameter_sensitivity": self.parameter_sensitivity,
            "trade_efficiency": self.trade_efficiency,
            "robustness_score": self.robustness_score,
        }


@dataclass(frozen=True)
class SymbolResearchScorecard:
    symbol: str
    benchmark_strategy: str
    benchmark_return: float
    selected_strategy: str
    selected_action: str
    best_edge_strategy: str | None
    best_excess_return: float
    regime: MarketRegimeProfile | None = None
    active_strategies: tuple[str, ...] = tuple()
    filters: ResearchFilterSnapshot | None = None
    strategy_entries: tuple[StrategyScorecardEntry, ...] = tuple()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "benchmark_strategy": self.benchmark_strategy,
            "benchmark_return": self.benchmark_return,
            "selected_strategy": self.selected_strategy,
            "selected_action": self.selected_action,
            "best_edge_strategy": self.best_edge_strategy,
            "best_excess_return": self.best_excess_return,
            "regime": self.regime.to_dict() if self.regime else None,
            "active_strategies": list(self.active_strategies),
            "filters": self.filters.to_dict() if self.filters else None,
            "strategy_entries": [entry.to_dict() for entry in self.strategy_entries],
        }


@dataclass
class ScorecardReport:
    scorecards: list[SymbolResearchScorecard] = field(default_factory=list)
    missing_benchmarks: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        selected_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        for scorecard in self.scorecards:
            selected_counts[scorecard.selected_strategy] = selected_counts.get(scorecard.selected_strategy, 0) + 1
            action_counts[scorecard.selected_action] = action_counts.get(scorecard.selected_action, 0) + 1
        return {
            "symbols": len(self.scorecards),
            "selected_strategy_counts": selected_counts,
            "selected_action_counts": action_counts,
            "missing_benchmarks": self.missing_benchmarks,
        }

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "scorecards": [scorecard.to_dict() for scorecard in self.scorecards],
        }


def build_symbol_scorecards(
    records: Sequence[BulkBacktestRecord],
    data_by_symbol: Mapping[str, pd.DataFrame] | None = None,
    policy: StrategySelectionPolicy | None = None,
) -> ScorecardReport:
    """Build per-symbol research scorecards from bulk records and optional market data."""

    policy = policy or StrategySelectionPolicy()
    grouped = _group_records(records)
    best_records = [_best_record(strategy_records) for strategies in grouped.values() for strategy_records in strategies.values()]
    selection_report = select_strategies_against_benchmark(best_records, policy)
    selections = {selection.symbol: selection for selection in selection_report.selections}
    report = ScorecardReport(missing_benchmarks=list(selection_report.missing_benchmarks))

    for symbol, strategies in sorted(grouped.items()):
        benchmark_records = strategies.get(policy.benchmark_strategy)
        if not benchmark_records:
            continue
        benchmark_record = _best_record(benchmark_records)
        entries = tuple(
            sorted(
                (
                    _entry_for_strategy(strategy, strategy_records, benchmark_record.total_pnl_pct)
                    for strategy, strategy_records in strategies.items()
                    if strategy != policy.benchmark_strategy
                ),
                key=lambda entry: entry.robustness_score,
                reverse=True,
            )
        )
        best_entry = entries[0] if entries else None
        data = _data_for_symbol(data_by_symbol, symbol)
        regime = classify_market_regime(data, symbol) if data is not None else None
        filters = evaluate_research_filters(data, symbol) if data is not None else None
        active_strategies = (
            activate_strategies_for_regime([policy.benchmark_strategy, *[entry.strategy for entry in entries]], regime).active_strategies
            if regime is not None
            else tuple()
        )
        selection = selections.get(symbol)

        report.scorecards.append(
            SymbolResearchScorecard(
                symbol=symbol,
                benchmark_strategy=policy.benchmark_strategy,
                benchmark_return=float(benchmark_record.total_pnl_pct),
                selected_strategy=selection.selected_strategy if selection else policy.benchmark_strategy,
                selected_action=selection.action if selection else "use_benchmark",
                best_edge_strategy=best_entry.strategy if best_entry else None,
                best_excess_return=best_entry.best_excess_return if best_entry else 0.0,
                regime=regime,
                active_strategies=active_strategies,
                filters=filters,
                strategy_entries=entries,
            )
        )
    return report


def _group_records(records: Sequence[BulkBacktestRecord]) -> dict[str, dict[str, list[BulkBacktestRecord]]]:
    grouped: dict[str, dict[str, list[BulkBacktestRecord]]] = {}
    for record in records:
        grouped.setdefault(record.symbol, {}).setdefault(record.strategy, []).append(record)
    return grouped


def _best_record(records: Sequence[BulkBacktestRecord]) -> BulkBacktestRecord:
    return max(records, key=lambda record: record.total_pnl_pct)


def _entry_for_strategy(strategy: str, records: Sequence[BulkBacktestRecord], benchmark_return: float) -> StrategyScorecardEntry:
    returns = [float(record.total_pnl_pct) for record in records]
    drawdowns = [float(record.metrics.get("max_drawdown", 0.0)) for record in records]
    trades = sum(record.trades for record in records)
    average_return = _average(returns)
    best_return = max(returns) if returns else 0.0
    best_excess = best_return - benchmark_return
    parameter_sensitivity = (max(returns) - min(returns)) if len(returns) > 1 else 0.0
    trade_efficiency = best_excess / trades if trades else 0.0
    average_drawdown = _average(drawdowns)
    robustness_score = best_excess - parameter_sensitivity * 0.25 - abs(average_drawdown) * 0.25

    return StrategyScorecardEntry(
        strategy=strategy,
        observations=len(records),
        best_return=best_return,
        average_return=average_return,
        benchmark_return=benchmark_return,
        best_excess_return=best_excess,
        average_drawdown=average_drawdown,
        parameter_sensitivity=parameter_sensitivity,
        trade_efficiency=trade_efficiency,
        robustness_score=robustness_score,
    )


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _data_for_symbol(data_by_symbol: Mapping[str, pd.DataFrame] | None, symbol: str) -> pd.DataFrame | None:
    if not data_by_symbol:
        return None
    for candidate in (symbol, symbol.upper(), symbol.lower()):
        if candidate in data_by_symbol:
            return data_by_symbol[candidate]
    return None
