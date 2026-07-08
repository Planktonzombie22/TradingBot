from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .bulk import BulkBacktestRecord


@dataclass(frozen=True)
class StrategySelectionPolicy:
    """Rules for deciding whether a strategy deserves capital against a benchmark."""

    benchmark_strategy: str = "buyHold"
    min_excess_return: float = 0.0
    min_drawdown_improvement: float = -0.05
    max_strategy_drawdown: float = -0.60
    min_trades: int = 1
    drawdown_weight: float = 0.50
    rejection_penalty: float = 0.01
    trade_penalty: float = 0.0001


@dataclass(frozen=True)
class StrategyBenchmarkComparison:
    symbol: str
    strategy: str
    benchmark_strategy: str
    strategy_return: float
    benchmark_return: float
    excess_return: float
    strategy_drawdown: float
    benchmark_drawdown: float
    drawdown_improvement: float
    trades: int
    rejections: int
    score: float
    decision: str
    reason: str
    trade_efficiency: float
    tail_risk: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "benchmark_strategy": self.benchmark_strategy,
            "strategy_return": self.strategy_return,
            "benchmark_return": self.benchmark_return,
            "excess_return": self.excess_return,
            "strategy_drawdown": self.strategy_drawdown,
            "benchmark_drawdown": self.benchmark_drawdown,
            "drawdown_improvement": self.drawdown_improvement,
            "trades": self.trades,
            "rejections": self.rejections,
            "score": self.score,
            "decision": self.decision,
            "reason": self.reason,
            "trade_efficiency": self.trade_efficiency,
            "tail_risk": self.tail_risk,
        }


@dataclass(frozen=True)
class StrategyBenchmarkSummary:
    strategy: str
    markets: int
    average_excess_return: float
    median_excess_return: float
    average_drawdown_improvement: float
    average_trade_efficiency: float
    upside_capture: float | None
    downside_capture: float | None
    tail_risk: float
    select_rate: float
    benchmark_preferred_rate: float
    reject_rate: float

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "markets": self.markets,
            "average_excess_return": self.average_excess_return,
            "median_excess_return": self.median_excess_return,
            "average_drawdown_improvement": self.average_drawdown_improvement,
            "average_trade_efficiency": self.average_trade_efficiency,
            "upside_capture": self.upside_capture,
            "downside_capture": self.downside_capture,
            "tail_risk": self.tail_risk,
            "select_rate": self.select_rate,
            "benchmark_preferred_rate": self.benchmark_preferred_rate,
            "reject_rate": self.reject_rate,
        }


@dataclass(frozen=True)
class SymbolStrategySelection:
    symbol: str
    selected_strategy: str
    action: str
    score: float
    comparison: StrategyBenchmarkComparison | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "selected_strategy": self.selected_strategy,
            "action": self.action,
            "score": self.score,
            "comparison": self.comparison.to_dict() if self.comparison else None,
        }


@dataclass
class StrategySelectionReport:
    policy: StrategySelectionPolicy
    comparisons: list[StrategyBenchmarkComparison] = field(default_factory=list)
    selections: list[SymbolStrategySelection] = field(default_factory=list)
    missing_benchmarks: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        action_counts: dict[str, int] = {}
        strategy_counts: dict[str, int] = {}
        for selection in self.selections:
            action_counts[selection.action] = action_counts.get(selection.action, 0) + 1
            strategy_counts[selection.selected_strategy] = strategy_counts.get(selection.selected_strategy, 0) + 1
        return {
            "benchmark_strategy": self.policy.benchmark_strategy,
            "symbols": len(self.selections),
            "comparisons": len(self.comparisons),
            "action_counts": action_counts,
            "selected_strategy_counts": strategy_counts,
            "missing_benchmarks": self.missing_benchmarks,
        }

    def to_dict(self) -> dict:
        return {
            "policy": {
                "benchmark_strategy": self.policy.benchmark_strategy,
                "min_excess_return": self.policy.min_excess_return,
                "min_drawdown_improvement": self.policy.min_drawdown_improvement,
                "max_strategy_drawdown": self.policy.max_strategy_drawdown,
                "min_trades": self.policy.min_trades,
                "drawdown_weight": self.policy.drawdown_weight,
                "rejection_penalty": self.policy.rejection_penalty,
                "trade_penalty": self.policy.trade_penalty,
            },
            "summary": self.summary(),
            "selections": [selection.to_dict() for selection in self.selections],
            "comparisons": [comparison.to_dict() for comparison in self.comparisons],
        }


@dataclass
class BenchmarkRelativeReport:
    selection_report: StrategySelectionReport

    def strategy_summary(self) -> list[StrategyBenchmarkSummary]:
        grouped: dict[str, list[StrategyBenchmarkComparison]] = {}
        for comparison in self.selection_report.comparisons:
            grouped.setdefault(comparison.strategy, []).append(comparison)

        summaries = []
        for strategy, comparisons in sorted(grouped.items()):
            markets = len(comparisons)
            excess_returns = [comparison.excess_return for comparison in comparisons]
            drawdown_improvements = [comparison.drawdown_improvement for comparison in comparisons]
            trade_efficiencies = [comparison.trade_efficiency for comparison in comparisons]
            select_count = sum(1 for comparison in comparisons if comparison.decision == "select_strategy")
            benchmark_count = sum(1 for comparison in comparisons if comparison.decision == "use_benchmark")
            reject_count = sum(1 for comparison in comparisons if comparison.decision == "reject")

            summaries.append(
                StrategyBenchmarkSummary(
                    strategy=strategy,
                    markets=markets,
                    average_excess_return=_average(excess_returns),
                    median_excess_return=_median(excess_returns),
                    average_drawdown_improvement=_average(drawdown_improvements),
                    average_trade_efficiency=_average(trade_efficiencies),
                    upside_capture=_capture_ratio(comparisons, up_market=True),
                    downside_capture=_capture_ratio(comparisons, up_market=False),
                    tail_risk=min((comparison.tail_risk for comparison in comparisons), default=0.0),
                    select_rate=select_count / markets if markets else 0.0,
                    benchmark_preferred_rate=benchmark_count / markets if markets else 0.0,
                    reject_rate=reject_count / markets if markets else 0.0,
                )
            )
        return sorted(summaries, key=lambda summary: (summary.select_rate, summary.average_excess_return), reverse=True)

    def to_dict(self) -> dict:
        return {
            "selection": self.selection_report.to_dict(),
            "strategy_summary": [summary.to_dict() for summary in self.strategy_summary()],
        }


def select_strategies_against_benchmark(
    records: Sequence[BulkBacktestRecord],
    policy: StrategySelectionPolicy | None = None,
) -> StrategySelectionReport:
    """Select per-symbol strategies only when they beat the benchmark after risk gates."""

    policy = policy or StrategySelectionPolicy()
    by_symbol = _records_by_symbol(records)
    report = StrategySelectionReport(policy=policy)

    for symbol, symbol_records in sorted(by_symbol.items()):
        benchmark = symbol_records.get(policy.benchmark_strategy)
        if benchmark is None:
            report.missing_benchmarks.append(symbol)
            continue

        comparisons = [
            _compare_record(record, benchmark, policy)
            for strategy, record in sorted(symbol_records.items())
            if strategy != policy.benchmark_strategy
        ]
        report.comparisons.extend(comparisons)

        selected = [comparison for comparison in comparisons if comparison.decision == "select_strategy"]
        if selected:
            best = max(selected, key=lambda comparison: comparison.score)
            report.selections.append(
                SymbolStrategySelection(
                    symbol=symbol,
                    selected_strategy=best.strategy,
                    action="trade_strategy",
                    score=best.score,
                    comparison=best,
                )
            )
        else:
            report.selections.append(
                SymbolStrategySelection(
                    symbol=symbol,
                    selected_strategy=policy.benchmark_strategy,
                    action="use_benchmark",
                    score=float(benchmark.total_pnl_pct),
                    comparison=None,
                )
            )
    return report


def benchmark_relative_report(
    records: Sequence[BulkBacktestRecord],
    policy: StrategySelectionPolicy | None = None,
) -> BenchmarkRelativeReport:
    return BenchmarkRelativeReport(select_strategies_against_benchmark(records, policy))


def _records_by_symbol(records: Sequence[BulkBacktestRecord]) -> dict[str, dict[str, BulkBacktestRecord]]:
    grouped: dict[str, dict[str, BulkBacktestRecord]] = {}
    for record in records:
        grouped.setdefault(record.symbol, {})[record.strategy] = record
    return grouped


def _compare_record(
    record: BulkBacktestRecord,
    benchmark: BulkBacktestRecord,
    policy: StrategySelectionPolicy,
) -> StrategyBenchmarkComparison:
    strategy_return = float(record.total_pnl_pct)
    benchmark_return = float(benchmark.total_pnl_pct)
    strategy_drawdown = _metric_float(record.metrics, "max_drawdown")
    benchmark_drawdown = _metric_float(benchmark.metrics, "max_drawdown")
    excess_return = strategy_return - benchmark_return
    drawdown_improvement = abs(benchmark_drawdown) - abs(strategy_drawdown)
    score = (
        excess_return
        + drawdown_improvement * policy.drawdown_weight
        - record.rejections * policy.rejection_penalty
        - record.trades * policy.trade_penalty
    )
    decision, reason = _decision(record, excess_return, drawdown_improvement, strategy_drawdown, policy)
    trade_efficiency = excess_return / record.trades if record.trades else 0.0
    tail_risk = min(strategy_return, strategy_drawdown)

    return StrategyBenchmarkComparison(
        symbol=record.symbol,
        strategy=record.strategy,
        benchmark_strategy=benchmark.strategy,
        strategy_return=strategy_return,
        benchmark_return=benchmark_return,
        excess_return=excess_return,
        strategy_drawdown=strategy_drawdown,
        benchmark_drawdown=benchmark_drawdown,
        drawdown_improvement=drawdown_improvement,
        trades=record.trades,
        rejections=record.rejections,
        score=score,
        decision=decision,
        reason=reason,
        trade_efficiency=trade_efficiency,
        tail_risk=tail_risk,
    )


def _decision(
    record: BulkBacktestRecord,
    excess_return: float,
    drawdown_improvement: float,
    strategy_drawdown: float,
    policy: StrategySelectionPolicy,
) -> tuple[str, str]:
    if record.trades < policy.min_trades:
        return "reject", "insufficient_trades"
    if strategy_drawdown < policy.max_strategy_drawdown:
        return "reject", "strategy_drawdown_too_deep"
    if excess_return < policy.min_excess_return:
        return "use_benchmark", "benchmark_return_higher"
    if drawdown_improvement < policy.min_drawdown_improvement:
        return "reject", "drawdown_not_compensated"
    return "select_strategy", "passes_benchmark_relative_gates"


def _metric_float(metrics: Mapping[str, object], name: str) -> float:
    value = metrics.get(name, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _capture_ratio(comparisons: Sequence[StrategyBenchmarkComparison], up_market: bool) -> float | None:
    filtered = [
        comparison
        for comparison in comparisons
        if (comparison.benchmark_return > 0 if up_market else comparison.benchmark_return < 0)
    ]
    benchmark_average = _average([comparison.benchmark_return for comparison in filtered])
    if not filtered or benchmark_average == 0:
        return None
    return _average([comparison.strategy_return for comparison in filtered]) / benchmark_average
