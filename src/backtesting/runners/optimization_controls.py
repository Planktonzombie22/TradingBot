import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class OptimizationReproducibilityCheck:
    name: str
    passed: bool
    baseline_value: Any
    candidate_value: Any
    reason: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "baseline_value": self.baseline_value,
            "candidate_value": self.candidate_value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OptimizationReproducibilityReport:
    checks: tuple[OptimizationReproducibilityCheck, ...]
    score_tolerance: float = 1e-9
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "optimization_reproducibility_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "score_tolerance": self.score_tolerance,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class OptimizationBudgetReport:
    trials_run: int
    failed_trials: int
    runtime_seconds: float
    memory_mb: float
    max_trials: int = 100
    max_runtime_seconds: float = 900.0
    max_memory_mb: float = 4096.0
    max_failed_trial_rate: float = 0.20
    artifact_path: str | None = None

    @property
    def failed_trial_rate(self) -> float:
        return self.failed_trials / self.trials_run if self.trials_run else 0.0

    @property
    def passed(self) -> bool:
        return (
            self.trials_run <= self.max_trials
            and self.runtime_seconds <= self.max_runtime_seconds
            and self.memory_mb <= self.max_memory_mb
            and self.failed_trial_rate <= self.max_failed_trial_rate
        )

    @property
    def reason(self) -> str:
        if self.trials_run > self.max_trials:
            return "optimization_trial_budget_exceeded"
        if self.runtime_seconds > self.max_runtime_seconds:
            return "optimization_runtime_budget_exceeded"
        if self.memory_mb > self.max_memory_mb:
            return "optimization_memory_budget_exceeded"
        if self.failed_trial_rate > self.max_failed_trial_rate:
            return "optimization_failed_trial_rate_exceeded"
        return "optimization_budget_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "trials_run": self.trials_run,
            "failed_trials": self.failed_trials,
            "failed_trial_rate": self.failed_trial_rate,
            "runtime_seconds": self.runtime_seconds,
            "memory_mb": self.memory_mb,
            "max_trials": self.max_trials,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_memory_mb": self.max_memory_mb,
            "max_failed_trial_rate": self.max_failed_trial_rate,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PromotionOverfittingWarning:
    name: str
    triggered: bool
    value: float | int | None
    threshold: float | int | None
    reason: str

    @property
    def passed(self) -> bool:
        return not self.triggered

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "triggered": self.triggered,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PromotionOverfittingWarningReport:
    warnings: tuple[PromotionOverfittingWarning, ...]
    manifest: Mapping[str, Any] = field(default_factory=dict)
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(warning.passed for warning in self.warnings)

    @property
    def reason(self) -> str:
        if self.passed:
            return "promotion_manifest_overfitting_warnings_clear"
        return next(warning.reason for warning in self.warnings if warning.triggered)

    @property
    def warning_reasons(self) -> tuple[str, ...]:
        return tuple(warning.reason for warning in self.warnings if warning.triggered)

    def to_dict(self) -> dict:
        payload = dict(self.manifest)
        payload["overfitting_warnings"] = [warning.to_dict() for warning in self.warnings]
        payload["warning_reasons"] = list(self.warning_reasons)
        return {
            "passed": self.passed,
            "reason": self.reason,
            "manifest": payload,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class SurvivorshipBiasSymbolCheck:
    symbol: str
    included: bool
    listed_at: str | None
    delisted_at: str | None
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "included": self.included,
            "listed_at": self.listed_at,
            "delisted_at": self.delisted_at,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SurvivorshipBiasAwarenessReport:
    checks: tuple[SurvivorshipBiasSymbolCheck, ...]
    backtest_start: str
    backtest_end: str
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def reason(self) -> str:
        if self.passed:
            return "survivorship_bias_awareness_passed"
        return next(check.reason for check in self.checks if not check.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "backtest_start": self.backtest_start,
            "backtest_end": self.backtest_end,
            "checks": [check.to_dict() for check in self.checks],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class WalkForwardDeploymentDecision:
    strategy_name: str
    symbol: str
    decision_at: str
    selected_at: str
    latest_data_used_at: str
    deployment_start_at: str
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "decision_at": self.decision_at,
            "selected_at": self.selected_at,
            "latest_data_used_at": self.latest_data_used_at,
            "deployment_start_at": self.deployment_start_at,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WalkForwardDeploymentSimulationReport:
    decisions: tuple[WalkForwardDeploymentDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "walk_forward_deployment_simulation_passed"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


def build_optimization_reproducibility_report(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    score_tolerance: float = 1e-9,
) -> OptimizationReproducibilityReport:
    checks = (
        _exact_check("code_version", baseline, candidate, "optimization_code_version_mismatch"),
        _exact_check("dependency_versions", baseline, candidate, "optimization_dependency_versions_mismatch"),
        _exact_check("sampler_seed", baseline, candidate, "optimization_seed_mismatch"),
        _exact_check("best_params", baseline, candidate, "optimization_best_params_mismatch"),
        _score_check(baseline, candidate, score_tolerance),
    )
    return OptimizationReproducibilityReport(checks, score_tolerance=score_tolerance)


def build_optimization_budget_report(
    trials_run: int,
    failed_trials: int,
    runtime_seconds: float,
    memory_mb: float,
    max_trials: int = 100,
    max_runtime_seconds: float = 900.0,
    max_memory_mb: float = 4096.0,
    max_failed_trial_rate: float = 0.20,
) -> OptimizationBudgetReport:
    return OptimizationBudgetReport(
        trials_run=trials_run,
        failed_trials=failed_trials,
        runtime_seconds=runtime_seconds,
        memory_mb=memory_mb,
        max_trials=max_trials,
        max_runtime_seconds=max_runtime_seconds,
        max_memory_mb=max_memory_mb,
        max_failed_trial_rate=max_failed_trial_rate,
    )


def build_promotion_overfitting_warning_report(
    manifest: Mapping[str, Any],
    parameter_stability_score: float,
    false_discovery_rate: float,
    train_score: float,
    holdout_score: float,
    trials: int,
    min_parameter_stability_score: float = 0.50,
    max_false_discovery_rate: float = 0.50,
    max_train_holdout_gap: float = 0.10,
    max_trials_without_budget_review: int = 100,
) -> PromotionOverfittingWarningReport:
    train_holdout_gap = train_score - holdout_score
    warnings = (
        _warning("parameter_stability", parameter_stability_score < min_parameter_stability_score, parameter_stability_score, min_parameter_stability_score, "parameter_surface_unstable"),
        _warning("false_discovery_rate", false_discovery_rate > max_false_discovery_rate, false_discovery_rate, max_false_discovery_rate, "false_discovery_rate_warning"),
        _warning("train_holdout_gap", train_holdout_gap > max_train_holdout_gap, train_holdout_gap, max_train_holdout_gap, "train_holdout_gap_warning"),
        _warning("trial_count", trials > max_trials_without_budget_review, trials, max_trials_without_budget_review, "optimization_trial_count_warning"),
    )
    return PromotionOverfittingWarningReport(warnings=warnings, manifest=dict(manifest))


def build_survivorship_bias_awareness_report(
    rows: Sequence[Mapping[str, Any]],
    backtest_start: Any,
    backtest_end: Any,
) -> SurvivorshipBiasAwarenessReport:
    start = _parse_datetime(backtest_start)
    end = _parse_datetime(backtest_end)
    if start is None or end is None:
        raise ValueError("backtest_start and backtest_end must be valid datetimes.")
    checks = tuple(_survivorship_check(row, start, end) for row in rows)
    return SurvivorshipBiasAwarenessReport(checks, backtest_start=start.isoformat(), backtest_end=end.isoformat())


def build_walk_forward_deployment_simulation_report(rows: Sequence[Mapping[str, Any]]) -> WalkForwardDeploymentSimulationReport:
    return WalkForwardDeploymentSimulationReport(tuple(_deployment_decision(row) for row in rows))


def write_optimization_reproducibility_report(report: OptimizationReproducibilityReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_optimization_budget_report(report: OptimizationBudgetReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_promotion_overfitting_warning_report(report: PromotionOverfittingWarningReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_survivorship_bias_awareness_report(report: SurvivorshipBiasAwarenessReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_walk_forward_deployment_simulation_report(report: WalkForwardDeploymentSimulationReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def _exact_check(name: str, baseline: Mapping[str, Any], candidate: Mapping[str, Any], reason: str) -> OptimizationReproducibilityCheck:
    baseline_value = baseline.get(name)
    candidate_value = candidate.get(name)
    passed = baseline_value == candidate_value
    return OptimizationReproducibilityCheck(name, passed, baseline_value, candidate_value, "passed" if passed else reason)


def _score_check(baseline: Mapping[str, Any], candidate: Mapping[str, Any], tolerance: float) -> OptimizationReproducibilityCheck:
    baseline_score = _optional_float(baseline.get("best_score"))
    candidate_score = _optional_float(candidate.get("best_score"))
    passed = baseline_score is not None and candidate_score is not None and abs(baseline_score - candidate_score) <= tolerance
    return OptimizationReproducibilityCheck(
        "best_score",
        passed,
        baseline_score,
        candidate_score,
        "passed" if passed else "optimization_best_score_mismatch",
    )


def _warning(name: str, triggered: bool, value: float | int, threshold: float | int, reason: str) -> PromotionOverfittingWarning:
    return PromotionOverfittingWarning(name, triggered, value, threshold, reason if triggered else "passed")


def _survivorship_check(row: Mapping[str, Any], start: datetime, end: datetime) -> SurvivorshipBiasSymbolCheck:
    listed_at = _parse_datetime(row.get("listed_at"))
    delisted_at = _parse_datetime(row.get("delisted_at"))
    included = bool(row.get("included", True))
    if listed_at is None:
        reason = "missing_listing_date"
    elif listed_at > start and included:
        reason = "symbol_listed_after_backtest_start"
    elif delisted_at is not None and start <= delisted_at <= end and included:
        reason = "delisted_symbol_included_without_bias_control"
    else:
        reason = "survivorship_bias_check_passed"
    return SurvivorshipBiasSymbolCheck(
        symbol=str(row.get("symbol") or "").upper(),
        included=included,
        listed_at=listed_at.isoformat() if listed_at else None,
        delisted_at=delisted_at.isoformat() if delisted_at else None,
        passed=reason == "survivorship_bias_check_passed",
        reason=reason,
    )


def _deployment_decision(row: Mapping[str, Any]) -> WalkForwardDeploymentDecision:
    decision_at = _required_datetime(row.get("decision_at"))
    selected_at = _required_datetime(row.get("selected_at") or row.get("manifest_selected_at"))
    latest_data_used_at = _required_datetime(row.get("latest_data_used_at") or row.get("train_end"))
    deployment_start_at = _required_datetime(row.get("deployment_start_at"))
    if latest_data_used_at > decision_at:
        reason = "deployment_used_future_data"
    elif selected_at > deployment_start_at:
        reason = "manifest_selected_after_deployment_start"
    elif decision_at > deployment_start_at:
        reason = "deployment_decision_after_start"
    else:
        reason = "walk_forward_deployment_prior_data_passed"
    return WalkForwardDeploymentDecision(
        strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
        symbol=str(row.get("symbol") or "").upper(),
        decision_at=decision_at.isoformat(),
        selected_at=selected_at.isoformat(),
        latest_data_used_at=latest_data_used_at.isoformat(),
        deployment_start_at=deployment_start_at.isoformat(),
        passed=reason == "walk_forward_deployment_prior_data_passed",
        reason=reason,
    )


def _required_datetime(value: Any) -> datetime:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError("deployment simulation timestamps are required.")
    return parsed


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
