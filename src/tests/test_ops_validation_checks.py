from src.config import AlpacaConfig, ExecutionConfig, MarketDataConfig, RuntimeConfig
from src.validation import (
    evaluate_daily_ops_acceptance,
    evaluate_observability_acceptance,
    evaluate_paper_soak_tiers,
    evaluate_security_config,
)


def test_paper_soak_tiers_require_sessions_and_tier_specific_evidence():
    evidence = {
        "local_sample_soak": {"passed": True, "completed_sessions": 3},
        "alpaca_data_only_dry_run": {"passed": True, "completed_sessions": 3, "alpaca": True},
        "alpaca_micro_notional_submit": {"passed": True, "completed_sessions": 3, "alpaca": True, "submitted": True},
        "portfolio_paper_soak": {"passed": True, "completed_sessions": 3, "portfolio": True},
        "restart_recovery_soak": {"passed": True, "completed_sessions": 2, "recovery": True},
        "full_paper_rehearsal": {
            "passed": True,
            "completed_sessions": 5,
            "alpaca": True,
            "submitted": True,
            "recovery": True,
            "portfolio": True,
        },
    }

    clean = evaluate_paper_soak_tiers(evidence)
    dirty = evaluate_paper_soak_tiers(
        {"alpaca_micro_notional_submit": {"passed": True, "completed_sessions": 1, "alpaca": True}}
    )

    assert clean.passed
    assert not dirty.passed
    probes = {probe.name: probe for probe in dirty.probes}
    assert probes["alpaca_micro_notional_submit"].reason == "paper_soak_tier_incomplete"
    assert not probes["alpaca_micro_notional_submit"].evidence["checks"]["minimum_sessions"]
    assert not probes["alpaca_micro_notional_submit"].evidence["checks"]["submission_mode"]


def test_daily_ops_acceptance_validates_operator_report_sections():
    payload = {
        "summary": {"promotion_enabled": 0},
        "recommendations": ["Continue dry-run evidence collection."],
        "reconciliation": {"unresolved_sessions": 0},
        "fills": {"missed_or_unsubmitted_sessions": 0},
        "scorecards": {"passed": 2, "failed": 0},
        "warnings": [],
    }

    clean = evaluate_daily_ops_acceptance(payload)
    dirty = evaluate_daily_ops_acceptance(
        {"summary": {"promotion_enabled": 1}, "recommendations": [], "warnings": []}
    )

    assert clean.passed
    assert not dirty.passed
    reasons = {probe.name: probe.reason for probe in dirty.probes if not probe.passed}
    assert reasons["recommendations_present"] == "missing_recommendations"
    assert reasons["unresolved_order_summary_present"] == "missing_reconciliation_summary"
    assert reasons["missed_fill_summary_present"] == "missing_fill_summary"
    assert reasons["scorecard_summary_present"] == "missing_scorecard_summary"
    assert reasons["promotion_queue_summary_present"] == "missing_promotion_queue_summary"


def test_observability_acceptance_requires_metrics_health_notifications_and_halt_reason():
    metrics = {"counters": {"orders": 1}, "gauges": {"equity": 10_000}, "timings": {}}
    health = [{"name": "stream", "healthy": True}]
    events = [{"topic": "startup", "severity": "INFO"}, {"topic": "halt", "severity": "CRITICAL"}]
    dashboard = {"account": {"equity": 10_000}, "risk_halt": {"halted": True, "reason": "daily loss"}}

    clean = evaluate_observability_acceptance(metrics, health, events, dashboard)
    dirty = evaluate_observability_acceptance(
        {"counters": {}, "gauges": {"equity": 10_000}},
        [{"name": "stream"}],
        [{"topic": "startup", "severity": "INFO"}],
        {"account": {"equity": 10_000}, "risk_halt": {"halted": True}},
    )

    assert clean.passed
    assert not dirty.passed
    reasons = {probe.name: probe.reason for probe in dirty.probes if not probe.passed}
    assert reasons["required_metrics_present"] == "missing_required_metrics"
    assert reasons["health_checks_present"] == "missing_health_checks"
    assert reasons["notification_topics_present"] == "missing_notification_topics"
    assert reasons["critical_severity_routed"] == "missing_critical_notification"
    assert reasons["halt_reason_visible"] == "missing_halt_reason"


def test_security_config_report_blocks_unsafe_paper_and_secret_combinations():
    safe = RuntimeConfig(
        data=MarketDataConfig(provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper"),
        paper_trading=True,
    )
    unsafe = RuntimeConfig(
        data=MarketDataConfig(provider="alpaca"),
        alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://api.alpaca.markets"),
        execution=ExecutionConfig(mode="paper", allow_live_trading=True),
        paper_trading=False,
    )

    clean = evaluate_security_config(
        safe,
        {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"},
        committed_text="ALPACA_API_KEY=example",
    )
    dirty = evaluate_security_config(unsafe, {}, committed_text="ALPACA_SECRET_KEY=supersecret")

    assert clean.passed
    assert not dirty.passed
    reasons = {probe.name: probe.reason for probe in dirty.probes if not probe.passed}
    assert reasons["runtime_environment_valid"] == "runtime_environment_invalid"
    assert reasons["paper_trading_flag_safe"] == "paper_trading_disabled_for_paper_mode"
    assert reasons["allow_live_trading_guarded"] == "allow_live_trading_enabled"
    assert reasons["env_values_present_when_required"] == "missing_required_env_values"
    assert reasons["no_committed_secret_markers"] == "possible_committed_secret"
