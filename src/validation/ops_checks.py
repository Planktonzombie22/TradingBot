from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.config import RuntimeConfig, validate_runtime_environment

from .broker_checks import ValidationProbe


@dataclass(frozen=True)
class PaperSoakTierSpec:
    name: str
    required_sessions: int
    submit_orders: bool
    requires_alpaca: bool = False
    requires_recovery: bool = False
    requires_portfolio: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "required_sessions": self.required_sessions,
            "submit_orders": self.submit_orders,
            "requires_alpaca": self.requires_alpaca,
            "requires_recovery": self.requires_recovery,
            "requires_portfolio": self.requires_portfolio,
            "description": self.description,
        }


@dataclass(frozen=True)
class PaperSoakTierReport:
    probes: tuple[ValidationProbe, ...]
    tiers: tuple[PaperSoakTierSpec, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "tiers": [tier.to_dict() for tier in self.tiers],
            "probes": [probe.to_dict() for probe in self.probes],
        }


@dataclass(frozen=True)
class DailyOpsAcceptanceReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "probes": [probe.to_dict() for probe in self.probes]}


@dataclass(frozen=True)
class ObservabilityAcceptanceReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "probes": [probe.to_dict() for probe in self.probes]}


@dataclass(frozen=True)
class SecurityConfigReport:
    probes: tuple[ValidationProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "probes": [probe.to_dict() for probe in self.probes]}


def default_paper_soak_tiers() -> tuple[PaperSoakTierSpec, ...]:
    return (
        PaperSoakTierSpec("local_sample_soak", 3, False, description="Local sample-provider dry-run soak."),
        PaperSoakTierSpec("alpaca_data_only_dry_run", 3, False, requires_alpaca=True, description="Alpaca data path without order submission."),
        PaperSoakTierSpec("alpaca_micro_notional_submit", 3, True, requires_alpaca=True, description="Tiny paper submissions with strict risk budgets."),
        PaperSoakTierSpec("portfolio_paper_soak", 3, False, requires_portfolio=True, description="Portfolio candidate allocation and consolidated order proof."),
        PaperSoakTierSpec("restart_recovery_soak", 2, False, requires_recovery=True, description="Restart-aware persisted-state recovery proof."),
        PaperSoakTierSpec("full_paper_rehearsal", 5, True, requires_alpaca=True, requires_recovery=True, requires_portfolio=True, description="Guarded full paper rehearsal after lower tiers pass."),
    )


def evaluate_paper_soak_tiers(
    evidence_by_tier: Mapping[str, Mapping[str, Any]],
    tiers: Sequence[PaperSoakTierSpec] | None = None,
) -> PaperSoakTierReport:
    tiers = tuple(tiers or default_paper_soak_tiers())
    probes = []
    for tier in tiers:
        evidence = dict(evidence_by_tier.get(tier.name, {}))
        completed = int(evidence.get("completed_sessions", 0) or 0)
        passed = bool(evidence.get("passed", False))
        submitted = bool(evidence.get("submitted", False))
        alpaca = bool(evidence.get("alpaca", False))
        recovery = bool(evidence.get("recovery", False))
        portfolio = bool(evidence.get("portfolio", False))
        checks = {
            "passed": passed,
            "minimum_sessions": completed >= tier.required_sessions,
            "submission_mode": (not tier.submit_orders) or submitted,
            "alpaca_requirement": (not tier.requires_alpaca) or alpaca,
            "recovery_requirement": (not tier.requires_recovery) or recovery,
            "portfolio_requirement": (not tier.requires_portfolio) or portfolio,
        }
        tier_passed = all(checks.values())
        probes.append(
            ValidationProbe(
                tier.name,
                tier_passed,
                "passed" if tier_passed else "paper_soak_tier_incomplete",
                {"checks": checks, "required": tier.to_dict(), "evidence": evidence},
            )
        )
    return PaperSoakTierReport(tuple(probes), tiers)


def evaluate_daily_ops_acceptance(report_payload: Mapping[str, Any]) -> DailyOpsAcceptanceReport:
    summary = dict(report_payload.get("summary", {}))
    warnings = list(report_payload.get("warnings", []))
    recommendations = list(report_payload.get("recommendations", []))
    reconciliation = dict(report_payload.get("reconciliation", {}))
    fills = dict(report_payload.get("fills", {}))
    scorecards = dict(report_payload.get("scorecards", {}))
    promotion = dict(report_payload.get("promotion_queue") or {})
    probes = (
        ValidationProbe("summary_present", bool(summary), "passed" if summary else "missing_summary", {"summary": summary}),
        ValidationProbe("recommendations_present", bool(recommendations), "passed" if recommendations else "missing_recommendations", {"recommendations": recommendations}),
        ValidationProbe(
            "unresolved_order_summary_present",
            "unresolved_sessions" in reconciliation,
            "passed" if "unresolved_sessions" in reconciliation else "missing_reconciliation_summary",
            {"reconciliation": reconciliation},
        ),
        ValidationProbe(
            "missed_fill_summary_present",
            "missed_or_unsubmitted_sessions" in fills,
            "passed" if "missed_or_unsubmitted_sessions" in fills else "missing_fill_summary",
            {"fills": fills},
        ),
        ValidationProbe(
            "scorecard_summary_present",
            "failed" in scorecards and "passed" in scorecards,
            "passed" if "failed" in scorecards and "passed" in scorecards else "missing_scorecard_summary",
            {"scorecards": scorecards},
        ),
        ValidationProbe(
            "promotion_queue_summary_present",
            bool(promotion) or summary.get("promotion_enabled", 0) == 0,
            "passed" if bool(promotion) or summary.get("promotion_enabled", 0) == 0 else "missing_promotion_queue_summary",
            {"promotion_queue": promotion, "summary": summary},
        ),
        ValidationProbe("warnings_serialized", isinstance(warnings, list), "passed" if isinstance(warnings, list) else "warnings_not_serialized", {"warnings": warnings}),
    )
    return DailyOpsAcceptanceReport(probes)


def evaluate_observability_acceptance(
    metrics_snapshot: Mapping[str, Any],
    health_statuses: Sequence[Mapping[str, Any]],
    notification_events: Sequence[Mapping[str, Any]],
    dashboard_snapshot: Mapping[str, Any],
    required_metrics: Sequence[str] = ("orders", "equity"),
    required_topics: Sequence[str] = ("startup", "halt"),
) -> ObservabilityAcceptanceReport:
    counters = dict(metrics_snapshot.get("counters", {}))
    gauges = dict(metrics_snapshot.get("gauges", {}))
    timings = dict(metrics_snapshot.get("timings", {}))
    metric_names = set(counters) | set(gauges) | set(timings)
    health = list(health_statuses)
    topics = {event.get("topic") for event in notification_events}
    severities = {event.get("severity") for event in notification_events}
    probes = (
        ValidationProbe("required_metrics_present", set(required_metrics) <= metric_names, "passed" if set(required_metrics) <= metric_names else "missing_required_metrics", {"required": list(required_metrics), "available": sorted(metric_names)}),
        ValidationProbe("health_checks_present", bool(health) and all("healthy" in item for item in health), "passed" if bool(health) and all("healthy" in item for item in health) else "missing_health_checks", {"health": health}),
        ValidationProbe("notification_topics_present", set(required_topics) <= topics, "passed" if set(required_topics) <= topics else "missing_notification_topics", {"required": list(required_topics), "topics": sorted(item for item in topics if item)}),
        ValidationProbe("critical_severity_routed", "CRITICAL" in severities, "passed" if "CRITICAL" in severities else "missing_critical_notification", {"severities": sorted(item for item in severities if item)}),
        ValidationProbe("dashboard_account_present", "account" in dashboard_snapshot and "risk_halt" in dashboard_snapshot, "passed" if "account" in dashboard_snapshot and "risk_halt" in dashboard_snapshot else "dashboard_missing_account_or_risk", {"dashboard_keys": sorted(dashboard_snapshot)}),
        ValidationProbe("halt_reason_visible", bool(dict(dashboard_snapshot.get("risk_halt", {})).get("reason")) or dict(dashboard_snapshot.get("risk_halt", {})).get("halted") is False, "passed" if bool(dict(dashboard_snapshot.get("risk_halt", {})).get("reason")) or dict(dashboard_snapshot.get("risk_halt", {})).get("halted") is False else "missing_halt_reason", {"risk_halt": dict(dashboard_snapshot.get("risk_halt", {}))}),
    )
    return ObservabilityAcceptanceReport(probes)


def evaluate_security_config(
    config: RuntimeConfig,
    env_payload: Mapping[str, str] | None = None,
    committed_text: str = "",
) -> SecurityConfigReport:
    validation = validate_runtime_environment(config)
    env_payload = dict(env_payload or {})
    secret_markers = ("ALPACA_API_KEY=", "ALPACA_SECRET_KEY=", "api_key=", "secret_key=")
    leaked_markers = [marker for marker in secret_markers if marker in committed_text and "example" not in committed_text.lower()]
    probes = (
        ValidationProbe("runtime_environment_valid", validation.passed, "passed" if validation.passed else "runtime_environment_invalid", {"errors": validation.errors, "warnings": validation.warnings}),
        ValidationProbe("paper_trading_flag_safe", config.paper_trading or config.execution.mode != "paper", "passed" if config.paper_trading or config.execution.mode != "paper" else "paper_trading_disabled_for_paper_mode", {"paper_trading": config.paper_trading, "execution_mode": config.execution.mode}),
        ValidationProbe("alpaca_paper_url_safe", config.execution.mode != "paper" or "paper-api.alpaca.markets" in config.alpaca.base_url.lower() or config.execution.allow_live_trading, "passed" if config.execution.mode != "paper" or "paper-api.alpaca.markets" in config.alpaca.base_url.lower() or config.execution.allow_live_trading else "paper_mode_non_paper_url", {"base_url": config.alpaca.base_url, "execution_mode": config.execution.mode}),
        ValidationProbe("allow_live_trading_guarded", not config.execution.allow_live_trading, "passed" if not config.execution.allow_live_trading else "allow_live_trading_enabled", {"allow_live_trading": config.execution.allow_live_trading}),
        ValidationProbe("env_values_present_when_required", _required_env_present(config, env_payload), "passed" if _required_env_present(config, env_payload) else "missing_required_env_values", {"required": _required_env_keys(config), "present": sorted(key for key, value in env_payload.items() if value)}),
        ValidationProbe("no_committed_secret_markers", not leaked_markers, "passed" if not leaked_markers else "possible_committed_secret", {"markers": leaked_markers}),
    )
    return SecurityConfigReport(probes)


def _required_env_keys(config: RuntimeConfig) -> tuple[str, ...]:
    if config.data.provider.lower() == "alpaca" or config.execution.mode.lower() == "paper":
        return ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    return ()


def _required_env_present(config: RuntimeConfig, env_payload: Mapping[str, str]) -> bool:
    required = _required_env_keys(config)
    return all(bool(env_payload.get(key)) for key in required)
