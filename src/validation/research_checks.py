from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .broker_checks import ValidationProbe


@dataclass(frozen=True)
class BacktestDifferentialScenario:
    name: str
    observed: Mapping[str, Any]
    reference: Mapping[str, Any]
    tolerances: Mapping[str, float] = field(default_factory=dict)
    required_fields: tuple[str, ...] = ("total_return", "ending_equity", "fills")


@dataclass(frozen=True)
class BacktestDifferentialReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "probes": [probe.to_dict() for probe in self.probes]}


@dataclass(frozen=True)
class StrategyRobustnessCase:
    name: str
    walk_forward_passed: bool
    parameter_stability: float
    cluster_pass_rate: float
    cost_stress_passed: bool
    benchmark_relative_passed: bool
    min_parameter_stability: float = 0.50
    min_cluster_pass_rate: float = 0.60
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyRobustnessReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "probes": [probe.to_dict() for probe in self.probes]}


@dataclass(frozen=True)
class OptimizerValidationCase:
    name: str
    seeded_reproducible: bool
    train_test_separated: bool
    no_lookahead_detected: bool
    persistence_reloaded: bool
    failed_trials_handled: bool
    objective_metric_correct: bool
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptimizerValidationReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "probes": [probe.to_dict() for probe in self.probes]}


@dataclass(frozen=True)
class PortfolioRiskStressScenario:
    name: str
    expected_action: str
    observed_action: str
    exposure: float = 0.0
    limit: float | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioRiskStressReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "probes": [probe.to_dict() for probe in self.probes]}


def evaluate_backtest_differential(scenarios: Sequence[BacktestDifferentialScenario]) -> BacktestDifferentialReport:
    probes: list[ValidationProbe] = []
    for scenario in scenarios:
        missing = [field for field in scenario.required_fields if field not in scenario.observed or field not in scenario.reference]
        if missing:
            probes.append(
                ValidationProbe(
                    scenario.name,
                    False,
                    "missing_required_fields",
                    {"missing_fields": missing, "required_fields": list(scenario.required_fields)},
                )
            )
            continue
        deltas = {}
        failures = {}
        for field in scenario.required_fields:
            observed = scenario.observed[field]
            reference = scenario.reference[field]
            tolerance = float(scenario.tolerances.get(field, 0.0))
            if isinstance(observed, (int, float)) and isinstance(reference, (int, float)):
                delta = abs(float(observed) - float(reference))
                deltas[field] = delta
                if delta > tolerance:
                    failures[field] = {"observed": observed, "reference": reference, "delta": delta, "tolerance": tolerance}
            else:
                equal = observed == reference
                deltas[field] = 0.0 if equal else 1.0
                if not equal:
                    failures[field] = {"observed": observed, "reference": reference, "tolerance": tolerance}
        probes.append(
            ValidationProbe(
                scenario.name,
                not failures,
                "passed" if not failures else "backtest_differential_mismatch",
                {
                    "deltas": deltas,
                    "failures": failures,
                    "observed": dict(scenario.observed),
                    "reference": dict(scenario.reference),
                    "tolerances": dict(scenario.tolerances),
                },
            )
        )
    return BacktestDifferentialReport(tuple(probes))


def evaluate_strategy_robustness(cases: Sequence[StrategyRobustnessCase]) -> StrategyRobustnessReport:
    probes: list[ValidationProbe] = []
    for case in cases:
        checks = {
            "walk_forward_passed": case.walk_forward_passed,
            "parameter_stability": case.parameter_stability >= case.min_parameter_stability,
            "cluster_pass_rate": case.cluster_pass_rate >= case.min_cluster_pass_rate,
            "cost_stress_passed": case.cost_stress_passed,
            "benchmark_relative_passed": case.benchmark_relative_passed,
        }
        passed = all(checks.values())
        probes.append(
            ValidationProbe(
                case.name,
                passed,
                "passed" if passed else "strategy_robustness_failed",
                {
                    "checks": checks,
                    "parameter_stability": case.parameter_stability,
                    "min_parameter_stability": case.min_parameter_stability,
                    "cluster_pass_rate": case.cluster_pass_rate,
                    "min_cluster_pass_rate": case.min_cluster_pass_rate,
                    **dict(case.evidence),
                },
            )
        )
    return StrategyRobustnessReport(tuple(probes))


def evaluate_optimizer_validation(cases: Sequence[OptimizerValidationCase]) -> OptimizerValidationReport:
    probes: list[ValidationProbe] = []
    for case in cases:
        checks = {
            "seeded_reproducible": case.seeded_reproducible,
            "train_test_separated": case.train_test_separated,
            "no_lookahead_detected": case.no_lookahead_detected,
            "persistence_reloaded": case.persistence_reloaded,
            "failed_trials_handled": case.failed_trials_handled,
            "objective_metric_correct": case.objective_metric_correct,
        }
        passed = all(checks.values())
        probes.append(
            ValidationProbe(
                case.name,
                passed,
                "passed" if passed else "optimizer_validation_failed",
                {"checks": checks, **dict(case.evidence)},
            )
        )
    return OptimizerValidationReport(tuple(probes))


def evaluate_portfolio_risk_stress(scenarios: Sequence[PortfolioRiskStressScenario]) -> PortfolioRiskStressReport:
    probes: list[ValidationProbe] = []
    for scenario in scenarios:
        action_ok = scenario.observed_action == scenario.expected_action
        limit_ok = scenario.limit is None or scenario.exposure <= scenario.limit or scenario.expected_action in {"block", "halt", "reduce", "flatten"}
        passed = action_ok and limit_ok
        probes.append(
            ValidationProbe(
                scenario.name,
                passed,
                "passed" if passed else "portfolio_risk_stress_failed",
                {
                    "expected_action": scenario.expected_action,
                    "observed_action": scenario.observed_action,
                    "exposure": scenario.exposure,
                    "limit": scenario.limit,
                    "action_ok": action_ok,
                    "limit_ok": limit_ok,
                    **dict(scenario.evidence),
                },
            )
        )
    return PortfolioRiskStressReport(tuple(probes))


def default_portfolio_risk_stress_scenarios() -> tuple[PortfolioRiskStressScenario, ...]:
    return (
        PortfolioRiskStressScenario("concentration_limit", "block", "block", exposure=0.40, limit=0.25),
        PortfolioRiskStressScenario("cash_reserve", "reduce", "reduce", exposure=0.95, limit=0.80),
        PortfolioRiskStressScenario("correlation_spike", "reduce", "reduce", exposure=0.75, limit=0.70),
        PortfolioRiskStressScenario("gap_through_stop", "halt", "halt", evidence={"loss_multiple": 2.5}),
        PortfolioRiskStressScenario("flatten_kill_switch", "flatten", "flatten"),
    )
