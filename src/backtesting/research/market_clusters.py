from dataclasses import dataclass
from typing import Mapping, Sequence

from ..runners.bulk import BulkBacktestRecord


@dataclass(frozen=True)
class MarketClusterDefinition:
    name: str
    symbols: tuple[str, ...]
    description: str = ""
    min_markets: int = 2
    min_average_excess_return: float = 0.0
    min_win_rate: float = 0.50
    max_average_drawdown: float = -0.60

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "symbols": list(self.symbols),
            "description": self.description,
            "min_markets": self.min_markets,
            "min_average_excess_return": self.min_average_excess_return,
            "min_win_rate": self.min_win_rate,
            "max_average_drawdown": self.max_average_drawdown,
        }


@dataclass(frozen=True)
class MarketClusterValidationPolicy:
    benchmark_strategy: str = "buyHold"
    clusters: tuple[MarketClusterDefinition, ...] = tuple()
    min_pass_rate: float = 0.50


@dataclass(frozen=True)
class StrategyClusterResult:
    strategy: str
    cluster: str
    markets: int
    average_return: float
    benchmark_return: float
    average_excess_return: float
    average_drawdown: float
    win_rate: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "cluster": self.cluster,
            "markets": self.markets,
            "average_return": self.average_return,
            "benchmark_return": self.benchmark_return,
            "average_excess_return": self.average_excess_return,
            "average_drawdown": self.average_drawdown,
            "win_rate": self.win_rate,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyClusterSummary:
    strategy: str
    clusters_tested: int
    clusters_passed: int
    pass_rate: float
    promoted: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "clusters_tested": self.clusters_tested,
            "clusters_passed": self.clusters_passed,
            "pass_rate": self.pass_rate,
            "promoted": self.promoted,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MarketClusterValidationReport:
    policy: MarketClusterValidationPolicy
    results: tuple[StrategyClusterResult, ...]
    summaries: tuple[StrategyClusterSummary, ...]
    missing_benchmarks: tuple[str, ...] = tuple()

    def to_dict(self) -> dict:
        return {
            "policy": {
                "benchmark_strategy": self.policy.benchmark_strategy,
                "min_pass_rate": self.policy.min_pass_rate,
                "clusters": [cluster.to_dict() for cluster in self.policy.clusters],
            },
            "missing_benchmarks": list(self.missing_benchmarks),
            "summaries": [summary.to_dict() for summary in self.summaries],
            "results": [result.to_dict() for result in self.results],
        }


DEFAULT_MARKET_CLUSTERS: tuple[MarketClusterDefinition, ...] = (
    MarketClusterDefinition("equity_bull", ("SPY", "QQQ", "IWM"), "Growth/risk-on equity proxies."),
    MarketClusterDefinition("equity_defensive", ("XLU", "XLP", "USMV"), "Defensive equity and low-volatility proxies."),
    MarketClusterDefinition("bond_selloff", ("TLT", "IEF", "LQD"), "Duration and credit-sensitive bond proxies."),
    MarketClusterDefinition("inflation_commodities", ("GLD", "DBC", "USO"), "Gold, broad commodity, and energy proxies."),
    MarketClusterDefinition("crypto_cycle", ("BTC-USD", "ETH-USD", "SOL-USD"), "Major crypto cycle proxies."),
    MarketClusterDefinition("choppy_value", ("DIA", "XLF", "XLV"), "Older-economy and mixed-regime equity proxies."),
)


def validate_market_clusters(
    records: Sequence[BulkBacktestRecord],
    policy: MarketClusterValidationPolicy | None = None,
) -> MarketClusterValidationReport:
    """Validate strategy evidence across predefined market clusters."""

    policy = policy or MarketClusterValidationPolicy(clusters=DEFAULT_MARKET_CLUSTERS)
    if not policy.clusters:
        policy = MarketClusterValidationPolicy(
            benchmark_strategy=policy.benchmark_strategy,
            clusters=DEFAULT_MARKET_CLUSTERS,
            min_pass_rate=policy.min_pass_rate,
        )
    by_symbol = _records_by_symbol(records)
    strategies = sorted({record.strategy for record in records if record.strategy != policy.benchmark_strategy})
    results = []
    missing_benchmarks = [
        symbol
        for symbol, strategies in by_symbol.items()
        if policy.benchmark_strategy not in strategies
    ]

    for cluster in policy.clusters:
        cluster_symbols = tuple(symbol.upper() for symbol in cluster.symbols)
        for strategy in strategies:
            results.append(_cluster_result(strategy, cluster, by_symbol, policy.benchmark_strategy))

    summaries = tuple(_summary_for_strategy(strategy, results, policy) for strategy in strategies)
    return MarketClusterValidationReport(
        policy=policy,
        results=tuple(results),
        summaries=tuple(sorted(summaries, key=lambda item: (item.promoted, item.pass_rate), reverse=True)),
        missing_benchmarks=tuple(sorted(set(missing_benchmarks))),
    )


def _records_by_symbol(records: Sequence[BulkBacktestRecord]) -> dict[str, dict[str, BulkBacktestRecord]]:
    grouped: dict[str, dict[str, BulkBacktestRecord]] = {}
    for record in records:
        grouped.setdefault(record.symbol.upper(), {})[record.strategy] = record
    return grouped


def _cluster_result(
    strategy: str,
    cluster: MarketClusterDefinition,
    by_symbol: Mapping[str, Mapping[str, BulkBacktestRecord]],
    benchmark_strategy: str,
) -> StrategyClusterResult:
    matched = []
    for symbol in cluster.symbols:
        symbol_records = by_symbol.get(symbol.upper(), {})
        if strategy in symbol_records and benchmark_strategy in symbol_records:
            matched.append((symbol_records[strategy], symbol_records[benchmark_strategy]))

    if len(matched) < cluster.min_markets:
        return StrategyClusterResult(strategy, cluster.name, len(matched), 0.0, 0.0, 0.0, 0.0, 0.0, False, "insufficient_markets")

    strategy_returns = [float(record.total_pnl_pct) for record, _ in matched]
    benchmark_returns = [float(benchmark.total_pnl_pct) for _, benchmark in matched]
    excess_returns = [strategy_return - benchmark_return for strategy_return, benchmark_return in zip(strategy_returns, benchmark_returns)]
    drawdowns = [_metric_float(record.metrics, "max_drawdown") for record, _ in matched]
    average_return = _average(strategy_returns)
    benchmark_return = _average(benchmark_returns)
    average_excess = _average(excess_returns)
    average_drawdown = _average(drawdowns)
    win_rate = sum(1 for value in excess_returns if value > 0) / len(excess_returns)
    passed, reason = _decision(average_excess, average_drawdown, win_rate, cluster)
    return StrategyClusterResult(
        strategy=strategy,
        cluster=cluster.name,
        markets=len(matched),
        average_return=average_return,
        benchmark_return=benchmark_return,
        average_excess_return=average_excess,
        average_drawdown=average_drawdown,
        win_rate=win_rate,
        passed=passed,
        reason=reason,
    )


def _decision(
    average_excess: float,
    average_drawdown: float,
    win_rate: float,
    cluster: MarketClusterDefinition,
) -> tuple[bool, str]:
    if average_excess < cluster.min_average_excess_return:
        return False, "insufficient_cluster_edge"
    if average_drawdown < cluster.max_average_drawdown:
        return False, "cluster_drawdown_too_deep"
    if win_rate < cluster.min_win_rate:
        return False, "cluster_win_rate_too_low"
    return True, "passes_cluster_gates"


def _summary_for_strategy(
    strategy: str,
    results: Sequence[StrategyClusterResult],
    policy: MarketClusterValidationPolicy,
) -> StrategyClusterSummary:
    strategy_results = [result for result in results if result.strategy == strategy]
    tested = len(strategy_results)
    passed = sum(1 for result in strategy_results if result.passed)
    pass_rate = passed / tested if tested else 0.0
    promoted = pass_rate >= policy.min_pass_rate and passed > 0
    reason = "passes_market_cluster_validation" if promoted else "insufficient_cluster_pass_rate"
    return StrategyClusterSummary(strategy, tested, passed, pass_rate, promoted, reason)


def _metric_float(metrics: Mapping[str, object], name: str) -> float:
    value = metrics.get(name, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
