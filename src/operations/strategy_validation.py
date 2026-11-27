import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from typing import Any, Mapping, Sequence


STRATEGY_STATUSES = {"exploratory", "paper-active", "disabled", "retired", "live-eligible"}


@dataclass(frozen=True)
class StrategyRegistryEntry:
    strategy_name: str
    status: str
    family: str = "default"
    symbol_scope: tuple[str, ...] = ()
    reason: str = "registered"
    metadata: Mapping[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return self.status in STRATEGY_STATUSES

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "status": self.status,
            "family": self.family,
            "symbol_scope": list(self.symbol_scope),
            "passed": self.passed,
            "reason": self.reason if self.passed else "unknown_strategy_status",
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class StrategyRegistryReport:
    entries: tuple[StrategyRegistryEntry, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(entry.passed for entry in self.entries)

    @property
    def reason(self) -> str:
        if self.passed:
            return "strategy_registry_valid"
        return "unknown_strategy_status"

    @property
    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.status] = counts.get(entry.status, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "status_counts": self.status_counts,
            "entries": [entry.to_dict() for entry in self.entries],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StrategyRetirementDecision:
    strategy_name: str
    retired: bool
    benchmark_failures: int
    paper_scorecard_failures: int
    reason: str

    @property
    def passed(self) -> bool:
        return not self.retired

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "retired": self.retired,
            "passed": self.passed,
            "benchmark_failures": self.benchmark_failures,
            "paper_scorecard_failures": self.paper_scorecard_failures,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyRetirementReport:
    decisions: tuple[StrategyRetirementDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "strategy_retirement_rules_clear"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StrategyQuarantineDecision:
    strategy_name: str
    quarantined: bool
    return_drift: float
    slippage_drift_bps: float
    missed_fill_rate: float
    reject_rate: float
    reason: str

    @property
    def passed(self) -> bool:
        return not self.quarantined

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "quarantined": self.quarantined,
            "passed": self.passed,
            "return_drift": self.return_drift,
            "slippage_drift_bps": self.slippage_drift_bps,
            "missed_fill_rate": self.missed_fill_rate,
            "reject_rate": self.reject_rate,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyQuarantineReport:
    decisions: tuple[StrategyQuarantineDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "strategy_quarantine_rules_clear"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class WalkForwardRefreshDecision:
    strategy_name: str
    status: str
    days_since_refresh: int | None
    action: str
    reason: str

    @property
    def passed(self) -> bool:
        return self.action in {"keep_active", "promote", "refresh_due"}

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "status": self.status,
            "days_since_refresh": self.days_since_refresh,
            "action": self.action,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WalkForwardRefreshReport:
    decisions: tuple[WalkForwardRefreshDecision, ...]
    max_refresh_age_days: int = 30
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "walk_forward_refresh_evaluated"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_refresh_age_days": self.max_refresh_age_days,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class HoldoutMetadataCheck:
    strategy_name: str
    train_start: str | None
    train_end: str | None
    validation_start: str | None
    validation_end: str | None
    test_start: str | None
    test_end: str | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class HoldoutMetadataReport:
    checks: tuple[HoldoutMetadataCheck, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "holdout_metadata_valid"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class BenchmarkPaperMonitorDecision:
    strategy_name: str
    symbol: str
    strategy_return_after_costs: float
    benchmark_return: float
    excess_return_after_costs: float
    disabled: bool
    reason: str

    @property
    def passed(self) -> bool:
        return not self.disabled

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "strategy_return_after_costs": self.strategy_return_after_costs,
            "benchmark_return": self.benchmark_return,
            "excess_return_after_costs": self.excess_return_after_costs,
            "disabled": self.disabled,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BenchmarkPaperMonitorReport:
    decisions: tuple[BenchmarkPaperMonitorDecision, ...]
    min_excess_return_after_costs: float = 0.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "benchmark_relative_paper_monitor_passed"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "min_excess_return_after_costs": self.min_excess_return_after_costs,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class RegimeConditionedScorecard:
    strategy_name: str
    regime: str
    sample_size: int
    excess_return_after_costs: float
    max_drawdown: float
    tradable: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.tradable

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "regime": self.regime,
            "sample_size": self.sample_size,
            "excess_return_after_costs": self.excess_return_after_costs,
            "max_drawdown": self.max_drawdown,
            "tradable": self.tradable,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RegimeConditionedScorecardReport:
    scorecards: tuple[RegimeConditionedScorecard, ...]
    min_sample_size: int = 20
    min_excess_return_after_costs: float = 0.0
    max_drawdown: float = 0.20
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return any(scorecard.passed for scorecard in self.scorecards)

    @property
    def reason(self) -> str:
        if self.passed:
            return "regime_scorecards_have_tradable_regimes"
        return "no_regime_scorecard_passed"

    @property
    def tradable_regimes(self) -> tuple[str, ...]:
        return tuple(scorecard.regime for scorecard in self.scorecards if scorecard.tradable)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "min_sample_size": self.min_sample_size,
            "min_excess_return_after_costs": self.min_excess_return_after_costs,
            "max_drawdown": self.max_drawdown,
            "tradable_regimes": list(self.tradable_regimes),
            "scorecards": [scorecard.to_dict() for scorecard in self.scorecards],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class MarketClusterPaperScorecard:
    strategy_name: str
    cluster: str
    asset_class: str
    symbols_tested: int
    pass_rate: float
    average_excess_return_after_costs: float
    paper_sessions: int
    tradable: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.tradable

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "cluster": self.cluster,
            "asset_class": self.asset_class,
            "symbols_tested": self.symbols_tested,
            "pass_rate": self.pass_rate,
            "average_excess_return_after_costs": self.average_excess_return_after_costs,
            "paper_sessions": self.paper_sessions,
            "tradable": self.tradable,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MarketClusterPaperScorecardReport:
    scorecards: tuple[MarketClusterPaperScorecard, ...]
    min_symbols_tested: int = 3
    min_pass_rate: float = 0.50
    min_paper_sessions: int = 3
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(scorecard.passed for scorecard in self.scorecards)

    @property
    def reason(self) -> str:
        if self.passed:
            return "market_cluster_paper_scorecards_passed"
        return next(scorecard.reason for scorecard in self.scorecards if not scorecard.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "min_symbols_tested": self.min_symbols_tested,
            "min_pass_rate": self.min_pass_rate,
            "min_paper_sessions": self.min_paper_sessions,
            "scorecards": [scorecard.to_dict() for scorecard in self.scorecards],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class CapacityScorecard:
    strategy_name: str
    symbol: str
    target_notional: float
    observed_slippage_bps: float
    volume_participation: float
    estimated_capacity_notional: float | None
    capacity_ok: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.capacity_ok

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "target_notional": self.target_notional,
            "observed_slippage_bps": self.observed_slippage_bps,
            "volume_participation": self.volume_participation,
            "estimated_capacity_notional": self.estimated_capacity_notional,
            "capacity_ok": self.capacity_ok,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CapacityScorecardReport:
    scorecards: tuple[CapacityScorecard, ...]
    max_observed_slippage_bps: float = 25.0
    max_volume_participation: float = 0.01
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(scorecard.passed for scorecard in self.scorecards)

    @property
    def reason(self) -> str:
        if self.passed:
            return "capacity_scorecards_passed"
        return next(scorecard.reason for scorecard in self.scorecards if not scorecard.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_observed_slippage_bps": self.max_observed_slippage_bps,
            "max_volume_participation": self.max_volume_participation,
            "scorecards": [scorecard.to_dict() for scorecard in self.scorecards],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class SampleSizeGate:
    strategy_name: str
    trades: int
    sessions: int
    symbols: int
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "trades": self.trades,
            "sessions": self.sessions,
            "symbols": self.symbols,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SampleSizeGateReport:
    gates: tuple[SampleSizeGate, ...]
    min_trades: int = 30
    min_sessions: int = 5
    min_symbols: int = 1
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def reason(self) -> str:
        if self.passed:
            return "sample_size_gates_passed"
        return next(gate.reason for gate in self.gates if not gate.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "min_trades": self.min_trades,
            "min_sessions": self.min_sessions,
            "min_symbols": self.min_symbols,
            "gates": [gate.to_dict() for gate in self.gates],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StatisticalConfidenceResult:
    strategy_name: str
    sample_size: int
    mean_excess_return: float
    standard_deviation: float
    t_statistic: float
    confident: bool
    warning: str | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.confident

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "sample_size": self.sample_size,
            "mean_excess_return": self.mean_excess_return,
            "standard_deviation": self.standard_deviation,
            "t_statistic": self.t_statistic,
            "confident": self.confident,
            "passed": self.passed,
            "warning": self.warning,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StatisticalConfidenceReport:
    results: tuple[StatisticalConfidenceResult, ...]
    min_sample_size: int = 30
    min_t_statistic: float = 1.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def reason(self) -> str:
        if self.passed:
            return "statistical_confidence_passed"
        return next(result.reason for result in self.results if not result.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "min_sample_size": self.min_sample_size,
            "min_t_statistic": self.min_t_statistic,
            "results": [result.to_dict() for result in self.results],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ParameterDriftResult:
    strategy_name: str
    drift_by_parameter: Mapping[str, float]
    max_drift: float
    drifted: bool
    reason: str

    @property
    def passed(self) -> bool:
        return not self.drifted

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "drift_by_parameter": dict(self.drift_by_parameter),
            "max_drift": self.max_drift,
            "drifted": self.drifted,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ParameterDriftReport:
    results: tuple[ParameterDriftResult, ...]
    max_allowed_drift: float = 0.25
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def reason(self) -> str:
        if self.passed:
            return "parameter_drift_clear"
        return next(result.reason for result in self.results if not result.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_allowed_drift": self.max_allowed_drift,
            "results": [result.to_dict() for result in self.results],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class BoringBaselineControl:
    strategy_name: str
    symbol: str
    strategy_return_after_costs: float
    best_baseline_name: str
    best_baseline_return: float
    edge_over_best_baseline: float
    justified: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.justified

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "strategy_return_after_costs": self.strategy_return_after_costs,
            "best_baseline_name": self.best_baseline_name,
            "best_baseline_return": self.best_baseline_return,
            "edge_over_best_baseline": self.edge_over_best_baseline,
            "justified": self.justified,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BoringBaselineControlReport:
    controls: tuple[BoringBaselineControl, ...]
    min_edge_over_best_baseline: float = 0.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(control.passed for control in self.controls)

    @property
    def reason(self) -> str:
        if self.passed:
            return "boring_baseline_controls_passed"
        return next(control.reason for control in self.controls if not control.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "min_edge_over_best_baseline": self.min_edge_over_best_baseline,
            "controls": [control.to_dict() for control in self.controls],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class EnsemblePromotionDecision:
    strategy_name: str
    family: str
    proposed_weight: float
    benchmark_edge: float
    correlation_to_ensemble: float
    failure_modes: tuple[str, ...]
    promoted: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.promoted

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "family": self.family,
            "proposed_weight": self.proposed_weight,
            "benchmark_edge": self.benchmark_edge,
            "correlation_to_ensemble": self.correlation_to_ensemble,
            "failure_modes": list(self.failure_modes),
            "promoted": self.promoted,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EnsemblePromotionReport:
    decisions: tuple[EnsemblePromotionDecision, ...]
    max_correlation_to_ensemble: float = 0.70
    min_benchmark_edge: float = 0.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return any(decision.promoted for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "ensemble_has_promoted_members"
        return "no_ensemble_members_promoted"

    @property
    def promoted_strategies(self) -> tuple[str, ...]:
        return tuple(decision.strategy_name for decision in self.decisions if decision.promoted)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "max_correlation_to_ensemble": self.max_correlation_to_ensemble,
            "min_benchmark_edge": self.min_benchmark_edge,
            "promoted_strategies": list(self.promoted_strategies),
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class CandidateABPaperTest:
    symbol: str
    strategy_a: str
    strategy_b: str
    score_a: float
    score_b: float
    score_gap: float
    winner: str
    separate_manifests: bool
    tiny_parallel_exposure: bool
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy_a": self.strategy_a,
            "strategy_b": self.strategy_b,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "score_gap": self.score_gap,
            "winner": self.winner,
            "separate_manifests": self.separate_manifests,
            "tiny_parallel_exposure": self.tiny_parallel_exposure,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CandidateABPaperTestReport:
    tests: tuple[CandidateABPaperTest, ...]
    min_score_gap: float = 0.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(test.passed for test in self.tests)

    @property
    def reason(self) -> str:
        if self.passed:
            return "candidate_ab_paper_tests_passed"
        return next(test.reason for test in self.tests if not test.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "min_score_gap": self.min_score_gap,
            "tests": [test.to_dict() for test in self.tests],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StrategyOrderExplainabilitySummary:
    order_id: str
    strategy_name: str
    symbol: str
    signal_values: Mapping[str, Any]
    indicator_state: Mapping[str, Any]
    regime_state: Mapping[str, Any]
    risk_gates: Mapping[str, Any]
    expected_thesis: str
    complete: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.complete

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "signal_values": dict(self.signal_values),
            "indicator_state": dict(self.indicator_state),
            "regime_state": dict(self.regime_state),
            "risk_gates": dict(self.risk_gates),
            "expected_thesis": self.expected_thesis,
            "complete": self.complete,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyOrderExplainabilityReport:
    summaries: tuple[StrategyOrderExplainabilitySummary, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(summary.passed for summary in self.summaries)

    @property
    def reason(self) -> str:
        if self.passed:
            return "strategy_order_explainability_complete"
        return next(summary.reason for summary in self.summaries if not summary.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "summaries": [summary.to_dict() for summary in self.summaries],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StrategyExitReview:
    exit_id: str
    strategy_name: str
    symbol: str
    entry_thesis: str
    exit_reason: str
    pnl: float
    thesis_aligned: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.thesis_aligned

    def to_dict(self) -> dict:
        return {
            "exit_id": self.exit_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "entry_thesis": self.entry_thesis,
            "exit_reason": self.exit_reason,
            "pnl": self.pnl,
            "thesis_aligned": self.thesis_aligned,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyExitReviewReport:
    reviews: tuple[StrategyExitReview, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(review.passed for review in self.reviews)

    @property
    def reason(self) -> str:
        if self.passed:
            return "strategy_exit_reviews_passed"
        return next(review.reason for review in self.reviews if not review.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "reviews": [review.to_dict() for review in self.reviews],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StrategyAuditEntry:
    strategy_name: str
    status: str
    family: str
    reason: str
    last_reviewed_at: str | None
    needs_review: bool

    @property
    def passed(self) -> bool:
        return self.status in STRATEGY_STATUSES and bool(self.reason) and not self.needs_review

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "status": self.status,
            "family": self.family,
            "reason": self.reason,
            "last_reviewed_at": self.last_reviewed_at,
            "needs_review": self.needs_review,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class StrategyAuditReport:
    entries: tuple[StrategyAuditEntry, ...]
    generated_at: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(entry.passed for entry in self.entries)

    @property
    def reason(self) -> str:
        if self.passed:
            return "strategy_audit_current"
        return next(entry.reason for entry in self.entries if not entry.passed)

    @property
    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.status] = counts.get(entry.status, 0) + 1
        return counts

    def entries_by_status(self, status: str) -> tuple[StrategyAuditEntry, ...]:
        return tuple(entry for entry in self.entries if entry.status == status)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "generated_at": self.generated_at,
            "status_counts": self.status_counts,
            "active": [entry.to_dict() for entry in self.entries_by_status("paper-active")],
            "disabled": [entry.to_dict() for entry in self.entries_by_status("disabled")],
            "retired": [entry.to_dict() for entry in self.entries_by_status("retired")],
            "candidates": [entry.to_dict() for entry in self.entries_by_status("exploratory")],
            "live_eligible": [entry.to_dict() for entry in self.entries_by_status("live-eligible")],
            "entries": [entry.to_dict() for entry in self.entries],
            "artifact_path": self.artifact_path,
        }


def build_strategy_registry_report(entries: Sequence[Mapping[str, Any]]) -> StrategyRegistryReport:
    return StrategyRegistryReport(tuple(_registry_entry(entry) for entry in entries))


def build_strategy_retirement_report(
    rows: Sequence[Mapping[str, Any]],
    max_benchmark_failures: int = 3,
    max_paper_scorecard_failures: int = 2,
) -> StrategyRetirementReport:
    return StrategyRetirementReport(tuple(_retirement_decision(row, max_benchmark_failures, max_paper_scorecard_failures) for row in rows))


def build_strategy_quarantine_report(
    rows: Sequence[Mapping[str, Any]],
    max_return_drift: float = 0.10,
    max_slippage_drift_bps: float = 50.0,
    max_missed_fill_rate: float = 0.10,
    max_reject_rate: float = 0.05,
) -> StrategyQuarantineReport:
    return StrategyQuarantineReport(
        tuple(_quarantine_decision(row, max_return_drift, max_slippage_drift_bps, max_missed_fill_rate, max_reject_rate) for row in rows)
    )


def build_walk_forward_refresh_report(
    rows: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
    max_refresh_age_days: int = 30,
) -> WalkForwardRefreshReport:
    observed = now or datetime.now(timezone.utc)
    return WalkForwardRefreshReport(
        tuple(_walk_forward_decision(row, observed, max_refresh_age_days) for row in rows),
        max_refresh_age_days=max_refresh_age_days,
    )


def build_holdout_metadata_report(rows: Sequence[Mapping[str, Any]]) -> HoldoutMetadataReport:
    return HoldoutMetadataReport(tuple(_holdout_check(row) for row in rows))


def build_benchmark_paper_monitor_report(
    rows: Sequence[Mapping[str, Any]],
    min_excess_return_after_costs: float = 0.0,
) -> BenchmarkPaperMonitorReport:
    return BenchmarkPaperMonitorReport(
        tuple(_benchmark_paper_decision(row, min_excess_return_after_costs) for row in rows),
        min_excess_return_after_costs=min_excess_return_after_costs,
    )


def build_regime_conditioned_scorecard_report(
    rows: Sequence[Mapping[str, Any]],
    min_sample_size: int = 20,
    min_excess_return_after_costs: float = 0.0,
    max_drawdown: float = 0.20,
) -> RegimeConditionedScorecardReport:
    return RegimeConditionedScorecardReport(
        tuple(_regime_scorecard(row, min_sample_size, min_excess_return_after_costs, max_drawdown) for row in rows),
        min_sample_size=min_sample_size,
        min_excess_return_after_costs=min_excess_return_after_costs,
        max_drawdown=max_drawdown,
    )


def build_market_cluster_paper_scorecard_report(
    rows: Sequence[Mapping[str, Any]],
    min_symbols_tested: int = 3,
    min_pass_rate: float = 0.50,
    min_paper_sessions: int = 3,
) -> MarketClusterPaperScorecardReport:
    return MarketClusterPaperScorecardReport(
        tuple(_market_cluster_scorecard(row, min_symbols_tested, min_pass_rate, min_paper_sessions) for row in rows),
        min_symbols_tested=min_symbols_tested,
        min_pass_rate=min_pass_rate,
        min_paper_sessions=min_paper_sessions,
    )


def build_capacity_scorecard_report(
    rows: Sequence[Mapping[str, Any]],
    max_observed_slippage_bps: float = 25.0,
    max_volume_participation: float = 0.01,
) -> CapacityScorecardReport:
    return CapacityScorecardReport(
        tuple(_capacity_scorecard(row, max_observed_slippage_bps, max_volume_participation) for row in rows),
        max_observed_slippage_bps=max_observed_slippage_bps,
        max_volume_participation=max_volume_participation,
    )


def build_sample_size_gate_report(
    rows: Sequence[Mapping[str, Any]],
    min_trades: int = 30,
    min_sessions: int = 5,
    min_symbols: int = 1,
) -> SampleSizeGateReport:
    return SampleSizeGateReport(
        tuple(_sample_size_gate(row, min_trades, min_sessions, min_symbols) for row in rows),
        min_trades=min_trades,
        min_sessions=min_sessions,
        min_symbols=min_symbols,
    )


def build_statistical_confidence_report(
    rows: Sequence[Mapping[str, Any]],
    min_sample_size: int = 30,
    min_t_statistic: float = 1.0,
) -> StatisticalConfidenceReport:
    return StatisticalConfidenceReport(
        tuple(_statistical_confidence(row, min_sample_size, min_t_statistic) for row in rows),
        min_sample_size=min_sample_size,
        min_t_statistic=min_t_statistic,
    )


def build_parameter_drift_report(
    rows: Sequence[Mapping[str, Any]],
    max_allowed_drift: float = 0.25,
) -> ParameterDriftReport:
    return ParameterDriftReport(tuple(_parameter_drift(row, max_allowed_drift) for row in rows), max_allowed_drift=max_allowed_drift)


def build_boring_baseline_control_report(
    rows: Sequence[Mapping[str, Any]],
    min_edge_over_best_baseline: float = 0.0,
) -> BoringBaselineControlReport:
    return BoringBaselineControlReport(
        tuple(_boring_baseline_control(row, min_edge_over_best_baseline) for row in rows),
        min_edge_over_best_baseline=min_edge_over_best_baseline,
    )


def build_ensemble_promotion_report(
    rows: Sequence[Mapping[str, Any]],
    max_correlation_to_ensemble: float = 0.70,
    min_benchmark_edge: float = 0.0,
) -> EnsemblePromotionReport:
    promoted_failure_modes: set[str] = set()
    decisions = []
    for row in rows:
        decision = _ensemble_promotion_decision(row, promoted_failure_modes, max_correlation_to_ensemble, min_benchmark_edge)
        decisions.append(decision)
        if decision.promoted:
            promoted_failure_modes.update(decision.failure_modes)
    return EnsemblePromotionReport(
        tuple(decisions),
        max_correlation_to_ensemble=max_correlation_to_ensemble,
        min_benchmark_edge=min_benchmark_edge,
    )


def build_candidate_ab_paper_test_report(
    rows: Sequence[Mapping[str, Any]],
    min_score_gap: float = 0.0,
) -> CandidateABPaperTestReport:
    return CandidateABPaperTestReport(tuple(_candidate_ab_test(row, min_score_gap) for row in rows), min_score_gap=min_score_gap)


def build_strategy_order_explainability_report(rows: Sequence[Mapping[str, Any]]) -> StrategyOrderExplainabilityReport:
    return StrategyOrderExplainabilityReport(tuple(_strategy_order_explainability(row) for row in rows))


def build_strategy_exit_review_report(rows: Sequence[Mapping[str, Any]]) -> StrategyExitReviewReport:
    return StrategyExitReviewReport(tuple(_strategy_exit_review(row) for row in rows))


def build_strategy_audit_report(
    rows: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
    max_review_age_days: int = 30,
) -> StrategyAuditReport:
    observed = now or datetime.now(timezone.utc)
    return StrategyAuditReport(
        tuple(_strategy_audit_entry(row, observed, max_review_age_days) for row in rows),
        generated_at=observed.isoformat(),
    )


def write_strategy_registry_report(report: StrategyRegistryReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_strategy_retirement_report(report: StrategyRetirementReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_strategy_quarantine_report(report: StrategyQuarantineReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_walk_forward_refresh_report(report: WalkForwardRefreshReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_holdout_metadata_report(report: HoldoutMetadataReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_benchmark_paper_monitor_report(report: BenchmarkPaperMonitorReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_regime_conditioned_scorecard_report(report: RegimeConditionedScorecardReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_market_cluster_paper_scorecard_report(report: MarketClusterPaperScorecardReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_capacity_scorecard_report(report: CapacityScorecardReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_sample_size_gate_report(report: SampleSizeGateReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_statistical_confidence_report(report: StatisticalConfidenceReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_parameter_drift_report(report: ParameterDriftReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_boring_baseline_control_report(report: BoringBaselineControlReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_ensemble_promotion_report(report: EnsemblePromotionReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_candidate_ab_paper_test_report(report: CandidateABPaperTestReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_strategy_order_explainability_report(report: StrategyOrderExplainabilityReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_strategy_exit_review_report(report: StrategyExitReviewReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_strategy_audit_report(report: StrategyAuditReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def _registry_entry(entry: Mapping[str, Any]) -> StrategyRegistryEntry:
    return StrategyRegistryEntry(
        strategy_name=str(entry.get("strategy_name") or entry.get("strategy") or "unknown"),
        status=str(entry.get("status") or "exploratory"),
        family=str(entry.get("family") or "default"),
        symbol_scope=tuple(str(symbol).upper() for symbol in entry.get("symbol_scope", ()) or ()),
        reason=str(entry.get("reason") or "registered"),
        metadata=entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {},
    )


def _retirement_decision(row: Mapping[str, Any], max_benchmark_failures: int, max_paper_scorecard_failures: int) -> StrategyRetirementDecision:
    benchmark_failures = int(row.get("benchmark_failures", 0) or 0)
    paper_failures = int(row.get("paper_scorecard_failures", 0) or 0)
    retired = benchmark_failures >= max_benchmark_failures or paper_failures >= max_paper_scorecard_failures
    if benchmark_failures >= max_benchmark_failures:
        reason = "benchmark_failures_retired"
    elif paper_failures >= max_paper_scorecard_failures:
        reason = "paper_scorecard_failures_retired"
    else:
        reason = "retirement_rules_clear"
    return StrategyRetirementDecision(str(row.get("strategy_name") or row.get("strategy") or "unknown"), retired, benchmark_failures, paper_failures, reason)


def _quarantine_decision(
    row: Mapping[str, Any],
    max_return_drift: float,
    max_slippage_drift_bps: float,
    max_missed_fill_rate: float,
    max_reject_rate: float,
) -> StrategyQuarantineDecision:
    return_drift = abs(_optional_float(row.get("return_drift")) or 0.0)
    slippage_drift = abs(_optional_float(row.get("slippage_drift_bps")) or 0.0)
    missed_fill_rate = _optional_float(row.get("missed_fill_rate")) or 0.0
    reject_rate = _optional_float(row.get("reject_rate")) or 0.0
    reason = "quarantine_rules_clear"
    if return_drift > max_return_drift:
        reason = "return_drift_quarantine"
    elif slippage_drift > max_slippage_drift_bps:
        reason = "slippage_drift_quarantine"
    elif missed_fill_rate > max_missed_fill_rate:
        reason = "missed_fill_quarantine"
    elif reject_rate > max_reject_rate:
        reason = "reject_rate_quarantine"
    return StrategyQuarantineDecision(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        quarantined=reason != "quarantine_rules_clear",
        return_drift=return_drift,
        slippage_drift_bps=slippage_drift,
        missed_fill_rate=missed_fill_rate,
        reject_rate=reject_rate,
        reason=reason,
    )


def _walk_forward_decision(row: Mapping[str, Any], observed: datetime, max_refresh_age_days: int) -> WalkForwardRefreshDecision:
    status = str(row.get("status") or "exploratory")
    refreshed = _parse_datetime(row.get("last_refresh_at"))
    days = (observed - refreshed).days if refreshed else None
    oos_passed = bool(row.get("out_of_sample_passed", False))
    if status not in {"paper-active", "live-eligible"}:
        action = "keep_inactive"
        reason = "strategy_not_paper_active"
    elif days is None or days > max_refresh_age_days:
        action = "refresh_due"
        reason = "walk_forward_refresh_due"
    elif not oos_passed:
        action = "disable"
        reason = "walk_forward_oos_failed"
    elif status == "paper-active" and bool(row.get("promotion_eligible", False)):
        action = "promote"
        reason = "walk_forward_promote"
    else:
        action = "keep_active"
        reason = "walk_forward_current"
    return WalkForwardRefreshDecision(str(row.get("strategy_name") or row.get("strategy") or "unknown"), status, days, action, reason)


def _holdout_check(row: Mapping[str, Any]) -> HoldoutMetadataCheck:
    train_start = _date_text(row.get("train_start"))
    train_end = _date_text(row.get("train_end"))
    validation_start = _date_text(row.get("validation_start"))
    validation_end = _date_text(row.get("validation_end"))
    test_start = _date_text(row.get("test_start"))
    test_end = _date_text(row.get("test_end"))
    reason = "passed"
    if not all((train_start, train_end, validation_start, validation_end, test_start, test_end)):
        reason = "missing_split_metadata"
    elif not (train_end < validation_start and validation_end < test_start):
        reason = "split_windows_overlap"
    elif bool(row.get("retuned_on_holdout", False)):
        reason = "holdout_retuning_detected"
    return HoldoutMetadataCheck(
        str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        train_start,
        train_end,
        validation_start,
        validation_end,
        test_start,
        test_end,
        reason,
    )


def _benchmark_paper_decision(row: Mapping[str, Any], min_excess_return_after_costs: float) -> BenchmarkPaperMonitorDecision:
    strategy_return = _optional_float(row.get("strategy_return_after_costs") or row.get("strategy_return")) or 0.0
    benchmark_return = _optional_float(row.get("benchmark_return")) or 0.0
    excess = strategy_return - benchmark_return
    disabled = excess < min_excess_return_after_costs
    return BenchmarkPaperMonitorDecision(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        symbol=str(row.get("symbol") or "").upper(),
        strategy_return_after_costs=strategy_return,
        benchmark_return=benchmark_return,
        excess_return_after_costs=excess,
        disabled=disabled,
        reason="benchmark_underperformance_disable" if disabled else "benchmark_relative_paper_passed",
    )


def _regime_scorecard(
    row: Mapping[str, Any],
    min_sample_size: int,
    min_excess_return_after_costs: float,
    max_drawdown: float,
) -> RegimeConditionedScorecard:
    sample_size = int(row.get("sample_size") or row.get("trades") or 0)
    excess = _optional_float(row.get("excess_return_after_costs") or row.get("excess_return")) or 0.0
    drawdown = abs(_optional_float(row.get("max_drawdown")) or 0.0)
    if sample_size < min_sample_size:
        reason = "regime_sample_too_small"
    elif excess < min_excess_return_after_costs:
        reason = "regime_excess_return_too_low"
    elif drawdown > max_drawdown:
        reason = "regime_drawdown_too_high"
    else:
        reason = "regime_tradable"
    return RegimeConditionedScorecard(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        regime=str(row.get("regime") or "unknown"),
        sample_size=sample_size,
        excess_return_after_costs=excess,
        max_drawdown=drawdown,
        tradable=reason == "regime_tradable",
        reason=reason,
    )


def _market_cluster_scorecard(
    row: Mapping[str, Any],
    min_symbols_tested: int,
    min_pass_rate: float,
    min_paper_sessions: int,
) -> MarketClusterPaperScorecard:
    symbols_tested = int(row.get("symbols_tested") or row.get("symbols") or 0)
    pass_rate = _optional_float(row.get("pass_rate")) or 0.0
    paper_sessions = int(row.get("paper_sessions") or row.get("sessions") or 0)
    average_excess = _optional_float(row.get("average_excess_return_after_costs") or row.get("average_excess_return")) or 0.0
    if symbols_tested < min_symbols_tested:
        reason = "cluster_symbol_sample_too_small"
    elif paper_sessions < min_paper_sessions:
        reason = "cluster_paper_sessions_too_few"
    elif pass_rate < min_pass_rate:
        reason = "cluster_pass_rate_too_low"
    elif average_excess < 0:
        reason = "cluster_average_excess_negative"
    else:
        reason = "market_cluster_tradable"
    return MarketClusterPaperScorecard(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        cluster=str(row.get("cluster") or "unknown"),
        asset_class=str(row.get("asset_class") or "unknown"),
        symbols_tested=symbols_tested,
        pass_rate=pass_rate,
        average_excess_return_after_costs=average_excess,
        paper_sessions=paper_sessions,
        tradable=reason == "market_cluster_tradable",
        reason=reason,
    )


def _capacity_scorecard(row: Mapping[str, Any], max_observed_slippage_bps: float, max_volume_participation: float) -> CapacityScorecard:
    target_notional = _optional_float(row.get("target_notional")) or 0.0
    slippage = abs(_optional_float(row.get("observed_slippage_bps")) or 0.0)
    participation = _optional_float(row.get("volume_participation")) or 0.0
    capacity = _optional_float(row.get("estimated_capacity_notional"))
    if slippage > max_observed_slippage_bps:
        reason = "capacity_slippage_too_high"
    elif participation > max_volume_participation:
        reason = "capacity_volume_participation_too_high"
    elif capacity is not None and target_notional > capacity:
        reason = "target_notional_above_capacity"
    else:
        reason = "capacity_ok"
    return CapacityScorecard(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        symbol=str(row.get("symbol") or "").upper(),
        target_notional=target_notional,
        observed_slippage_bps=slippage,
        volume_participation=participation,
        estimated_capacity_notional=capacity,
        capacity_ok=reason == "capacity_ok",
        reason=reason,
    )


def _sample_size_gate(row: Mapping[str, Any], min_trades: int, min_sessions: int, min_symbols: int) -> SampleSizeGate:
    trades = int(row.get("trades") or 0)
    sessions = int(row.get("sessions") or row.get("paper_sessions") or 0)
    symbols = int(row.get("symbols") or row.get("symbols_tested") or 0)
    if trades < min_trades:
        reason = "sample_trades_too_few"
    elif sessions < min_sessions:
        reason = "sample_sessions_too_few"
    elif symbols < min_symbols:
        reason = "sample_symbols_too_few"
    else:
        reason = "sample_size_passed"
    return SampleSizeGate(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        trades=trades,
        sessions=sessions,
        symbols=symbols,
        passed=reason == "sample_size_passed",
        reason=reason,
    )


def _statistical_confidence(row: Mapping[str, Any], min_sample_size: int, min_t_statistic: float) -> StatisticalConfidenceResult:
    values = _float_sequence(row.get("excess_returns"))
    if values:
        sample_size = len(values)
        mean = sum(values) / sample_size
        variance = sum((value - mean) ** 2 for value in values) / (sample_size - 1) if sample_size > 1 else 0.0
        standard_deviation = sqrt(variance)
    else:
        sample_size = int(row.get("sample_size") or 0)
        mean = _optional_float(row.get("mean_excess_return")) or 0.0
        standard_deviation = abs(_optional_float(row.get("standard_deviation") or row.get("std_excess_return")) or 0.0)
    t_statistic = 0.0
    if sample_size > 0 and standard_deviation > 0:
        t_statistic = mean / (standard_deviation / sqrt(sample_size))
    elif sample_size > 0 and mean > 0:
        t_statistic = float("inf")
    warning = "sample_size_too_small" if sample_size < min_sample_size else None
    if warning:
        reason = warning
    elif mean <= 0:
        reason = "mean_excess_return_not_positive"
    elif t_statistic < min_t_statistic:
        reason = "confidence_t_statistic_too_low"
    else:
        reason = "statistical_confidence_passed"
    return StatisticalConfidenceResult(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        sample_size=sample_size,
        mean_excess_return=mean,
        standard_deviation=standard_deviation,
        t_statistic=t_statistic,
        confident=reason == "statistical_confidence_passed",
        warning=warning,
        reason=reason,
    )


def _parameter_drift(row: Mapping[str, Any], max_allowed_drift: float) -> ParameterDriftResult:
    approved = row.get("approved_params") if isinstance(row.get("approved_params"), Mapping) else {}
    current = row.get("current_params") if isinstance(row.get("current_params"), Mapping) else {}
    names = sorted(set(approved) | set(current))
    drift_by_parameter = {name: _parameter_value_drift(approved.get(name), current.get(name)) for name in names}
    max_drift = max(drift_by_parameter.values(), default=0.0)
    drifted = max_drift > max_allowed_drift
    return ParameterDriftResult(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        drift_by_parameter=drift_by_parameter,
        max_drift=max_drift,
        drifted=drifted,
        reason="parameter_drift_detected" if drifted else "parameter_drift_clear",
    )


def _boring_baseline_control(row: Mapping[str, Any], min_edge_over_best_baseline: float) -> BoringBaselineControl:
    strategy_return = _optional_float(row.get("strategy_return_after_costs") or row.get("strategy_return")) or 0.0
    baselines = row.get("baselines") if isinstance(row.get("baselines"), Mapping) else {}
    if not baselines:
        baselines = {
            "buy_hold": row.get("buy_hold_return", 0.0),
            "cash": row.get("cash_return", 0.0),
            "simple_trend": row.get("simple_trend_return", 0.0),
            "risk_parity": row.get("risk_parity_return", 0.0),
        }
    parsed_baselines = {str(name): (_optional_float(value) or 0.0) for name, value in baselines.items()}
    best_name, best_return = max(parsed_baselines.items(), key=lambda item: item[1]) if parsed_baselines else ("none", 0.0)
    edge = strategy_return - best_return
    justified = edge >= min_edge_over_best_baseline
    return BoringBaselineControl(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        symbol=str(row.get("symbol") or "").upper(),
        strategy_return_after_costs=strategy_return,
        best_baseline_name=best_name,
        best_baseline_return=best_return,
        edge_over_best_baseline=edge,
        justified=justified,
        reason="boring_baseline_justified" if justified else "boring_baseline_not_beaten",
    )


def _ensemble_promotion_decision(
    row: Mapping[str, Any],
    promoted_failure_modes: set[str],
    max_correlation_to_ensemble: float,
    min_benchmark_edge: float,
) -> EnsemblePromotionDecision:
    edge = _optional_float(row.get("benchmark_edge") or row.get("excess_return_after_costs")) or 0.0
    correlation = abs(_optional_float(row.get("correlation_to_ensemble")) or 0.0)
    failure_modes = tuple(str(mode) for mode in row.get("failure_modes", ()) or ())
    overlapping_modes = promoted_failure_modes.intersection(failure_modes)
    if edge < min_benchmark_edge:
        reason = "ensemble_benchmark_edge_too_low"
    elif correlation > max_correlation_to_ensemble:
        reason = "ensemble_correlation_too_high"
    elif overlapping_modes:
        reason = "ensemble_failure_modes_overlap"
    else:
        reason = "ensemble_member_promoted"
    return EnsemblePromotionDecision(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        family=str(row.get("family") or "default"),
        proposed_weight=_optional_float(row.get("proposed_weight") or row.get("weight")) or 0.0,
        benchmark_edge=edge,
        correlation_to_ensemble=correlation,
        failure_modes=failure_modes,
        promoted=reason == "ensemble_member_promoted",
        reason=reason,
    )


def _candidate_ab_test(row: Mapping[str, Any], min_score_gap: float) -> CandidateABPaperTest:
    score_a = _optional_float(row.get("score_a")) or 0.0
    score_b = _optional_float(row.get("score_b")) or 0.0
    gap = abs(score_a - score_b)
    winner = str(row.get("strategy_a") if score_a >= score_b else row.get("strategy_b"))
    separate_manifests = bool(row.get("separate_manifests", False))
    tiny_parallel_exposure = bool(row.get("tiny_parallel_exposure", False))
    if not separate_manifests:
        reason = "ab_test_missing_separate_manifests"
    elif not tiny_parallel_exposure:
        reason = "ab_test_not_tiny_parallel_exposure"
    elif gap < min_score_gap:
        reason = "ab_test_score_gap_too_small"
    else:
        reason = "ab_test_passed"
    return CandidateABPaperTest(
        symbol=str(row.get("symbol") or "").upper(),
        strategy_a=str(row.get("strategy_a") or "strategy_a"),
        strategy_b=str(row.get("strategy_b") or "strategy_b"),
        score_a=score_a,
        score_b=score_b,
        score_gap=gap,
        winner=winner,
        separate_manifests=separate_manifests,
        tiny_parallel_exposure=tiny_parallel_exposure,
        passed=reason == "ab_test_passed",
        reason=reason,
    )


def _strategy_order_explainability(row: Mapping[str, Any]) -> StrategyOrderExplainabilitySummary:
    signal_values = row.get("signal_values") if isinstance(row.get("signal_values"), Mapping) else {}
    indicator_state = row.get("indicator_state") if isinstance(row.get("indicator_state"), Mapping) else {}
    regime_state = row.get("regime_state") if isinstance(row.get("regime_state"), Mapping) else {}
    risk_gates = row.get("risk_gates") if isinstance(row.get("risk_gates"), Mapping) else {}
    thesis = str(row.get("expected_thesis") or row.get("thesis") or "")
    if not signal_values:
        reason = "missing_signal_values"
    elif not indicator_state:
        reason = "missing_indicator_state"
    elif not regime_state:
        reason = "missing_regime_state"
    elif not risk_gates:
        reason = "missing_risk_gates"
    elif not all(bool(value) for value in risk_gates.values()):
        reason = "risk_gate_failed"
    elif not thesis:
        reason = "missing_expected_thesis"
    else:
        reason = "order_explainability_complete"
    return StrategyOrderExplainabilitySummary(
        order_id=str(row.get("order_id") or "unknown"),
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        symbol=str(row.get("symbol") or "").upper(),
        signal_values=signal_values,
        indicator_state=indicator_state,
        regime_state=regime_state,
        risk_gates=risk_gates,
        expected_thesis=thesis,
        complete=reason == "order_explainability_complete",
        reason=reason,
    )


def _strategy_exit_review(row: Mapping[str, Any]) -> StrategyExitReview:
    thesis = str(row.get("entry_thesis") or row.get("thesis") or "")
    exit_reason = str(row.get("exit_reason") or "")
    thesis_aligned = bool(row.get("exit_matches_thesis", row.get("thesis_aligned", False)))
    if not thesis:
        reason = "missing_original_thesis"
    elif not exit_reason:
        reason = "missing_exit_reason"
    elif not thesis_aligned:
        reason = "exit_not_aligned_with_thesis"
    else:
        reason = "exit_review_passed"
    return StrategyExitReview(
        exit_id=str(row.get("exit_id") or row.get("order_id") or "unknown"),
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        symbol=str(row.get("symbol") or "").upper(),
        entry_thesis=thesis,
        exit_reason=exit_reason,
        pnl=_optional_float(row.get("pnl")) or 0.0,
        thesis_aligned=reason == "exit_review_passed",
        reason=reason,
    )


def _strategy_audit_entry(row: Mapping[str, Any], observed: datetime, max_review_age_days: int) -> StrategyAuditEntry:
    status = str(row.get("status") or "exploratory")
    reason = str(row.get("reason") or "")
    reviewed = _parse_datetime(row.get("last_reviewed_at"))
    last_reviewed_at = reviewed.isoformat() if reviewed else None
    stale_review = reviewed is None or (observed - reviewed).days > max_review_age_days
    if status not in STRATEGY_STATUSES:
        audit_reason = "unknown_strategy_status"
    elif not reason:
        audit_reason = "missing_strategy_audit_reason"
    elif stale_review:
        audit_reason = "strategy_audit_review_stale"
    else:
        audit_reason = reason
    return StrategyAuditEntry(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        status=status,
        family=str(row.get("family") or "default"),
        reason=audit_reason,
        last_reviewed_at=last_reviewed_at,
        needs_review=audit_reason in {"unknown_strategy_status", "missing_strategy_audit_reason", "strategy_audit_review_stale"},
    )


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _date_text(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else None


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


def _float_sequence(value: Any) -> tuple[float, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(float(item) for item in value)
    return ()


def _parameter_value_drift(approved: Any, current: Any) -> float:
    approved_number = _try_float(approved)
    current_number = _try_float(current)
    if approved_number is not None and current_number is not None:
        denominator = max(abs(approved_number), 1.0)
        return abs(current_number - approved_number) / denominator
    return 0.0 if approved == current else 1.0


def _try_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
