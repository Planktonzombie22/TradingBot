import argparse
import os
import sys
import threading
import json
import _thread
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from src.app import TradingApplication
from src.backtesting import (
    BacktestConfig,
    StrategySelectionPolicy,
    benchmark_relative_report,
    build_benchmark_promotion_report,
    grid_search,
    load_research_matrix,
    load_replication_suite,
    run_bulk_backtests,
    run_research_matrix,
    run_replication_suite,
    write_replication_report,
)
from src.config import load_runtime_config
from src.deployment import docker_profile, local_windows_task_profile, small_server_profile
from src.engine import EngineEvent
from src.engine import EngineState
from src.engine import TradingEngine
from src.operations import (
    AutonomousPaperSessionOptions,
    PaperBrokerOrderPlan,
    PaperBrokerProofApprovalPolicy,
    PaperBrokerProofOptions,
    PaperCleanupOptions,
    PaperSessionSoakConfig,
    PaperTradingDaemonOptions,
    PortfolioPaperSessionOptions,
    ScheduledPaperSessionRecord,
    alpaca_paper_soak_profiles,
    build_asset_class_metadata_report,
    build_data_freshness_report,
    build_live_market_snapshot_report,
    build_paper_command_center_report,
    build_paper_daemon_activation_checklist_report,
    build_paper_controlled_flatten_plan,
    build_paper_daemon_daily_summary_report,
    build_paper_daemon_flatten_drill_report,
    build_paper_daemon_notification_report,
    build_paper_daemon_notional_decision_report,
    build_paper_daemon_recovery_report,
    build_paper_daemon_retention_plan,
    build_paper_daemon_restart_drill_report,
    build_paper_daemon_soak_readiness_rollup_report,
    build_paper_daemon_supervised_soak_report,
    build_paper_daemon_window_capture_plan_report,
    build_paper_exposure_acknowledgement_template_report,
    build_paper_drawdown_report,
    build_paper_eod_closeout_report,
    build_paper_exit_preview,
    build_paper_monitor_report,
    build_paper_pnl_attribution_report,
    build_paper_pilot_report,
    build_paper_position_stewardship_report,
    build_quote_spread_report,
    build_symbol_capability_report,
    clear_paper_daemon_stop,
    evaluate_paper_session_schedule,
    fetch_alpaca_asset_metadata,
    fetch_alpaca_live_market_snapshots,
    load_paper_daemon_state,
    load_paper_session_manifests,
    paper_open_order_snapshot_from_broker,
    request_paper_daemon_stop,
    run_autonomous_paper_session,
    run_paper_broker_proof,
    run_paper_cleanup,
    run_paper_stale_order_cancel,
    run_paper_session_soak,
    run_paper_trading_daemon,
    run_portfolio_paper_session,
    run_scheduled_paper_broker_proof,
    run_scheduled_paper_broker_proof_from_artifact,
    run_scheduled_paper_session,
    validate_alpaca_paper_soak_profile,
    write_paper_controlled_flatten_plan,
    write_asset_class_metadata_report,
    write_data_freshness_report,
    write_paper_command_center_report,
    write_paper_daemon_ops_report,
    write_paper_drawdown_report,
    write_paper_eod_closeout_report,
    write_paper_exit_preview_report,
    write_paper_monitor_report,
    write_paper_open_order_report,
    write_paper_pnl_attribution_report,
    write_paper_session_soak_report,
    write_paper_stale_order_cancel_report,
    write_live_market_snapshot_report,
    write_quote_spread_report,
    write_symbol_capability_report,
    write_paper_pilot_report,
)
from src.execution import BrokerReconciler, ExecutionReport
from src.models import Order
from src.reporting import (
    format_backtest_summary,
    build_paper_activation_report,
    plot_backtest,
    write_backtest_html_report,
    write_backtest_report,
    write_paper_activation_report,
    write_readiness_html_page,
)
from src.storage import JsonlStore
from src.utils.logger import configure_logging
from src.utils.profiling import BenchmarkTask, run_benchmark_suite
from src.validation import (
    BacktestDifferentialScenario,
    FailureInjectionScenario,
    GoldenArtifactCase,
    OptimizerValidationCase,
    build_autonomous_paper_trading_rehearsal_report,
    build_not_live_ready_report,
    build_release_decision_report,
    build_readiness_index,
    build_validation_run_metadata,
    build_validation_action_plan,
    default_cli_smoke_specs,
    default_performance_budgets,
    default_release_checklist,
    default_validation_manifest,
    default_validation_profiles,
    evaluate_backtest_differential,
    evaluate_calendar_torture,
    evaluate_data_quality_torture,
    evaluate_deployment_rehearsal,
    evaluate_evidence_freshness,
    evaluate_failure_injection,
    evaluate_golden_artifacts,
    evaluate_hard_pre_live_upgrade_gates,
    evaluate_daily_ops_acceptance,
    evaluate_observability_acceptance,
    evaluate_optimizer_validation,
    evaluate_paper_profile_validation,
    evaluate_paper_soak_tiers,
    evaluate_performance_budgets,
    evaluate_security_config,
    execute_validation_profile,
    load_validation_evidence_bundle,
    ValidationEvidence,
    ValidationEvidenceBundle,
    write_validation_evidence_bundle,
)


TIMEOUT_EXIT_CODE = 124


@dataclass(frozen=True)
class RuntimeTimeoutPolicy:
    seconds: float
    grace_seconds: float = 5.0


class RuntimeWatchdog:
    def __init__(
        self,
        policy: RuntimeTimeoutPolicy,
        interrupt_main=_thread.interrupt_main,
        hard_exit=os._exit,
    ):
        if policy.seconds <= 0:
            raise ValueError("Runtime timeout must be positive.")
        if policy.grace_seconds <= 0:
            raise ValueError("Runtime timeout grace period must be positive.")
        self.policy = policy
        self.interrupt_main = interrupt_main
        self.hard_exit = hard_exit
        self.triggered = False
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "RuntimeWatchdog":
        self._thread = threading.Thread(target=self._run, name="runtime-watchdog", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cancel()

    def cancel(self) -> None:
        self._stopped.set()

    def _run(self) -> None:
        if self._stopped.wait(self.policy.seconds):
            return
        self.triggered = True
        print(
            f"Runtime timeout reached after {self.policy.seconds:.0f}s; requesting shutdown.",
            file=sys.stderr,
            flush=True,
        )
        self.interrupt_main()
        if self._stopped.wait(self.policy.grace_seconds):
            return
        print(
            f"Runtime did not stop within {self.policy.grace_seconds:.0f}s; forcing exit.",
            file=sys.stderr,
            flush=True,
        )
        self.hard_exit(TIMEOUT_EXIT_CODE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradingBot MVP runner")
    paper_profile_choices = sorted(alpaca_paper_soak_profiles())
    parser.add_argument(
        "mode",
        nargs="?",
        choices=[
            "backtest",
            "stream",
            "paper",
            "paper-session",
            "paper-session-schedule",
            "paper-broker-proof",
            "paper-broker-schedule",
            "paper-cleanup",
            "paper-monitor",
            "paper-pilot",
            "paper-daemon",
            "paper-daemon-stop",
            "paper-daemon-clear-stop",
            "paper-daemon-status",
            "paper-daemon-ops",
            "paper-command-center",
            "paper-activation-report",
            "paper-soak",
            "paper-portfolio",
            "report",
            "optimize",
            "bulk",
            "matrix",
            "replicate",
            "validate",
            "validate-profile",
            "profile",
            "release-checklist",
            "release-rehearsal",
        ],
        default="backtest",
    )
    parser.add_argument("--provider", default="sample", choices=["sample", "yfinance", "alpaca"])
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--symbols", help="Comma-separated symbol list for bulk mode.")
    parser.add_argument("--symbols-file", help="JSON or text watchlist file for bulk mode.")
    parser.add_argument("--max-symbols", type=int, default=100, help="Maximum symbols to run in bulk mode.")
    parser.add_argument("--strategy", default="buyHold")
    parser.add_argument("--strategies", help="Comma-separated strategy list for bulk mode. Defaults to --strategy.")
    parser.add_argument("--strategy-params", default="{}", help="JSON object of strategy constructor parameters.")
    parser.add_argument("--strategy-params-file", help="Path to a JSON strategy parameter file.")
    parser.add_argument("--strategy-param-dir", default="configs/strategies", help="Directory for bulk strategy parameter JSON files.")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--start", help="Optional historical start timestamp/date, for example 2024-01-01T00:00:00Z.")
    parser.add_argument("--end", help="Optional historical end timestamp/date, for example 2024-12-31T00:00:00Z.")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--output", help="Optional path for a JSON backtest report.")
    parser.add_argument("--html-output", default="reports/backtest.html", help="Path for an HTML report in report mode.")
    parser.add_argument("--store-dir", default="runs", help="Directory for JSONL run artifacts.")
    parser.add_argument("--execution-mode", choices=["dry-run", "paper"], help="Broker execution mode. Defaults to EXECUTION_MODE or dry-run.")
    parser.add_argument("--flatten-on-stop", action="store_true", help="Submit flattening orders before stopping a stream/paper run.")
    parser.add_argument("--submit-orders", action="store_true", help="Submit generated paper-session orders after the guarded dry-run plan passes.")
    parser.add_argument("--paper-proof-output", default="reports/alpaca-paper-broker-proof.json", help="Path for the broker-facing paper proof artifact.")
    parser.add_argument("--paper-proof-existing-artifact", help="Existing broker proof artifact to score in paper-broker-schedule without submitting another order.")
    parser.add_argument("--paper-session-schedule-output", default="reports/paper-session-schedule.json", help="Path for the scheduled autonomous paper-session report artifact.")
    parser.add_argument("--paper-proof-schedule-output", default="reports/alpaca-paper-broker-proof-schedule.json", help="Path for the scheduled broker-proof report artifact.")
    parser.add_argument("--paper-proof-artifact-root", default="runs/paper-broker-proof", help="Directory for scheduled broker-proof child artifacts.")
    parser.add_argument("--paper-submit-evidence", default="reports/evidence/paper-submit-activation-check.json", help="Path to paper-submit validation-profile evidence used by paper-activation-report.")
    parser.add_argument("--paper-activation-output", default="reports/paper-activation-report.json", help="Path for the paper activation operator report.")
    parser.add_argument("--paper-cleanup-output", default="reports/paper-cleanup-report.json", help="Path for the paper account cleanup/flatten artifact.")
    parser.add_argument("--paper-cleanup-symbols", help="Optional comma-separated symbols to flatten in paper-cleanup mode. Defaults to every broker position.")
    parser.add_argument("--paper-monitor-output", default="reports/paper-monitor-report.json", help="Path for the paper position monitor report.")
    parser.add_argument("--paper-monitor-portfolio-input", default="runs/paper-pilot-promoted-submit/portfolio-session-report.json", help="Portfolio paper-session artifact whose submitted orders define expected positions.")
    parser.add_argument("--paper-monitor-position-input", help="Optional existing paper-cleanup/position-preview artifact. Defaults to a fresh no-submit broker position preview.")
    parser.add_argument("--paper-monitor-cleanup-input", help="Optional filled paper-cleanup artifact used to mark expected paper positions as closed.")
    parser.add_argument("--paper-monitor-max-notional", type=float, help="Optional max observed paper-position notional for paper-monitor.")
    parser.add_argument("--paper-position-journal", help="Optional JSONL path for appending paper position lifecycle observations from paper-monitor.")
    parser.add_argument("--paper-open-orders-input", help="Optional existing open-order artifact for paper-monitor stale-order scoring.")
    parser.add_argument("--paper-open-orders-output", help="Optional JSON artifact path for broker open-order scoring from paper-monitor.")
    parser.add_argument("--paper-open-order-timeout-minutes", type=float, default=15.0, help="Maximum age before unresolved paper orders are marked stale.")
    parser.add_argument("--paper-stale-order-cancel-output", help="Optional JSON artifact path for stale open-order cancel planning/acknowledgement.")
    parser.add_argument("--paper-cancel-stale-orders", action="store_true", help="Explicitly cancel stale paper open orders found by paper-monitor.")
    parser.add_argument("--paper-exit-preview-output", help="Optional JSON artifact path for paper-monitor flatten/exit preview orders.")
    parser.add_argument("--paper-exit-preview-active", action="store_true", help="Include active expected pilot positions in the paper exit preview.")
    parser.add_argument("--paper-controlled-flatten-output", help="Optional JSON artifact path for controlled active-pilot flatten planning.")
    parser.add_argument("--paper-controlled-flatten-symbols", help="Optional comma-separated active pilot symbols for controlled flatten planning. Defaults to all active pilot positions.")
    parser.add_argument("--paper-controlled-flatten-reason", default="operator_requested_controlled_flatten", help="Strategy-aware reason recorded on controlled flatten plans.")
    parser.add_argument("--paper-eod-closeout-output", help="Optional JSON artifact path for end-of-day flatten/reduce/hold closeout planning.")
    parser.add_argument("--paper-eod-overnight-policy", choices=["hold", "flatten", "reduce"], default="hold", help="Default overnight policy for paper EOD closeout planning.")
    parser.add_argument("--paper-eod-reduce-fraction", type=float, default=0.5, help="Fraction of current quantity to keep when EOD policy is reduce.")
    parser.add_argument("--paper-pnl-attribution-output", help="Optional JSON artifact path for paper PnL attribution by strategy/symbol/session.")
    parser.add_argument("--paper-drawdown-output", help="Optional JSON artifact path for broker equity and mark-to-market drawdown tracking.")
    parser.add_argument("--paper-drawdown-peak-equity", type=float, help="Optional prior peak equity used to calculate paper drawdown.")
    parser.add_argument("--paper-market-snapshot-output", help="Optional JSON artifact path for Alpaca latest-trade/latest-quote snapshots in paper-monitor.")
    parser.add_argument("--paper-data-freshness-output", help="Optional JSON artifact path for quote/trade freshness scoring in paper-monitor.")
    parser.add_argument("--paper-quote-spread-output", help="Optional JSON artifact path for quote spread and fill-quality analysis in paper-monitor.")
    parser.add_argument("--paper-asset-metadata-output", help="Optional JSON artifact path for asset-class/tradability metadata in paper-monitor.")
    parser.add_argument("--paper-symbol-capability-output", help="Optional JSON artifact path for fractional/short/margin capability gates in paper-monitor.")
    parser.add_argument("--paper-require-fractional", action="store_true", help="Require fractional trading support in paper symbol capability gates.")
    parser.add_argument("--paper-require-short", action="store_true", help="Require shortability/easy-to-borrow support in paper symbol capability gates.")
    parser.add_argument("--paper-require-margin", action="store_true", help="Require marginability support in paper symbol capability gates.")
    parser.add_argument("--paper-pilot-output", default="reports/paper-pilot-report.json", help="Path for the one-command paper pilot readiness report.")
    parser.add_argument("--paper-pilot-validation-output", default="reports/evidence/paper-pilot-paper-submit-validation.json", help="Path for paper-submit evidence generated by paper-pilot.")
    parser.add_argument("--paper-pilot-skip-portfolio", action="store_true", help="Skip promoted portfolio preview inside paper-pilot mode.")
    parser.add_argument("--paper-pilot-submit-portfolio", action="store_true", help="Allow paper-pilot to submit the promoted portfolio after cleanup and broker evidence are already clear.")
    parser.add_argument("--paper-daemon-interval-seconds", type=float, default=300.0, help="Seconds between always-on paper daemon schedule checks.")
    parser.add_argument("--paper-daemon-max-iterations", type=int, help="Optional maximum daemon iterations for smoke tests or bounded runs.")
    parser.add_argument("--paper-daemon-kill-switch", default="runs/paper-daemon.kill", help="Path whose presence stops or prevents paper-daemon trading.")
    parser.add_argument("--paper-daemon-state-output", default="runs/paper-daemon-state.json", help="Path for paper-daemon state JSON.")
    parser.add_argument("--paper-daemon-heartbeat-output", default="runs/paper-daemon-heartbeat.json", help="Path for paper-daemon heartbeat JSON.")
    parser.add_argument("--paper-daemon-lock-path", default="runs/paper-daemon.lock", help="Single-instance lock path for paper-daemon runs.")
    parser.add_argument("--paper-daemon-lock-stale-seconds", type=float, default=1800.0, help="Age after which an abandoned paper-daemon lock may be replaced.")
    parser.add_argument("--paper-daemon-artifact-root", default="runs/paper-daemon", help="Directory for paper-daemon child artifacts.")
    parser.add_argument("--paper-daemon-schedule-output", default="reports/paper-daemon-schedule.json", help="Base path for per-iteration paper-daemon schedule reports.")
    parser.add_argument("--paper-daemon-report-output", default="reports/paper-daemon-report.json", help="Path for the full paper-daemon run report JSON.")
    parser.add_argument("--paper-daemon-cleanup-each-iteration", action="store_true", help="Run a preview cleanup/flatten review after every daemon schedule check.")
    parser.add_argument("--paper-daemon-cleanup-submit", action="store_true", help="Allow daemon cleanup reviews to submit flattening orders after the existing guards pass.")
    parser.add_argument("--paper-daemon-cleanup-output", default="reports/paper-daemon-cleanup.json", help="Base path for per-iteration daemon cleanup artifacts.")
    parser.add_argument("--paper-daemon-monitor-each-iteration", action="store_true", help="Build expected-vs-observed paper monitor evidence after every daemon schedule check.")
    parser.add_argument("--paper-daemon-monitor-output", default="reports/paper-daemon-monitor.json", help="Base path for per-iteration daemon monitor artifacts.")
    parser.add_argument("--paper-daemon-monitor-open-order-timeout-minutes", type=float, default=15.0, help="Maximum unresolved paper-order age before daemon monitor evidence marks it stale.")
    parser.add_argument("--paper-daemon-data-parity-each-iteration", action="store_true", help="Attach websocket-vs-REST data parity evidence to every daemon schedule check.")
    parser.add_argument("--paper-daemon-data-parity-output", default="reports/paper-daemon-data-parity.json", help="Base path for per-iteration daemon websocket-vs-REST parity artifacts.")
    parser.add_argument("--paper-daemon-data-parity-max-close-drift-bps", type=float, default=5.0, help="Maximum close-price drift between streamed and REST bars before daemon data parity fails.")
    parser.add_argument("--paper-daemon-stop-reason", default="operator_requested_stop", help="Reason recorded when paper-daemon-stop writes the kill switch.")
    parser.add_argument("--paper-daemon-ops-type", choices=["recovery", "daily-summary", "notifications", "retention", "notional", "restart-drill", "activation-checklist", "exposure-ack-template", "supervised-soak", "position-stewardship", "flatten-drill", "soak-rollup", "window-capture-plan"], default="recovery", help="Operator report type emitted by paper-daemon-ops mode.")
    parser.add_argument("--paper-daemon-ops-output", default="reports/paper-daemon-ops.json", help="Path for paper-daemon-ops JSON output.")
    parser.add_argument("--paper-daemon-report-input", help="Optional full daemon report JSON used by the daily-summary report. Defaults to --paper-daemon-report-output when present, then daemon state only.")
    parser.add_argument("--paper-daemon-daily-summary-input", help="Optional daily-summary JSON used by activation-checklist mode.")
    parser.add_argument("--paper-command-center-input", help="Optional paper-command-center JSON used by activation-checklist mode.")
    parser.add_argument("--paper-daemon-kill-proof-input", help="Optional kill-switch proof daemon report JSON used by activation-checklist mode.")
    parser.add_argument("--paper-daemon-cleanup-input", help="Optional latest paper-cleanup JSON used by activation-checklist mode. Defaults to --paper-cleanup-output when that file exists.")
    parser.add_argument("--paper-daemon-acknowledged-exposure-input", help="Optional bounded paper-exposure acknowledgement JSON used by activation-checklist mode.")
    parser.add_argument("--paper-daemon-ack-template-buffer-pct", type=float, default=20.0, help="Notional buffer percentage used by exposure-ack-template mode.")
    parser.add_argument("--paper-daemon-ack-template-expires-at", help="Optional expiry timestamp written into exposure-ack-template output.")
    parser.add_argument("--paper-daemon-activation-allow-no-submit", action="store_true", help="Allow activation-checklist to pass without an active-window submitted daemon iteration.")
    parser.add_argument("--paper-daemon-activation-inputs", help="Comma-separated activation-checklist JSON artifacts used by supervised-soak mode.")
    parser.add_argument("--paper-daemon-soak-required-clean-activations", type=int, default=3, help="Clean activation-checklist artifacts required by supervised-soak mode.")
    parser.add_argument("--paper-daemon-soak-required-active-windows", type=int, default=2, help="Distinct active windows required by supervised-soak mode.")
    parser.add_argument("--paper-daemon-soak-max-observed-notional", type=float, help="Optional total observed-notional cap across supervised-soak activation artifacts.")
    parser.add_argument("--paper-daemon-position-monitor-input", help="Paper monitor JSON consumed by position-stewardship mode. Defaults to --paper-monitor-output when that file exists.")
    parser.add_argument("--paper-daemon-position-cleanup-input", help="Optional cleanup JSON consumed by position-stewardship mode for closure evidence.")
    parser.add_argument("--paper-daemon-position-max-age-hours", type=float, default=72.0, help="Maximum active paper-position age before position-stewardship requires closure evidence.")
    parser.add_argument("--paper-daemon-flatten-pre-monitor-input", help="Pre-flatten paper monitor artifact consumed by flatten-drill mode.")
    parser.add_argument("--paper-daemon-flatten-plan-input", help="Controlled flatten plan artifact consumed by flatten-drill mode.")
    parser.add_argument("--paper-daemon-flatten-cleanup-input", help="Submitted cleanup artifact consumed by flatten-drill mode.")
    parser.add_argument("--paper-daemon-flatten-post-monitor-input", help="Post-flatten paper monitor artifact consumed by flatten-drill mode.")
    parser.add_argument("--paper-daemon-flatten-stewardship-input", help="Optional position-stewardship artifact consumed by flatten-drill mode.")
    parser.add_argument("--paper-daemon-activation-checklist-input", help="Activation-checklist artifact consumed by soak-rollup mode.")
    parser.add_argument("--paper-daemon-supervised-soak-input", help="Supervised-soak artifact consumed by soak-rollup mode.")
    parser.add_argument("--paper-daemon-stewardship-input", help="Position-stewardship artifact consumed by soak-rollup mode.")
    parser.add_argument("--paper-daemon-flatten-drill-input", help="Flatten-drill artifact consumed by soak-rollup mode.")
    parser.add_argument("--paper-daemon-data-parity-input", help="Data-parity artifact consumed by soak-rollup mode.")
    parser.add_argument("--paper-daemon-notional-input", help="Notional decision artifact consumed by soak-rollup mode.")
    parser.add_argument("--paper-daemon-window-capture-windows", default="market_open,intraday,market_close", help="Comma-separated submit-capable windows targeted by window-capture-plan mode.")
    parser.add_argument("--paper-daemon-window-capture-max-iterations", type=int, default=1, help="Bounded daemon iterations suggested by window-capture-plan commands.")
    parser.add_argument("--paper-daemon-restart-drills-input", help="Optional JSON evidence file for paper-daemon-ops restart-drill mode.")
    parser.add_argument("--paper-daemon-retention-paths", help="Comma-separated daemon artifact paths to score in retention mode.")
    parser.add_argument("--paper-daemon-retention-keep-days", type=int, default=30, help="Retention-plan age threshold for daemon artifacts.")
    parser.add_argument("--paper-daemon-retention-preserve-recent", type=int, default=20, help="Number of newest daemon artifacts retained regardless of age.")
    parser.add_argument("--paper-daemon-current-notional", type=float, default=25.0, help="Current paper notional tier used by paper-daemon-ops notional mode.")
    parser.add_argument("--paper-daemon-required-clean-iterations", type=int, default=10, help="Clean submitted daemon iterations required before notional escalation is recommended.")
    parser.add_argument("--paper-command-center-output", default="reports/paper-command-center.json", help="Path for the paper command-center JSON summary.")
    parser.add_argument("--paper-command-center-stale-seconds", type=float, default=900.0, help="Heartbeat age after which the command center marks the daemon stale.")
    parser.add_argument("--paper-proof-quantity", type=float, default=1.0, help="Tiny quantity used by paper-broker-proof mode.")
    parser.add_argument("--paper-proof-limit-price", type=float, default=1.0, help="Conservative limit price used by paper-broker-proof mode.")
    parser.add_argument("--paper-proof-max-notional", type=float, default=25.0, help="Maximum planned notional allowed by paper-broker-proof mode.")
    parser.add_argument("--paper-proof-side", choices=["BUY", "SELL"], default="BUY", help="Order side used by paper-broker-proof mode.")
    parser.add_argument("--paper-proof-client-order-id", help="Optional client order id for duplicate-protection paper proof runs.")
    parser.add_argument("--fill-poll-attempts", type=int, default=1, help="Number of broker execution-report polling attempts after a paper proof submit/cancel.")
    parser.add_argument("--fill-poll-interval-seconds", type=float, default=0.0, help="Delay between broker execution-report polling attempts.")
    parser.add_argument("--paper-proof-symbol-allowlist", help="Comma-separated symbols allowed for broker-proof submission.")
    parser.add_argument("--max-daily-proof-submissions", type=int, help="Maximum submitted broker-proof orders allowed per UTC date.")
    parser.add_argument("--paper-proof-kill-switch", action="store_true", help="Block broker-proof submission regardless of other guards.")
    parser.add_argument("--repeated-reject-lockout-threshold", type=int, help="Block broker-proof submission after this many prior rejected proof orders for the symbol.")
    parser.add_argument("--paper-proof-prior-dir", help="Directory of prior broker-proof JSON artifacts for approval-policy limits.")
    parser.add_argument("--allow-pre-market", action="store_true", help="Allow paper-broker-proof submissions during the configured pre-market session.")
    parser.add_argument("--allow-after-hours", action="store_true", help="Allow paper-broker-proof submissions during the configured after-hours session.")
    parser.add_argument("--comparison-provider", choices=["sample", "yfinance", "alpaca"], help="Optional secondary provider for paper-session data drift checks.")
    parser.add_argument("--soak-sessions", type=int, help="Number of guarded paper sessions to run in paper-soak mode.")
    parser.add_argument("--paper-soak-output", default="reports/paper-soak-report.json", help="Path for the paper-soak scoreboard and promotion-gate report.")
    parser.add_argument("--paper-soak-min-clean-streak", type=int, default=10, help="Clean pass streak required before micro paper can graduate to larger notional.")
    parser.add_argument("--paper-soak-acknowledge-failure", action="store_true", help="Acknowledge a paper-soak failure halt for the selected operator action.")
    parser.add_argument("--paper-soak-operator-action", choices=["retry", "flatten", "disable"], help="Operator action after a paper-soak failure halt.")
    parser.add_argument(
        "--paper-profile",
        choices=paper_profile_choices,
        help="Apply a named paper profile with validation and risk-budget defaults.",
    )
    parser.add_argument(
        "--paper-daemon-profile",
        choices=paper_profile_choices,
        help="Apply daemon-specific profile defaults for bounded soaks, monitoring, cleanup, parity, and submit intent.",
    )
    parser.add_argument(
        "--paper-profile-preview",
        action="store_true",
        help="Apply paper-profile sizing and risk defaults but force no broker submission and skip broker/provider requirements.",
    )
    parser.add_argument("--recover-state", action="store_true", help="Load and reconcile persisted broker state before a paper-session or paper-soak decision.")
    parser.add_argument("--state-db-path", help="Override the SQLite broker state path for recovery/persistence.")
    parser.add_argument("--param-grid", default="{}", help="JSON object of strategy parameter lists for optimize mode.")
    parser.add_argument("--param-grid-file", help="Path to a JSON parameter grid file for optimize mode.")
    parser.add_argument("--metric", default="total_return", help="Metric to optimize.")
    parser.add_argument("--bulk-output", default="reports/bulk-backtest-summary.json", help="Path for a bulk backtest summary JSON report.")
    parser.add_argument("--benchmark-strategy", default="buyHold", help="Benchmark strategy for benchmark-relative bulk reports.")
    parser.add_argument("--benchmark-output", help="Optional path for a benchmark-relative bulk research report.")
    parser.add_argument("--promotion-output", help="Optional path for paper-candidate promotion manifests derived from benchmark-relative bulk selections.")
    parser.add_argument("--promotion-input", help="Optional benchmark promotion JSON whose enabled manifests seed paper-portfolio runs.")
    parser.add_argument("--research-matrix-file", default="configs/research/cross_asset_matrix.json", help="JSON research matrix for matrix mode.")
    parser.add_argument("--matrix-output", default="reports/research-matrix-summary.json", help="Path for matrix-mode JSON summary output.")
    parser.add_argument("--replication-file", default="configs/research/published_strategy_replications.json", help="JSON published-strategy replication suite for replicate mode.")
    parser.add_argument("--replication-output", default="reports/published-strategy-replication.json", help="Path for replicate-mode JSON comparison output.")
    parser.add_argument("--validation-output", default="reports/validation-readiness.json", help="Path for validate-mode readiness manifest output.")
    parser.add_argument("--evidence-dir", default="reports/evidence", help="Directory or JSON file containing validation evidence artifacts.")
    parser.add_argument("--readiness-html-output", default="reports/readiness.html", help="Path for the operator readiness HTML page written by validate and release-checklist modes.")
    parser.add_argument("--validation-profile", default="fast", choices=["smoke", "fast", "full", "paper-dry-run", "paper-submit", "release", "live-gate"], help="Validation profile to execute in validate-profile mode.")
    parser.add_argument("--validation-profile-output", help="Optional evidence bundle output path for validate-profile mode. Defaults to the selected profile output path.")
    parser.add_argument("--validation-run-id", help="Optional run id recorded in validate-profile evidence metadata.")
    parser.add_argument("--consume-existing-evidence", action="store_true", help="For validate-profile mode, skip manifest commands and score only existing artifacts plus native evidence producers.")
    parser.add_argument("--profiling-output", default="reports/profiling-report.json", help="Path for profile-mode benchmark and budget report output.")
    parser.add_argument("--profiling-repeats", type=int, default=1, help="Number of measured repeats per profile-mode benchmark task.")
    parser.add_argument("--release-output", default="reports/release-validation-bundle.json", help="Path for release-checklist mode output.")
    parser.add_argument("--release-candidate-output", default="reports/release-candidate-bundle.json", help="Path for the release-candidate bundle written by release-checklist mode.")
    parser.add_argument("--rehearsal-evidence-dir", default="reports/evidence/release-rehearsal", help="Directory for release-rehearsal generated evidence bundles.")
    parser.add_argument("--rehearsal-output", default="reports/release-rehearsal-summary.json", help="Path for the release-rehearsal orchestration summary.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        help="Maximum runtime before the CLI interrupts the job and then hard-exits if cleanup stalls. Defaults are mode-specific.",
    )
    return parser


def load_json_options(raw: str = "{}", path: Optional[str] = None) -> dict:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.loads(raw)


def build_config(args: argparse.Namespace):
    return load_runtime_config(
        {
            "symbol": args.symbol,
            "provider": args.provider,
            "period": args.period,
            "interval": args.interval,
            "start": getattr(args, "start", None),
            "end": getattr(args, "end", None),
            "strategy": args.strategy,
            "strategy_params": load_json_options(
                getattr(args, "strategy_params", "{}"),
                getattr(args, "strategy_params_file", None),
            ),
            "execution_mode": getattr(args, "execution_mode", None),
        }
    )


def run_backtest_app(
    app: TradingApplication,
    show_plot: bool = False,
    output: Optional[str] = None,
    store_dir: str = "runs",
) -> None:
    data = app.load_data()
    strategy = app.create_strategy()
    result = app.run_backtest(data, strategy)
    print(format_backtest_summary(result))
    store = JsonlStore(store_dir)
    store.write_many("equity", [{"timestamp": str(index), "equity": value} for index, value in result.equity.items()])
    store.write_many("fills", [{"order_id": fill.order.id, "symbol": fill.order.symbol, "side": fill.order.side, "quantity": fill.quantity, "price": fill.price} for fill in result.fills])
    if output:
        destination = write_backtest_report(result, output)
        print(f"Report written: {destination}")
    if show_plot:
        try:
            plot_backtest(data, strategy, result)
        except ValueError as exc:
            print(f"Plot skipped: {exc}")


def run_stream_app(app: TradingApplication, store_dir: str = "runs", label: str = "Stream", flatten_on_stop: bool = False) -> TradingEngine:
    engine = app.create_engine()
    event_count = 0
    store = JsonlStore(store_dir)

    def print_event(event: EngineEvent) -> None:
        nonlocal event_count
        event_count += 1
        store.append("engine-events", {"type": event.event_type.value, "message": event.message, "payload": event.payload, "timestamp": event.timestamp})
        if event.event_type.value == "SIGNAL" and event.payload.get("action") == "HOLD":
            return
        if event.event_type.value in {"STARTED", "STOPPED", "SIGNAL", "ORDER", "FILL", "ERROR"}:
            print(f"{event.event_type.value}: {event.message} {event.payload}")

    engine.add_handler(print_event)
    try:
        engine.start()
    except KeyboardInterrupt:
        print("Stream interrupted by user.")
    finally:
        if flatten_on_stop and engine.state in {EngineState.RUNNING, EngineState.PAUSED}:
            engine.flatten_positions()
        if engine.state != EngineState.STOPPED:
            engine.stop()
    print(f"{label} run complete. Engine events: {event_count}")
    return engine


def run_report_app(app: TradingApplication, html_output: str) -> None:
    data = app.load_data()
    strategy = app.create_strategy()
    result = app.run_backtest(data, strategy)
    destination = write_backtest_html_report(result, html_output)
    print(format_backtest_summary(result))
    print(f"HTML report written: {destination}")


def run_optimize_app(app: TradingApplication, param_grid: str, metric: str, store_dir: str = "runs", param_grid_file: Optional[str] = None) -> None:
    data = app.load_data()
    grid = load_json_options(param_grid, param_grid_file)
    results = grid_search(
        strategy_name=app.config.strategy.name,
        symbol=app.config.data.symbol,
        data=data,
        param_grid=grid,
        metric=metric,
    )
    store = JsonlStore(store_dir)
    store.write_many(
        "optimization-results",
        [
            {
                "rank": index + 1,
                "strategy": result.strategy_name,
                "params": result.params,
                "score": result.score,
                "rank_metrics": result.rank_metrics(),
            }
            for index, result in enumerate(results)
        ],
    )
    if results:
        best = results[0]
        print(f"Best params: {best.params} score={best.score:.6f}")
    print(f"Optimization runs: {len(results)}")


def load_symbol_list(symbols: Optional[str] = None, symbols_file: Optional[str] = None, fallback: str = "SPY", max_symbols: int = 100) -> list[str]:
    values = []
    if symbols:
        values.extend(symbols.split(","))
    if symbols_file:
        path = Path(symbols_file)
        text = path.read_text(encoding="utf-8").strip()
        if text:
            if path.suffix.lower() == ".json":
                payload = json.loads(text)
                values.extend(payload.get("symbols", []) if isinstance(payload, dict) else payload)
            else:
                for line in text.splitlines():
                    values.extend(line.split(","))
    if not values:
        values = [fallback]

    normalized = []
    seen = set()
    for value in values:
        symbol = str(value).strip().upper()
        if not symbol or symbol in seen:
            continue
        normalized.append(symbol)
        seen.add(symbol)
        if len(normalized) >= max_symbols:
            break
    return normalized


def load_bulk_strategy_params(strategies: list[str], strategy_param_dir: str, explicit_params: Optional[dict] = None) -> dict[str, dict]:
    params_by_strategy = {}
    directory = Path(strategy_param_dir)
    for strategy in strategies:
        candidates = [
            directory / f"{strategy}_cross_market_candidate.json",
            directory / f"{strategy}_default.json",
            directory / f"{_camel_to_snake(strategy)}_cross_market_candidate.json",
            directory / f"{_camel_to_snake(strategy)}_default.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                params_by_strategy[strategy] = load_json_options(path=str(candidate))
                break
        else:
            params_by_strategy[strategy] = {}
    if explicit_params and len(strategies) == 1:
        params_by_strategy[strategies[0]] = explicit_params
    return params_by_strategy


def run_bulk_backtest_app(args: argparse.Namespace) -> None:
    symbols = load_symbol_list(args.symbols, args.symbols_file, fallback=args.symbol, max_symbols=args.max_symbols)
    strategies = [value.strip() for value in (args.strategies or args.strategy).split(",") if value.strip()]
    explicit_params = load_json_options(getattr(args, "strategy_params", "{}"), getattr(args, "strategy_params_file", None))
    params_by_strategy = load_bulk_strategy_params(strategies, args.strategy_param_dir, explicit_params=explicit_params)

    def load_symbol_data(symbol: str):
        config = load_runtime_config(
            {
                "symbol": symbol,
                "provider": args.provider,
                "period": args.period,
                "interval": args.interval,
                "start": args.start,
                "end": args.end,
            }
        )
        return TradingApplication(config).load_data()

    store = JsonlStore(args.store_dir)
    report = run_bulk_backtests(
        symbols=symbols,
        strategies=strategies,
        data_loader=load_symbol_data,
        strategy_params=params_by_strategy,
        config=BacktestConfig(),
        store=store,
    )

    output = Path(args.bulk_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Bulk backtest complete. Symbols: {len(symbols)} Strategies: {len(strategies)} Completed: {report.completed} Failed: {report.failed}")
    print(f"Bulk summary written: {output}")
    benchmark_report = None
    if args.benchmark_output or args.promotion_output:
        benchmark_report = benchmark_relative_report(
            report.records,
            StrategySelectionPolicy(benchmark_strategy=args.benchmark_strategy),
        )
        if args.benchmark_output:
            benchmark_output = Path(args.benchmark_output)
            benchmark_output.parent.mkdir(parents=True, exist_ok=True)
            benchmark_output.write_text(json.dumps(benchmark_report.to_dict(), indent=2), encoding="utf-8")
            print(f"Benchmark-relative report written: {benchmark_output}")
        for row in benchmark_report.strategy_summary()[:5]:
            print(
                f"{row.strategy} vs {args.benchmark_strategy}: "
                f"avg_excess={row.average_excess_return:.2%} select_rate={row.select_rate:.2%} "
                f"avg_dd_improvement={row.average_drawdown_improvement:.2%}"
            )
    if args.promotion_output and benchmark_report is not None:
        promotion_report = build_benchmark_promotion_report(report.records, benchmark_report.selection_report)
        promotion_output = Path(args.promotion_output)
        promotion_output.parent.mkdir(parents=True, exist_ok=True)
        promotion_output.write_text(json.dumps(promotion_report.to_dict(), indent=2), encoding="utf-8")
        print(f"Research promotion report written: {promotion_output}")
        print(f"Paper candidates: {promotion_report.enabled_count}/{promotion_report.candidate_count}")
    for row in report.strategy_summary():
        print(
            f"{row['strategy']}: markets={row['markets']} "
            f"avg_return={row['average_return']:.2%} median={row['median_return']:.2%} "
            f"win_rate={row['win_rate']:.2%} avg_drawdown={row['average_max_drawdown']:.2%}"
        )


def run_research_matrix_app(args: argparse.Namespace) -> None:
    matrix = load_research_matrix(args.research_matrix_file)
    strategies = [value.strip() for value in (args.strategies or args.strategy).split(",") if value.strip()]
    explicit_params = load_json_options(getattr(args, "strategy_params", "{}"), getattr(args, "strategy_params_file", None))
    params_by_strategy = load_bulk_strategy_params(strategies, args.strategy_param_dir, explicit_params=explicit_params)

    def data_loader_factory(job):
        def load_symbol_data(symbol: str):
            period = job.window.period if job.window.period else None if (job.window.start or job.window.end) else args.period
            config = load_runtime_config(
                {
                    "symbol": symbol,
                    "provider": job.provider,
                    "interval": job.interval,
                    "period": period,
                    "start": job.window.start,
                    "end": job.window.end,
                }
            )
            return TradingApplication(config).load_data()

        return load_symbol_data

    store = JsonlStore(args.store_dir)
    report = run_research_matrix(
        config=matrix,
        strategies=strategies,
        data_loader_factory=data_loader_factory,
        strategy_params=params_by_strategy,
        backtest_config=BacktestConfig(),
        store=store,
        max_symbols_per_group=args.max_symbols,
    )
    output = Path(args.matrix_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Research matrix complete. Jobs: {len(report.job_results)} Completed: {report.completed} Failed: {report.failed}")
    print(f"Research matrix summary written: {output}")
    for row in report.asset_class_summary():
        print(f"{row['asset_class']}: jobs={row['jobs']} completed={row['completed']} failed={row['failed']}")


def run_replication_app(args: argparse.Namespace) -> None:
    suite = load_replication_suite(args.replication_file)
    report = run_replication_suite(suite)
    output = write_replication_report(report, args.replication_output)
    print(f"Published replication complete. Runs: {len(report.results)}")
    print(f"Replication report written: {output}")
    for row in report.to_dict()["rows"]:
        ours = row["ours"]
        published = row["published"]
        print(
            f"{row['profile']} {row['name']}: "
            f"return={ours['return_pct']:.2f}% vs {_format_optional_pct(published['return_pct'])} "
            f"trades={ours['trades']} vs {_format_optional_value(published['trades'])} "
            f"win={ours['win_rate_pct']:.2f}% vs {_format_optional_pct(published['win_rate_pct'])}"
        )


def run_paper_session_app(app: TradingApplication, args: argparse.Namespace) -> None:
    result = run_autonomous_paper_session(
        app,
        _paper_session_options(app, args),
    )
    print(json.dumps(result.to_dict(), indent=2))
    if result.report_path:
        print(f"Paper session report written: {result.report_path}")


def run_paper_session_schedule_app(
    app: TradingApplication,
    args: argparse.Namespace,
    now: datetime | None = None,
) -> None:
    report = run_scheduled_paper_session(
        app,
        _paper_session_options(app, args),
        now=now,
        artifact_root=args.store_dir,
        schedule_output_path=args.paper_session_schedule_output,
    )
    print(json.dumps(report.to_dict(), indent=2))
    if report.artifact_path:
        print(f"Paper session schedule written: {report.artifact_path}")


def run_paper_daemon_app(app: TradingApplication, args: argparse.Namespace) -> None:
    session_args = _paper_daemon_session_args(args)
    report = run_paper_trading_daemon(
        app,
        _paper_session_options(app, session_args),
        _paper_daemon_options(args),
    )
    print(json.dumps(report.to_dict(), indent=2))
    print(f"Paper daemon report written: {report.artifact_path}")


def run_paper_daemon_stop_app(args: argparse.Namespace) -> None:
    output = request_paper_daemon_stop(args.paper_daemon_kill_switch, reason=args.paper_daemon_stop_reason)
    print(f"Paper daemon kill switch written: {output}")


def run_paper_daemon_clear_stop_app(args: argparse.Namespace) -> None:
    removed = clear_paper_daemon_stop(args.paper_daemon_kill_switch)
    status = "cleared" if removed else "not present"
    print(f"Paper daemon kill switch {status}: {args.paper_daemon_kill_switch}")


def run_paper_daemon_status_app(args: argparse.Namespace) -> None:
    state = load_paper_daemon_state(args.paper_daemon_state_output)
    kill_switch_active = Path(args.paper_daemon_kill_switch).exists()
    print(json.dumps({**dict(state), "kill_switch_active": kill_switch_active}, indent=2))


def run_paper_daemon_ops_app(args: argparse.Namespace) -> None:
    report_type = args.paper_daemon_ops_type
    if report_type == "recovery":
        report = build_paper_daemon_recovery_report(
            args.paper_daemon_state_output,
            args.paper_daemon_lock_path,
            stale_after_seconds=args.paper_daemon_lock_stale_seconds,
        )
    elif report_type == "daily-summary":
        report = build_paper_daemon_daily_summary_report(_load_daemon_report_payload(args))
    elif report_type == "notifications":
        state = load_paper_daemon_state(args.paper_daemon_state_output)
        recovery = build_paper_daemon_recovery_report(
            args.paper_daemon_state_output,
            args.paper_daemon_lock_path,
            stale_after_seconds=args.paper_daemon_lock_stale_seconds,
        )
        report = build_paper_daemon_notification_report(state, recovery_report=recovery)
    elif report_type == "notional":
        report = build_paper_daemon_notional_decision_report(
            _load_daemon_report_payload(args),
            current_notional=args.paper_daemon_current_notional,
            required_clean_iterations=args.paper_daemon_required_clean_iterations,
        )
    elif report_type == "restart-drill":
        report = build_paper_daemon_restart_drill_report(_load_daemon_restart_drill_payload(args))
    elif report_type == "activation-checklist":
        report = build_paper_daemon_activation_checklist_report(
            _load_daemon_report_payload(args),
            daily_summary=_load_optional_json_mapping(args.paper_daemon_daily_summary_input),
            command_center=_load_optional_json_mapping(args.paper_command_center_input),
            kill_switch_proof=_load_optional_json_mapping(args.paper_daemon_kill_proof_input),
            cleanup_evidence=_load_optional_json_mapping(args.paper_daemon_cleanup_input)
            or _load_optional_json_mapping(getattr(args, "paper_cleanup_output", None)),
            acknowledged_exposure=_load_optional_json_mapping(args.paper_daemon_acknowledged_exposure_input),
            require_submitted_iteration=not args.paper_daemon_activation_allow_no_submit,
        )
    elif report_type == "exposure-ack-template":
        report = build_paper_exposure_acknowledgement_template_report(
            _load_optional_json_mapping(args.paper_daemon_cleanup_input)
            or _load_optional_json_mapping(getattr(args, "paper_cleanup_output", None))
            or {},
            max_notional_buffer_pct=args.paper_daemon_ack_template_buffer_pct,
            expires_at=args.paper_daemon_ack_template_expires_at,
        )
    elif report_type == "supervised-soak":
        report = build_paper_daemon_supervised_soak_report(
            _load_json_mapping_list(args.paper_daemon_activation_inputs),
            required_clean_activations=args.paper_daemon_soak_required_clean_activations,
            required_active_windows=args.paper_daemon_soak_required_active_windows,
            require_submitted_iterations=not args.paper_daemon_activation_allow_no_submit,
            max_total_observed_notional=args.paper_daemon_soak_max_observed_notional,
        )
    elif report_type == "position-stewardship":
        report = build_paper_position_stewardship_report(
            _load_optional_json_mapping(args.paper_daemon_position_monitor_input)
            or _load_optional_json_mapping(getattr(args, "paper_monitor_output", None))
            or {},
            cleanup_evidence=_load_optional_json_mapping(args.paper_daemon_position_cleanup_input),
            max_active_age_hours=args.paper_daemon_position_max_age_hours,
        )
    elif report_type == "flatten-drill":
        report = build_paper_daemon_flatten_drill_report(
            _load_optional_json_mapping(args.paper_daemon_flatten_pre_monitor_input) or {},
            _load_optional_json_mapping(args.paper_daemon_flatten_plan_input) or {},
            _load_optional_json_mapping(args.paper_daemon_flatten_cleanup_input) or {},
            _load_optional_json_mapping(args.paper_daemon_flatten_post_monitor_input) or {},
            stewardship=_load_optional_json_mapping(args.paper_daemon_flatten_stewardship_input),
        )
    elif report_type == "soak-rollup":
        report = build_paper_daemon_soak_readiness_rollup_report(
            _load_optional_json_mapping(args.paper_daemon_activation_checklist_input) or {},
            _load_optional_json_mapping(args.paper_daemon_supervised_soak_input) or {},
            command_center=_load_optional_json_mapping(args.paper_command_center_input),
            monitor=_load_optional_json_mapping(args.paper_daemon_position_monitor_input)
            or _load_optional_json_mapping(getattr(args, "paper_monitor_output", None)),
            cleanup=_load_optional_json_mapping(args.paper_daemon_position_cleanup_input)
            or _load_optional_json_mapping(args.paper_daemon_cleanup_input),
            data_parity=_load_optional_json_mapping(args.paper_daemon_data_parity_input),
            notional_decision=_load_optional_json_mapping(args.paper_daemon_notional_input),
            stewardship=_load_optional_json_mapping(args.paper_daemon_stewardship_input)
            or _load_optional_json_mapping(args.paper_daemon_flatten_stewardship_input),
            flatten_drill=_load_optional_json_mapping(args.paper_daemon_flatten_drill_input),
        )
    elif report_type == "window-capture-plan":
        report = build_paper_daemon_window_capture_plan_report(
            _load_optional_json_mapping(args.paper_daemon_supervised_soak_input) or {},
            required_window_names=_parse_csv(args.paper_daemon_window_capture_windows),
            provider=args.provider,
            symbol=args.symbol,
            strategy=args.strategy,
            paper_profile=args.paper_profile or "micro-notional",
            interval_seconds=args.paper_daemon_interval_seconds,
            max_iterations=args.paper_daemon_window_capture_max_iterations,
        )
    else:
        report = build_paper_daemon_retention_plan(
            _daemon_retention_paths(args),
            keep_days=args.paper_daemon_retention_keep_days,
            preserve_recent=args.paper_daemon_retention_preserve_recent,
        )

    output = write_paper_daemon_ops_report(report, args.paper_daemon_ops_output)
    print(json.dumps(report.to_dict(), indent=2))
    print(f"Paper daemon ops report written: {output}")


def _load_daemon_report_payload(args: argparse.Namespace) -> Mapping[str, Any]:
    for candidate in (args.paper_daemon_report_input, getattr(args, "paper_daemon_report_output", None)):
        if not candidate:
            continue
        input_path = Path(candidate)
        if input_path.exists():
            payload = json.loads(input_path.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                return payload
    state = load_paper_daemon_state(args.paper_daemon_state_output)
    return {"state": dict(state), "iterations": []}


def _load_daemon_restart_drill_payload(args: argparse.Namespace) -> Mapping[str, Any]:
    input_path_value = getattr(args, "paper_daemon_restart_drills_input", None)
    if input_path_value:
        input_path = Path(input_path_value)
        if input_path.exists():
            payload = json.loads(input_path.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                return payload
    return {"drills": [], "order_artifacts": []}


def _load_optional_json_mapping(path_value: str | None) -> Mapping[str, Any] | None:
    if not path_value:
        return None
    input_path = Path(path_value)
    if not input_path.exists():
        return None
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, Mapping) else None


def _load_json_mapping_list(path_values: str | None) -> tuple[Mapping[str, Any], ...]:
    if not path_values:
        return ()
    payloads: list[Mapping[str, Any]] = []
    for value in path_values.split(","):
        path_value = value.strip()
        if not path_value:
            continue
        payload = _load_optional_json_mapping(path_value)
        if payload is not None:
            payloads.append({**dict(payload), "artifact_path": path_value})
    return tuple(payloads)


def _parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _daemon_retention_paths(args: argparse.Namespace) -> tuple[str, ...]:
    if args.paper_daemon_retention_paths:
        return tuple(path.strip() for path in args.paper_daemon_retention_paths.split(",") if path.strip())
    return (
        args.paper_daemon_state_output,
        args.paper_daemon_heartbeat_output,
        args.paper_daemon_lock_path,
        args.paper_daemon_schedule_output,
    )


def run_paper_command_center_app(args: argparse.Namespace) -> None:
    report = build_paper_command_center_report(
        provider=args.provider,
        symbol=args.symbol,
        strategy=args.strategy,
        execution_mode=args.execution_mode or "dry-run",
        paper_profile=getattr(args, "paper_daemon_profile", None) or getattr(args, "paper_profile", None),
        state_path=args.paper_daemon_state_output,
        kill_switch_path=args.paper_daemon_kill_switch,
        daemon_report_path=args.paper_daemon_report_input or args.paper_daemon_report_output,
        monitor_path=args.paper_monitor_output,
        pnl_path=args.paper_pnl_attribution_output or "reports/paper-pnl-attribution-report.json",
        drawdown_path=args.paper_drawdown_output or "reports/paper-drawdown-report.json",
        fills_path=Path(args.store_dir) / "fills.jsonl",
        stale_after_seconds=args.paper_command_center_stale_seconds,
    )
    output = write_paper_command_center_report(report, args.paper_command_center_output)
    print("\n".join(report.summary_lines()))
    print(f"Paper command center written: {output}")


def run_paper_broker_proof_app(
    app: TradingApplication,
    args: argparse.Namespace,
    now: datetime | None = None,
    broker_factory=None,
) -> None:
    report = run_paper_broker_proof(
        app.config,
        broker_factory or app.create_broker,
        PaperBrokerOrderPlan(
            symbol=args.symbol,
            side=args.paper_proof_side,
            quantity=args.paper_proof_quantity,
            limit_price=args.paper_proof_limit_price,
            max_notional=args.paper_proof_max_notional,
            client_order_id=args.paper_proof_client_order_id,
        ),
        _paper_broker_proof_options(args, now=now),
        output_path=args.paper_proof_output,
    )
    print(json.dumps(report.to_dict(), indent=2))
    if report.artifact_path:
        print(f"Paper broker proof written: {report.artifact_path}")


def run_paper_broker_schedule_app(
    app: TradingApplication,
    args: argparse.Namespace,
    now: datetime | None = None,
    broker_factory=None,
) -> None:
    if getattr(args, "paper_proof_existing_artifact", None):
        report = run_scheduled_paper_broker_proof_from_artifact(
            args.paper_proof_existing_artifact,
            schedule_output_path=args.paper_proof_schedule_output,
        )
        print(json.dumps(report.to_dict(), indent=2))
        if report.artifact_path:
            print(f"Paper broker proof schedule written: {report.artifact_path}")
        return
    report = run_scheduled_paper_broker_proof(
        app.config,
        broker_factory or app.create_broker,
        PaperBrokerOrderPlan(
            symbol=args.symbol,
            side=args.paper_proof_side,
            quantity=args.paper_proof_quantity,
            limit_price=args.paper_proof_limit_price,
            max_notional=args.paper_proof_max_notional,
            client_order_id=args.paper_proof_client_order_id,
        ),
        artifact_root=args.paper_proof_artifact_root,
        schedule_output_path=args.paper_proof_schedule_output,
        options=_paper_broker_proof_options(args, now=now),
    )
    print(json.dumps(report.to_dict(), indent=2))
    if report.artifact_path:
        print(f"Paper broker proof schedule written: {report.artifact_path}")


def run_paper_activation_report_app(args: argparse.Namespace) -> None:
    report = build_paper_activation_report(
        broker_proof_path=args.paper_proof_output,
        scheduled_broker_proof_path=args.paper_proof_schedule_output,
        paper_submit_evidence_path=args.paper_submit_evidence,
        paper_cleanup_path=args.paper_cleanup_output,
        notes=("operator activation report",),
    )
    output = write_paper_activation_report(report, args.paper_activation_output)
    print(json.dumps(report.to_dict(), indent=2))
    print(f"Paper activation report written: {output}")


def run_paper_cleanup_app(app: TradingApplication, args: argparse.Namespace) -> None:
    symbols = tuple(
        value.strip().upper()
        for value in (getattr(args, "paper_cleanup_symbols", None) or "").split(",")
        if value.strip()
    )
    report = run_paper_cleanup(
        app,
        PaperCleanupOptions(
            submit_orders=args.submit_orders,
            artifact_path=args.paper_cleanup_output,
            symbols=symbols,
            approval_options=_paper_session_options(app, args),
            fill_poll_attempts=getattr(args, "fill_poll_attempts", 1),
            fill_poll_interval_seconds=getattr(args, "fill_poll_interval_seconds", 0.0),
        ),
    )
    print(json.dumps(report.to_dict(), indent=2))
    if report.artifact_path:
        print(f"Paper cleanup report written: {report.artifact_path}")


def run_paper_monitor_app(app: TradingApplication, args: argparse.Namespace) -> None:
    portfolio_payload = _load_json_payload(args.paper_monitor_portfolio_input)
    if getattr(args, "paper_monitor_position_input", None):
        position_payload = _load_json_payload(args.paper_monitor_position_input)
    else:
        position_snapshot = run_paper_cleanup(
            app,
            PaperCleanupOptions(
                submit_orders=False,
                artifact_path=args.paper_cleanup_output,
                approval_options=_paper_session_options(app, args),
            ),
        )
        position_payload = position_snapshot.to_dict()
    open_order_payload = None
    open_order_broker = None
    if getattr(args, "paper_open_orders_input", None):
        open_order_payload = _load_json_payload(args.paper_open_orders_input)
    elif (
        getattr(args, "paper_open_orders_output", None)
        or getattr(args, "paper_stale_order_cancel_output", None)
        or getattr(args, "paper_cancel_stale_orders", False)
    ):
        open_order_broker = app.create_broker()
        open_order_payload = paper_open_order_snapshot_from_broker(open_order_broker)
    cleanup_payload = (
        _load_json_payload(args.paper_monitor_cleanup_input)
        if getattr(args, "paper_monitor_cleanup_input", None)
        else None
    )
    report = build_paper_monitor_report(
        portfolio_payload,
        position_payload,
        max_expected_notional=getattr(args, "paper_monitor_max_notional", None),
        open_order_snapshot=open_order_payload,
        max_open_order_age_minutes=getattr(args, "paper_open_order_timeout_minutes", 15.0),
        cleanup_evidence=cleanup_payload,
    )
    output = write_paper_monitor_report(report, args.paper_monitor_output, journal_path=getattr(args, "paper_position_journal", None))
    open_orders_output = None
    if report.open_orders and getattr(args, "paper_open_orders_output", None):
        open_orders_output = write_paper_open_order_report(report.open_orders, args.paper_open_orders_output)
    stale_cancel_output = None
    if report.open_orders and (
        getattr(args, "paper_stale_order_cancel_output", None)
        or getattr(args, "paper_cancel_stale_orders", False)
    ):
        cancel_report = run_paper_stale_order_cancel(
            report.open_orders,
            broker=open_order_broker or app.create_broker(),
            cancel_requested=getattr(args, "paper_cancel_stale_orders", False),
        )
        stale_cancel_output = write_paper_stale_order_cancel_report(
            cancel_report,
            getattr(args, "paper_stale_order_cancel_output", None) or "reports/paper-stale-order-cancel-report.json",
        )
    exit_preview_output = None
    if report.lifecycle and getattr(args, "paper_exit_preview_output", None):
        exit_preview = build_paper_exit_preview(
            report.lifecycle,
            include_active_positions=getattr(args, "paper_exit_preview_active", False),
        )
        exit_preview_output = write_paper_exit_preview_report(exit_preview, args.paper_exit_preview_output)
    controlled_flatten_output = None
    if report.lifecycle and getattr(args, "paper_controlled_flatten_output", None):
        flatten_symbols = tuple(
            value.strip().upper()
            for value in (getattr(args, "paper_controlled_flatten_symbols", None) or "").split(",")
            if value.strip()
        )
        controlled_flatten = build_paper_controlled_flatten_plan(
            report.lifecycle,
            symbols=flatten_symbols,
            exit_reason=getattr(args, "paper_controlled_flatten_reason", "operator_requested_controlled_flatten"),
        )
        controlled_flatten_output = write_paper_controlled_flatten_plan(
            controlled_flatten,
            args.paper_controlled_flatten_output,
        )
    eod_closeout_output = None
    if report.lifecycle and getattr(args, "paper_eod_closeout_output", None):
        eod_closeout = build_paper_eod_closeout_report(
            report.lifecycle,
            default_overnight_policy=getattr(args, "paper_eod_overnight_policy", "hold"),
            reduce_fraction=getattr(args, "paper_eod_reduce_fraction", 0.5),
        )
        eod_closeout_output = write_paper_eod_closeout_report(eod_closeout, args.paper_eod_closeout_output)
    pnl_attribution_output = None
    if report.lifecycle and getattr(args, "paper_pnl_attribution_output", None):
        pnl_attribution = build_paper_pnl_attribution_report(report.lifecycle)
        pnl_attribution_output = write_paper_pnl_attribution_report(pnl_attribution, args.paper_pnl_attribution_output)
    drawdown_output = None
    if report.lifecycle and getattr(args, "paper_drawdown_output", None):
        account = app.create_broker().account_snapshot()
        drawdown = build_paper_drawdown_report(
            report.lifecycle,
            account_snapshot={
                "equity": account.equity,
                "cash": account.cash,
                "buying_power": account.buying_power,
                "captured_at": account.captured_at.isoformat(),
            },
            prior_peak_equity=getattr(args, "paper_drawdown_peak_equity", None),
        )
        drawdown_output = write_paper_drawdown_report(drawdown, args.paper_drawdown_output)
    market_snapshot_report = None
    market_snapshot_output = None
    if report.lifecycle and getattr(args, "paper_market_snapshot_output", None):
        symbols = tuple(position.symbol for position in report.lifecycle.positions)
        market_snapshot_report = _paper_market_snapshot_report(app, report.lifecycle, symbols)
        market_snapshot_output = write_live_market_snapshot_report(market_snapshot_report, args.paper_market_snapshot_output)
    data_freshness_output = None
    if market_snapshot_report and getattr(args, "paper_data_freshness_output", None):
        freshness = build_data_freshness_report(
            _freshness_rows_from_snapshots(market_snapshot_report),
            observed_at=datetime.fromisoformat(market_snapshot_report.observed_at),
        )
        data_freshness_output = write_data_freshness_report(freshness, args.paper_data_freshness_output)
    quote_spread_output = None
    if market_snapshot_report and report.lifecycle and getattr(args, "paper_quote_spread_output", None):
        quote_spread = build_quote_spread_report(
            market_snapshot_report.snapshots,
            _execution_rows_from_lifecycle(report.lifecycle),
        )
        quote_spread_output = write_quote_spread_report(quote_spread, args.paper_quote_spread_output)
    asset_metadata_report = None
    asset_metadata_output = None
    if report.lifecycle and getattr(args, "paper_asset_metadata_output", None):
        symbols = tuple(position.symbol for position in report.lifecycle.positions)
        asset_metadata_report = _paper_asset_metadata_report(app, symbols)
        asset_metadata_output = write_asset_class_metadata_report(asset_metadata_report, args.paper_asset_metadata_output)
    symbol_capability_output = None
    if getattr(args, "paper_symbol_capability_output", None):
        if asset_metadata_report is None and report.lifecycle:
            asset_metadata_report = _paper_asset_metadata_report(app, tuple(position.symbol for position in report.lifecycle.positions))
        if asset_metadata_report is not None:
            capabilities = build_symbol_capability_report(
                asset_metadata_report.assets,
                require_fractional=getattr(args, "paper_require_fractional", False),
                require_short=getattr(args, "paper_require_short", False),
                require_margin=getattr(args, "paper_require_margin", False),
            )
            symbol_capability_output = write_symbol_capability_report(capabilities, args.paper_symbol_capability_output)
    print(json.dumps({**report.to_dict(), "artifact_path": output}, indent=2))
    print(f"Paper monitor report written: {output}")
    if open_orders_output:
        print(f"Paper open-order report written: {open_orders_output}")
    if stale_cancel_output:
        print(f"Paper stale-order cancel report written: {stale_cancel_output}")
    if exit_preview_output:
        print(f"Paper exit preview written: {exit_preview_output}")
    if controlled_flatten_output:
        print(f"Paper controlled flatten plan written: {controlled_flatten_output}")
    if eod_closeout_output:
        print(f"Paper EOD closeout report written: {eod_closeout_output}")
    if pnl_attribution_output:
        print(f"Paper PnL attribution report written: {pnl_attribution_output}")
    if drawdown_output:
        print(f"Paper drawdown report written: {drawdown_output}")
    if market_snapshot_output:
        print(f"Paper market snapshot report written: {market_snapshot_output}")
    if data_freshness_output:
        print(f"Paper data freshness report written: {data_freshness_output}")
    if quote_spread_output:
        print(f"Paper quote spread report written: {quote_spread_output}")
    if asset_metadata_output:
        print(f"Paper asset metadata report written: {asset_metadata_output}")
    if symbol_capability_output:
        print(f"Paper symbol capability report written: {symbol_capability_output}")


def _paper_market_snapshot_report(app: TradingApplication, lifecycle, symbols: tuple[str, ...]):
    if app.config.data.provider.lower() == "alpaca":
        return fetch_alpaca_live_market_snapshots(app.config.alpaca, symbols)
    rows = []
    for position in lifecycle.positions:
        unit_price = None
        if position.market_value is not None and abs(position.observed_quantity) > 1e-12:
            unit_price = abs(position.market_value / position.observed_quantity)
        elif position.average_fill_price is not None:
            unit_price = position.average_fill_price
        rows.append(
            {
                "symbol": position.symbol,
                "provider": app.config.data.provider,
                "latest_trade_price": unit_price,
                "latest_trade_timestamp": position.fill_timestamp or position.opened_at,
                "bid_price": unit_price,
                "ask_price": unit_price,
                "quote_timestamp": position.fill_timestamp or position.opened_at,
            }
        )
    return build_live_market_snapshot_report(rows, provider=app.config.data.provider)


def _paper_asset_metadata_report(app: TradingApplication, symbols: tuple[str, ...]):
    if app.config.data.provider.lower() == "alpaca":
        return fetch_alpaca_asset_metadata(app.config.alpaca, symbols)
    return build_asset_class_metadata_report(
        [
            {
                "symbol": symbol,
                "asset_class": "etf" if symbol in {"SPY", "DIA", "QQQ", "IWM"} else "equity",
                "tradable": True,
                "fractionable": True,
                "shortable": False,
                "easy_to_borrow": False,
                "marginable": False,
            }
            for symbol in symbols
        ]
    )


def _paper_market_snapshot_report_from_portfolio(app: TradingApplication, portfolio: Mapping[str, Any]):
    symbols = tuple(portfolio.get("symbols") or ())
    if app.config.data.provider.lower() == "alpaca":
        return fetch_alpaca_live_market_snapshots(app.config.alpaca, symbols)
    rows = []
    for order in portfolio.get("consolidated_orders") or ():
        if not isinstance(order, Mapping):
            continue
        latest_price = order.get("latest_price")
        rows.append(
            {
                "symbol": order.get("symbol"),
                "provider": app.config.data.provider,
                "latest_trade_price": latest_price,
                "latest_trade_timestamp": order.get("created_at"),
                "bid_price": latest_price,
                "ask_price": latest_price,
                "quote_timestamp": order.get("created_at"),
            }
        )
    return build_live_market_snapshot_report(rows, provider=app.config.data.provider)


def _freshness_rows_from_snapshots(snapshot_report) -> tuple[Mapping[str, Any], ...]:
    rows = []
    for snapshot in snapshot_report.snapshots:
        if snapshot.latest_trade_timestamp:
            rows.append({"symbol": snapshot.symbol, "source": "latest_trade", "timestamp": snapshot.latest_trade_timestamp, "asset_class": "equity"})
        if snapshot.quote_timestamp:
            rows.append({"symbol": snapshot.symbol, "source": "latest_quote", "timestamp": snapshot.quote_timestamp, "asset_class": "equity"})
    return tuple(rows)


def _execution_rows_from_lifecycle(lifecycle) -> tuple[Mapping[str, Any], ...]:
    rows = []
    for position in lifecycle.positions:
        rows.append(
            {
                "symbol": position.symbol,
                "side": "BUY" if position.expected_quantity >= 0 else "SELL",
                "average_fill_price": position.average_fill_price,
            }
        )
    return tuple(rows)


def run_paper_pilot_app(app: TradingApplication, args: argparse.Namespace) -> None:
    cleanup_symbols = tuple(
        value.strip().upper()
        for value in (getattr(args, "paper_cleanup_symbols", None) or "").split(",")
        if value.strip()
    )
    cleanup_report = run_paper_cleanup(
        app,
        PaperCleanupOptions(
            submit_orders=args.submit_orders,
            artifact_path=args.paper_cleanup_output,
            symbols=cleanup_symbols,
            approval_options=_paper_session_options(app, args),
            fill_poll_attempts=getattr(args, "fill_poll_attempts", 1),
            fill_poll_interval_seconds=getattr(args, "fill_poll_interval_seconds", 0.0),
        ),
    )

    validation_args = _profile_namespace(
        args,
        "paper-submit",
        Path(args.paper_pilot_validation_output),
        getattr(args, "validation_run_id", None) or _validation_run_id("paper-pilot"),
    )
    validation_args.consume_existing_evidence = True
    validation_args.paper_cleanup_output = cleanup_report.artifact_path or args.paper_cleanup_output
    run_validation_profile_app(validation_args, app=app)
    validation_payload = _load_json_payload(validation_args.validation_profile_output)

    activation_report = build_paper_activation_report(
        broker_proof_path=args.paper_proof_output,
        scheduled_broker_proof_path=args.paper_proof_schedule_output,
        paper_submit_evidence_path=validation_args.validation_profile_output,
        paper_cleanup_path=cleanup_report.artifact_path or args.paper_cleanup_output,
        notes=("paper pilot orchestration",),
    )
    activation_output = write_paper_activation_report(activation_report, args.paper_activation_output)

    portfolio_payload = None
    if not getattr(args, "paper_pilot_skip_portfolio", False):
        portfolio_report = run_portfolio_paper_session(
            app,
            _paper_pilot_portfolio_options(app, args, validation_payload),
        )
        portfolio_payload = portfolio_report.to_dict()

    pilot_market_snapshot_output = None
    pilot_asset_metadata_output = None
    pilot_symbol_capability_output = None
    pilot_snapshot_report = None
    pilot_asset_report = None
    if portfolio_payload and getattr(args, "paper_market_snapshot_output", None):
        pilot_snapshot_report = _paper_market_snapshot_report_from_portfolio(app, portfolio_payload)
        pilot_market_snapshot_output = write_live_market_snapshot_report(pilot_snapshot_report, args.paper_market_snapshot_output)
    if portfolio_payload and getattr(args, "paper_asset_metadata_output", None):
        pilot_asset_report = _paper_asset_metadata_report(app, tuple(portfolio_payload.get("symbols") or ()))
        pilot_asset_metadata_output = write_asset_class_metadata_report(pilot_asset_report, args.paper_asset_metadata_output)
    if portfolio_payload and getattr(args, "paper_symbol_capability_output", None):
        if pilot_asset_report is None:
            pilot_asset_report = _paper_asset_metadata_report(app, tuple(portfolio_payload.get("symbols") or ()))
        capabilities = build_symbol_capability_report(
            pilot_asset_report.assets,
            require_fractional=getattr(args, "paper_require_fractional", False),
            require_short=getattr(args, "paper_require_short", False),
            require_margin=getattr(args, "paper_require_margin", False),
        )
        pilot_symbol_capability_output = write_symbol_capability_report(capabilities, args.paper_symbol_capability_output)

    artifacts = {
        "cleanup": str(cleanup_report.artifact_path or args.paper_cleanup_output),
        "paper_submit_validation": str(validation_args.validation_profile_output),
        "activation": str(activation_output),
    }
    if portfolio_payload and portfolio_payload.get("artifact_path"):
        artifacts["portfolio"] = str(portfolio_payload["artifact_path"])
    if pilot_market_snapshot_output:
        artifacts["market_snapshots"] = str(pilot_market_snapshot_output)
    if pilot_asset_metadata_output:
        artifacts["asset_metadata"] = str(pilot_asset_metadata_output)
    if pilot_symbol_capability_output:
        artifacts["symbol_capabilities"] = str(pilot_symbol_capability_output)
    report = build_paper_pilot_report(
        cleanup_report.to_dict(),
        validation_payload,
        activation_report.to_dict(),
        portfolio=portfolio_payload,
        artifacts=artifacts,
    )
    output = write_paper_pilot_report(report, args.paper_pilot_output)
    print(json.dumps({**report.to_dict(), "artifact_path": output}, indent=2))
    print(f"Paper pilot report written: {output}")
    if pilot_market_snapshot_output:
        print(f"Paper pilot market snapshot report written: {pilot_market_snapshot_output}")
    if pilot_asset_metadata_output:
        print(f"Paper pilot asset metadata report written: {pilot_asset_metadata_output}")
    if pilot_symbol_capability_output:
        print(f"Paper pilot symbol capability report written: {pilot_symbol_capability_output}")


def _paper_pilot_portfolio_options(
    app: TradingApplication,
    args: argparse.Namespace,
    validation_payload: Mapping[str, Any],
) -> PortfolioPaperSessionOptions:
    manifests = load_paper_session_manifests(args.promotion_input) if args.promotion_input else ()
    symbols = () if manifests else load_symbol_list(args.symbols, args.symbols_file, fallback=args.symbol, max_symbols=args.max_symbols)
    submit_portfolio = bool(getattr(args, "paper_pilot_submit_portfolio", False)) and _paper_pilot_submit_prereqs_passed(validation_payload)
    portfolio_args = argparse.Namespace(**vars(args))
    portfolio_args.submit_orders = submit_portfolio
    portfolio_args.paper_profile_preview = bool(getattr(args, "paper_profile_preview", False) or not submit_portfolio)
    session_template = _paper_session_options(app, portfolio_args)
    return PortfolioPaperSessionOptions(
        symbols=symbols,
        manifests=manifests,
        max_symbols=args.max_symbols,
        artifact_root=args.store_dir,
        session_template=session_template,
        requested_weight=0.10,
        comparison_provider=args.comparison_provider,
        recover_state=args.recover_state,
        state_db_path=args.state_db_path,
    )


def _paper_pilot_submit_prereqs_passed(validation_payload: Mapping[str, Any]) -> bool:
    required = {
        "alpaca_paper_order_lifecycle",
        "broker_account_parity",
        "paper_account_cleanup",
        "real_alpaca_fill_polling",
    }
    evidence = {
        item.get("check_id"): item
        for item in validation_payload.get("evidence", [])
        if isinstance(item, Mapping)
    }
    return all(evidence.get(check_id, {}).get("status") == "passed" for check_id in required)


def _load_json_payload(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _paper_broker_proof_options(args: argparse.Namespace, now: datetime | None = None) -> PaperBrokerProofOptions:
    return PaperBrokerProofOptions(
        submit_orders=args.submit_orders,
        allow_pre_market=args.allow_pre_market,
        allow_after_hours=args.allow_after_hours,
        fill_poll_attempts=args.fill_poll_attempts,
        fill_poll_interval_seconds=args.fill_poll_interval_seconds,
        approval_policy=_paper_broker_approval_policy(args),
        prior_reports=_load_prior_paper_proof_reports(getattr(args, "paper_proof_prior_dir", None)),
        now=now,
    )


def _paper_broker_approval_policy(args: argparse.Namespace) -> PaperBrokerProofApprovalPolicy:
    allowlist = tuple(
        symbol.strip().upper()
        for symbol in (getattr(args, "paper_proof_symbol_allowlist", "") or "").split(",")
        if symbol.strip()
    )
    return PaperBrokerProofApprovalPolicy(
        symbol_allowlist=allowlist,
        max_daily_submissions=getattr(args, "max_daily_proof_submissions", None),
        kill_switch_enabled=bool(getattr(args, "paper_proof_kill_switch", False)),
        repeated_reject_lockout_threshold=getattr(args, "repeated_reject_lockout_threshold", None),
    )


def _load_prior_paper_proof_reports(path: str | None) -> tuple[Mapping[str, Any], ...]:
    if not path:
        return ()
    root = Path(path)
    if not root.exists():
        return ()
    files = [root] if root.is_file() else sorted(root.glob("**/*paper-broker-proof.json"))
    reports = []
    for source in files:
        try:
            reports.append(json.loads(source.read_text(encoding="utf-8")))
        except Exception:
            continue
    return tuple(reports)


def run_paper_soak_app(app: TradingApplication, args: argparse.Namespace) -> None:
    report = run_paper_session_soak(
        app,
        _paper_session_options(app, args),
        _paper_soak_config(args),
    )
    output = write_paper_session_soak_report(report, args.paper_soak_output)
    print(json.dumps(report.to_dict(), indent=2))
    print(f"Paper soak report written: {output}")


def run_paper_portfolio_app(app: TradingApplication, args: argparse.Namespace) -> None:
    manifests = load_paper_session_manifests(args.promotion_input) if args.promotion_input else ()
    symbols = () if manifests else load_symbol_list(args.symbols, args.symbols_file, fallback=args.symbol, max_symbols=args.max_symbols)
    session_template = _paper_session_options(app, args)
    report = run_portfolio_paper_session(
        app,
        PortfolioPaperSessionOptions(
            symbols=symbols,
            manifests=manifests,
            max_symbols=args.max_symbols,
            artifact_root=args.store_dir,
            session_template=session_template,
            requested_weight=0.10,
            comparison_provider=args.comparison_provider,
            recover_state=args.recover_state,
            state_db_path=args.state_db_path,
        ),
    )
    print(json.dumps(report.to_dict(), indent=2))
    if report.artifact_path:
        print(f"Portfolio paper session report written: {report.artifact_path}")


def run_validate_app(args: argparse.Namespace) -> None:
    manifest = default_validation_manifest()
    evidence_bundle = _optional_evidence_bundle(getattr(args, "evidence_dir", "reports/evidence"))
    evidence = evidence_bundle.latest_evidence()
    readiness = build_readiness_index(evidence, manifest=manifest)
    freshness = evaluate_evidence_freshness(evidence, manifest=manifest, target=readiness.target)
    action_plan = build_validation_action_plan(readiness, freshness)
    not_live_ready = build_not_live_ready_report(readiness)
    paper_profiles = evaluate_paper_profile_validation()
    output = Path(args.validation_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    readiness_html_output = Path(getattr(args, "readiness_html_output", "reports/readiness.html"))
    payload = {
        "manifest": manifest.to_dict(),
        "evidence_bundle": evidence_bundle.to_dict(),
        "readiness_index": readiness.to_dict(),
        "evidence_freshness": freshness.to_dict(),
        "action_plan": action_plan.to_dict(),
        "not_live_ready": not_live_ready.to_dict(),
        "cli_smoke_plan": [spec.to_dict() for spec in default_cli_smoke_specs()],
        "performance_budgets": [budget.to_dict() for budget in default_performance_budgets()],
        "paper_profile_validation": paper_profiles.to_dict(),
        "release_checklist": default_release_checklist().to_dict(),
        "readiness_html_path": str(readiness_html_output),
    }
    write_readiness_html_page(payload, readiness_html_output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Validation readiness written: {output}")
    print(f"Readiness HTML written: {readiness_html_output}")
    print(
        f"Readiness target={readiness.target} score={readiness.readiness_score:.1%} "
        f"missing={len(readiness.missing_required)} failed={len(readiness.failed_required)}"
    )


def run_validation_profile_app(
    args: argparse.Namespace,
    app: TradingApplication | None = None,
    command_runner=None,
    artifact_exists=None,
    performance_evidence_factory=None,
) -> None:
    manifest = default_validation_manifest()
    profiles = {profile.name: profile for profile in default_validation_profiles(manifest)}
    profile_name = getattr(args, "validation_profile", "fast")
    if profile_name not in profiles:
        raise ValueError(f"Unknown validation profile '{profile_name}'. Available profiles: {', '.join(sorted(profiles))}.")
    profile = profiles[profile_name]
    selected_checks = profile.select_checks(manifest)
    if getattr(args, "consume_existing_evidence", False):
        evidence = tuple(
            ValidationEvidence(check.check_id, "skipped", reason="consume_existing_evidence")
            for check in selected_checks
        )
    else:
        evidence = execute_validation_profile(
            profile,
            manifest=manifest,
            command_runner=command_runner,
            artifact_exists=artifact_exists,
        )
    evidence = _merge_validation_evidence(
        selected_checks,
        evidence,
        _builtin_validation_evidence(
            selected_checks,
            args,
            app,
            performance_evidence_factory=performance_evidence_factory,
        ),
    )
    output = Path(getattr(args, "validation_profile_output", None) or profile.output_path)
    expected_artifacts = tuple(
        artifact
        for check in selected_checks
        for artifact in check.expected_artifacts
    )
    run_id = getattr(args, "validation_run_id", None) or _validation_run_id(profile.name)
    metadata = build_validation_run_metadata(
        run_id,
        config={
            "profile": profile.to_dict(),
            "selected_check_ids": [check.check_id for check in selected_checks],
        },
        artifact_paths=expected_artifacts,
        provider=getattr(args, "provider", ""),
        broker_mode=getattr(args, "execution_mode", None) or "dry-run",
    )
    write_validation_evidence_bundle(output, evidence, metadata)
    readiness = build_readiness_index(evidence, manifest=manifest, target=profile.target)
    freshness = evaluate_evidence_freshness(
        evidence,
        manifest=manifest,
        target=profile.target,
        max_age_hours=profile.max_age_hours,
    )
    action_plan = build_validation_action_plan(readiness, freshness)
    print(f"Validation profile evidence written: {output}")
    print(
        f"Profile={profile.name} target={profile.target} checks={len(selected_checks)} "
        f"passed={sum(1 for item in evidence if item.passed)} failed={sum(1 for item in evidence if item.status == 'failed')} "
        f"skipped={sum(1 for item in evidence if item.status == 'skipped')}"
    )
    print(
        f"Readiness score={readiness.readiness_score:.1%} missing={len(readiness.missing_required)} "
        f"failed={len(readiness.failed_required)} actions={len(action_plan.actions)}"
    )


def run_profile_app(app: TradingApplication, args: argparse.Namespace) -> None:
    data = app.load_data()
    output = Path(args.profiling_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    repeats = max(int(args.profiling_repeats), 1)
    store = JsonlStore(str(Path(args.store_dir) / "profile"))

    def strategy_generation():
        return app.create_strategy().generate_signals(data)

    def single_backtest():
        return app.run_backtest(data, app.create_strategy())

    def bulk_research():
        return run_bulk_backtests(
            symbols=("SPY", "QQQ"),
            strategies=(app.config.strategy.name,),
            data_loader=lambda _: data,
            strategy_params={app.config.strategy.name: dict(app.config.strategy.params)},
            config=BacktestConfig(),
        )

    def paper_session_planning():
        return run_autonomous_paper_session(
            app,
            AutonomousPaperSessionOptions(artifact_root=str(Path(args.store_dir) / "profile-paper-session")),
        )

    def broker_reconciliation():
        orders = [Order(id=f"order-{index}", symbol="SPY", side="BUY", quantity=1, status="FILLED") for index in range(10)]
        reports = [ExecutionReport(order_id=order.id, status="FILLED", broker_order_id=f"broker-{index}") for index, order in enumerate(orders)]
        return BrokerReconciler().reconcile_orders(orders, reports)

    tasks = (
        BenchmarkTask("indicator-calculation", lambda: data["Close"].rolling(20).mean().dropna(), category="indicator", repeats=repeats, warmups=1, metadata={"rows": len(data)}),
        BenchmarkTask("strategy-generation", strategy_generation, category="strategy_generation", repeats=repeats, warmups=1, metadata={"rows": len(data), "strategy": app.config.strategy.name}),
        BenchmarkTask("single-backtest", single_backtest, category="backtest_loop", repeats=repeats, metadata={"rows": len(data), "strategy": app.config.strategy.name}),
        BenchmarkTask("bulk-research", bulk_research, category="bulk_research", repeats=repeats, metadata={"symbols": 2, "strategy": app.config.strategy.name}),
        BenchmarkTask("storage-write", lambda: store.write_many("profiling-storage", [{"index": index, "value": index * 2} for index in range(25)]), category="storage_write", repeats=repeats),
        BenchmarkTask("paper-session-planning", paper_session_planning, category="paper_session_planning", repeats=repeats, metadata={"provider": app.config.data.provider}),
        BenchmarkTask("broker-reconciliation", broker_reconciliation, category="broker_reconciliation", repeats=repeats, metadata={"orders": 10}),
    )
    benchmark_report = run_benchmark_suite(tasks)
    budget_report = evaluate_performance_budgets(benchmark_report)
    payload = budget_report.to_dict()
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Profiling report written: {output}")
    print(
        f"Performance budgets passed={budget_report.passed} "
        f"slowest={benchmark_report.slowest.name if benchmark_report.slowest else 'n/a'} "
        f"total={benchmark_report.total_elapsed_seconds:.3f}s"
    )


def run_release_checklist_app(args: argparse.Namespace) -> None:
    checklist = default_release_checklist()
    paper_profiles = evaluate_paper_profile_validation()
    evidence_bundle = _optional_evidence_bundle(getattr(args, "evidence_dir", "reports/evidence"))
    evidence = list(evidence_bundle.latest_evidence())
    if paper_profiles.passed:
        evidence.append(
            ValidationEvidence(
                "paper_profile_validation",
                "passed",
                reason="paper_profiles_validated",
                metadata=paper_profiles.to_dict(),
            )
        )
        evidence.append(
            ValidationEvidence(
                "release_checklist_bundle",
                "passed",
                reason="release_checklist_generated",
                artifact_path=args.release_output,
            )
        )
    readiness = build_readiness_index(evidence, target="release_readiness")
    release_decision = build_release_decision_report(evidence, target="release_readiness")
    not_live_ready = build_not_live_ready_report(readiness)
    output = Path(args.release_output)
    readiness_html_output = Path(getattr(args, "readiness_html_output", "reports/readiness.html"))
    release_candidate_output = Path(getattr(args, "release_candidate_output", "reports/release-candidate-bundle.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    release_candidate_output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "release_checklist": checklist.to_dict(),
        "evidence_bundle": evidence_bundle.to_dict(),
        "paper_profile_validation": paper_profiles.to_dict(),
        "readiness_index": readiness.to_dict(),
        "release_decision": release_decision.to_dict(),
        "not_live_ready": not_live_ready.to_dict(),
        "readiness_html_path": str(readiness_html_output),
    }
    write_readiness_html_page(payload, readiness_html_output)
    schedule_report = _schedule_report_from_evidence(evidence_bundle)
    rehearsal_report = build_autonomous_paper_trading_rehearsal_report(
        evidence_bundle.to_dict(),
        schedule_report,
        release_decision.to_dict(),
        readiness_page_path=str(readiness_html_output),
        release_candidate_bundle=str(release_candidate_output),
    )
    live_unlock_blockers = _live_unlock_blocker_summary(evidence_bundle, not_live_ready.to_dict())
    payload["scheduled_paper_sessions"] = schedule_report
    payload["rehearsal_report"] = rehearsal_report.to_dict()
    payload["live_unlock_blockers"] = live_unlock_blockers
    release_candidate_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Release validation bundle written: {output}")
    print(f"Readiness HTML written: {readiness_html_output}")
    print(f"Release candidate bundle written: {release_candidate_output}")
    print(f"Release readiness score={readiness.readiness_score:.1%} live_ready={not_live_ready.live_ready}")


def run_release_rehearsal_app(
    args: argparse.Namespace,
    app: TradingApplication | None = None,
    command_runner=None,
    artifact_exists=None,
    performance_evidence_factory=None,
) -> None:
    evidence_dir = Path(getattr(args, "rehearsal_evidence_dir", None) or getattr(args, "evidence_dir", "reports/evidence/release-rehearsal"))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = getattr(args, "validation_run_id", None) or _validation_run_id("release-rehearsal")
    release_evidence = evidence_dir / "release-validation.json"
    paper_evidence = evidence_dir / "paper-dry-run-validation.json"

    run_validation_profile_app(
        _profile_namespace(args, "release", release_evidence, f"{run_id}-release"),
        app=app,
        command_runner=command_runner,
        artifact_exists=artifact_exists,
        performance_evidence_factory=performance_evidence_factory,
    )
    run_validation_profile_app(
        _profile_namespace(args, "paper-dry-run", paper_evidence, f"{run_id}-paper-dry-run"),
        app=app,
        command_runner=command_runner,
        artifact_exists=artifact_exists,
        performance_evidence_factory=performance_evidence_factory,
    )

    release_output = Path(getattr(args, "release_output", "reports/release-validation-bundle.json"))
    readiness_html_output = Path(getattr(args, "readiness_html_output", "reports/readiness.html"))
    release_candidate_output = Path(getattr(args, "release_candidate_output", "reports/release-candidate-bundle.json"))
    run_release_checklist_app(
        argparse.Namespace(
            release_output=str(release_output),
            evidence_dir=str(evidence_dir),
            readiness_html_output=str(readiness_html_output),
            release_candidate_output=str(release_candidate_output),
        )
    )

    candidate_payload = json.loads(release_candidate_output.read_text(encoding="utf-8"))
    summary = {
        "run_id": run_id,
        "evidence_dir": str(evidence_dir),
        "profile_evidence": {
            "release": str(release_evidence),
            "paper_dry_run": str(paper_evidence),
        },
        "release_output": str(release_output),
        "readiness_html_output": str(readiness_html_output),
        "release_candidate_output": str(release_candidate_output),
        "release_decision": candidate_payload.get("release_decision", {}),
        "scheduled_paper_sessions": candidate_payload.get("scheduled_paper_sessions", {}),
        "rehearsal_report": candidate_payload.get("rehearsal_report", {}),
        "not_live_ready": candidate_payload.get("not_live_ready", {}),
        "live_unlock_blockers": candidate_payload.get("live_unlock_blockers", {}),
    }
    summary_output = Path(getattr(args, "rehearsal_output", "reports/release-rehearsal-summary.json"))
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Release rehearsal summary written: {summary_output}")
    print(
        f"Release rehearsal decision={summary['release_decision'].get('decision')} "
        f"rehearsal_passed={summary['rehearsal_report'].get('passed')} "
        f"live_status={summary['not_live_ready'].get('status')}"
    )


def _profile_namespace(args: argparse.Namespace, profile: str, output: Path, run_id: str) -> argparse.Namespace:
    payload = dict(vars(args))
    payload.update(
        {
            "validation_profile": profile,
            "validation_profile_output": str(output),
            "validation_run_id": run_id,
        }
    )
    return argparse.Namespace(**payload)


def _paper_session_options(app: TradingApplication, args: argparse.Namespace) -> AutonomousPaperSessionOptions:
    if not args.paper_profile:
        return AutonomousPaperSessionOptions(
            submit_orders=args.submit_orders,
            artifact_root=args.store_dir,
            comparison_provider=args.comparison_provider,
            recover_state=args.recover_state,
            state_db_path=args.state_db_path,
            submission_approval_policy=_paper_broker_approval_policy(args),
            prior_broker_proof_reports=_load_prior_paper_proof_reports(getattr(args, "paper_proof_prior_dir", None)),
            fill_poll_attempts=getattr(args, "fill_poll_attempts", 1),
            fill_poll_interval_seconds=getattr(args, "fill_poll_interval_seconds", 0.0),
        )
    profile = alpaca_paper_soak_profiles()[args.paper_profile]
    if not getattr(args, "paper_profile_preview", False):
        validation = validate_alpaca_paper_soak_profile(profile, app.config)
        if validation.errors:
            raise ValueError("; ".join(validation.errors))
    options = profile.session_options(args.store_dir, state_db_path=args.state_db_path)
    return AutonomousPaperSessionOptions(
        submit_orders=False if getattr(args, "paper_profile_preview", False) else profile.submit_orders or args.submit_orders,
        artifact_root=options.artifact_root,
        comparison_provider=args.comparison_provider or options.comparison_provider,
        recover_state=args.recover_state or (options.recover_state and not getattr(args, "paper_profile_preview", False)),
        state_db_path=options.state_db_path,
        risk_budget=options.risk_budget,
        max_position_weight=options.max_position_weight,
        execution_policy=options.execution_policy,
        submission_approval_policy=_paper_broker_approval_policy(args),
        prior_broker_proof_reports=_load_prior_paper_proof_reports(getattr(args, "paper_proof_prior_dir", None)),
        fill_poll_attempts=getattr(args, "fill_poll_attempts", 1),
        fill_poll_interval_seconds=getattr(args, "fill_poll_interval_seconds", 0.0),
    )


def _paper_daemon_session_args(args: argparse.Namespace) -> argparse.Namespace:
    session_args = argparse.Namespace(**vars(args))
    if getattr(session_args, "paper_daemon_profile", None) and not getattr(session_args, "paper_profile", None):
        session_args.paper_profile = session_args.paper_daemon_profile
    return session_args


def _paper_daemon_options(args: argparse.Namespace) -> PaperTradingDaemonOptions:
    profile_name = getattr(args, "paper_daemon_profile", None) or getattr(args, "paper_profile", None)
    profile_options = None
    if profile_name:
        profile = alpaca_paper_soak_profiles()[profile_name]
        profile_options = profile.daemon_options(
            artifact_root=args.paper_daemon_artifact_root,
            schedule_output_path=args.paper_daemon_schedule_output,
            report_path=args.paper_daemon_report_output,
            state_path=args.paper_daemon_state_output,
            heartbeat_path=args.paper_daemon_heartbeat_output,
            kill_switch_path=args.paper_daemon_kill_switch,
            lock_path=args.paper_daemon_lock_path,
            cleanup_output_path=args.paper_daemon_cleanup_output,
            monitor_output_path=args.paper_daemon_monitor_output,
            data_parity_output_path=args.paper_daemon_data_parity_output,
            submit_orders=bool(
                (not getattr(args, "paper_profile_preview", False))
                and (profile.submit_orders or getattr(args, "submit_orders", False))
            ),
        )

    if profile_options is None:
        return PaperTradingDaemonOptions(
            interval_seconds=args.paper_daemon_interval_seconds,
            max_iterations=args.paper_daemon_max_iterations,
            kill_switch_path=args.paper_daemon_kill_switch,
            state_path=args.paper_daemon_state_output,
            heartbeat_path=args.paper_daemon_heartbeat_output,
            lock_path=args.paper_daemon_lock_path,
            lock_stale_after_seconds=args.paper_daemon_lock_stale_seconds,
            artifact_root=args.paper_daemon_artifact_root,
            schedule_output_path=args.paper_daemon_schedule_output,
            report_path=args.paper_daemon_report_output,
            cleanup_each_iteration=args.paper_daemon_cleanup_each_iteration,
            cleanup_submit_orders=args.paper_daemon_cleanup_submit,
            cleanup_output_path=args.paper_daemon_cleanup_output,
            monitor_each_iteration=args.paper_daemon_monitor_each_iteration,
            monitor_output_path=args.paper_daemon_monitor_output,
            monitor_max_open_order_age_minutes=args.paper_daemon_monitor_open_order_timeout_minutes,
            data_parity_each_iteration=args.paper_daemon_data_parity_each_iteration,
            data_parity_output_path=args.paper_daemon_data_parity_output,
            data_parity_max_close_drift_bps=args.paper_daemon_data_parity_max_close_drift_bps,
            submit_orders=args.submit_orders,
        )

    interval_seconds = (
        args.paper_daemon_interval_seconds
        if args.paper_daemon_interval_seconds != 300.0
        else profile_options.interval_seconds
    )
    data_parity_max_close_drift_bps = (
        args.paper_daemon_data_parity_max_close_drift_bps
        if args.paper_daemon_data_parity_max_close_drift_bps != 5.0
        else profile_options.data_parity_max_close_drift_bps
    )
    return PaperTradingDaemonOptions(
        interval_seconds=interval_seconds,
        max_iterations=args.paper_daemon_max_iterations or profile_options.max_iterations,
        kill_switch_path=args.paper_daemon_kill_switch,
        state_path=args.paper_daemon_state_output,
        heartbeat_path=args.paper_daemon_heartbeat_output,
        lock_path=args.paper_daemon_lock_path,
        lock_stale_after_seconds=args.paper_daemon_lock_stale_seconds,
        artifact_root=args.paper_daemon_artifact_root,
        schedule_output_path=args.paper_daemon_schedule_output,
        report_path=args.paper_daemon_report_output,
        cleanup_each_iteration=bool(args.paper_daemon_cleanup_each_iteration or profile_options.cleanup_each_iteration),
        cleanup_submit_orders=bool(args.paper_daemon_cleanup_submit),
        cleanup_output_path=args.paper_daemon_cleanup_output,
        monitor_each_iteration=bool(args.paper_daemon_monitor_each_iteration or profile_options.monitor_each_iteration),
        monitor_output_path=args.paper_daemon_monitor_output,
        monitor_max_open_order_age_minutes=args.paper_daemon_monitor_open_order_timeout_minutes,
        data_parity_each_iteration=bool(
            args.paper_daemon_data_parity_each_iteration or profile_options.data_parity_each_iteration
        ),
        data_parity_output_path=args.paper_daemon_data_parity_output,
        data_parity_max_close_drift_bps=data_parity_max_close_drift_bps,
        submit_orders=bool(profile_options.submit_orders or args.submit_orders),
    )


def _optional_evidence_bundle(path: str) -> ValidationEvidenceBundle:
    evidence_path = Path(path)
    if not evidence_path.exists():
        return ValidationEvidenceBundle(())
    return load_validation_evidence_bundle((evidence_path,))


def _schedule_report_from_evidence(evidence_bundle: ValidationEvidenceBundle) -> dict:
    for evidence in evidence_bundle.latest_evidence():
        if evidence.check_id in {"paper_session_schedule", "scheduled_paper_sessions"}:
            payload = dict(evidence.metadata)
            if "passed" not in payload:
                payload["passed"] = evidence.status == "passed"
            if "reason" not in payload:
                payload["reason"] = evidence.reason or evidence.status
            if evidence.artifact_path and "artifact_path" not in payload:
                payload["artifact_path"] = evidence.artifact_path
            return payload
    return {
        "passed": False,
        "reason": "missing_scheduled_paper_session_evidence",
        "required_evidence": ["paper_session_schedule", "scheduled_paper_sessions"],
    }


def _live_unlock_blocker_summary(evidence_bundle: ValidationEvidenceBundle, not_live_ready: dict) -> dict:
    hard_evidence = {}
    for evidence in evidence_bundle.latest_evidence():
        payload = dict(evidence.metadata)
        payload.setdefault("passed", evidence.status == "passed")
        if evidence.artifact_path:
            payload.setdefault("artifact_path", evidence.artifact_path)
        hard_evidence[evidence.check_id] = payload
    hard_gates = evaluate_hard_pre_live_upgrade_gates(hard_evidence)
    blocked = [probe.to_dict() for probe in hard_gates.probes if not probe.passed]
    return {
        "live_unlock_allowed": False,
        "status": "live_locked",
        "reason": "hard_pre_live_gates_require_real_artifact_backed_evidence",
        "not_live_ready": dict(not_live_ready),
        "hard_pre_live_upgrade_gates": hard_gates.to_dict(),
        "blocked_gate_names": [probe["name"] for probe in blocked],
        "blocked_gates": blocked,
    }


def _validation_run_id(profile_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{profile_name}-{stamp}"


def _merge_validation_evidence(checks, command_evidence, builtin_evidence) -> tuple[ValidationEvidence, ...]:
    evidence_by_id = {item.check_id: item for item in command_evidence}
    evidence_by_id.update({item.check_id: item for item in builtin_evidence})
    return tuple(evidence_by_id[check.check_id] for check in checks if check.check_id in evidence_by_id)


def _builtin_validation_evidence(
    checks,
    args: argparse.Namespace,
    app: TradingApplication | None,
    performance_evidence_factory=None,
) -> tuple[ValidationEvidence, ...]:
    check_ids = {check.check_id for check in checks}
    evidence: list[ValidationEvidence] = []
    if "paper_profile_validation" in check_ids:
        report = evaluate_paper_profile_validation()
        evidence.append(
            ValidationEvidence(
                "paper_profile_validation",
                "passed" if report.passed else "failed",
                reason="passed" if report.passed else "paper_profile_validation_failed",
                metadata=report.to_dict(),
            )
        )
    if "security_configuration" in check_ids:
        report = evaluate_security_config(
            _validation_runtime_config(args),
            {
                "ALPACA_API_KEY": os.getenv("ALPACA_API_KEY", ""),
                "ALPACA_SECRET_KEY": os.getenv("ALPACA_SECRET_KEY", ""),
            },
            committed_text="",
        )
        evidence.append(
            ValidationEvidence(
                "security_configuration",
                "passed" if report.passed else "failed",
                reason="passed" if report.passed else "security_configuration_failed",
                metadata=report.to_dict(),
            )
        )
    performance_ids = {budget.check_id for budget in default_performance_budgets()}
    selected_performance_ids = check_ids & performance_ids
    if selected_performance_ids:
        if performance_evidence_factory is None:
            evidence.extend(_performance_validation_evidence(selected_performance_ids, app))
        else:
            evidence.extend(performance_evidence_factory(selected_performance_ids, app))
    if "paper_soak_tiers" in check_ids:
        report = evaluate_paper_soak_tiers(_paper_soak_tier_fixture())
        evidence.append(
            ValidationEvidence(
                "paper_soak_tiers",
                "passed" if report.passed else "failed",
                reason="passed" if report.passed else "paper_soak_tier_acceptance_failed",
                metadata={"report": report.to_dict(), "fixture": _paper_soak_tier_fixture()},
            )
        )
    if "paper_session_schedule" in check_ids:
        schedule_artifact = getattr(args, "paper_session_schedule_output", "reports/paper-session-schedule.json")
        artifact_path = Path(schedule_artifact)
        if artifact_path.exists():
            evidence.append(_paper_session_schedule_evidence(str(artifact_path)))
        else:
            report = evaluate_paper_session_schedule(_paper_session_schedule_fixture())
            evidence.append(report.to_evidence("paper_session_schedule"))
    if "daily_ops_acceptance" in check_ids:
        fixture = _daily_ops_acceptance_fixture()
        report = evaluate_daily_ops_acceptance(fixture)
        evidence.append(
            ValidationEvidence(
                "daily_ops_acceptance",
                "passed" if report.passed else "failed",
                reason="passed" if report.passed else "daily_ops_acceptance_failed",
                metadata={"report": report.to_dict(), "fixture": fixture},
            )
        )
    if "observability_acceptance" in check_ids:
        fixture = _observability_acceptance_fixture()
        report = evaluate_observability_acceptance(
            fixture["metrics_snapshot"],
            fixture["health_statuses"],
            fixture["notification_events"],
            fixture["dashboard_snapshot"],
        )
        evidence.append(
            ValidationEvidence(
                "observability_acceptance",
                "passed" if report.passed else "failed",
                reason="passed" if report.passed else "observability_acceptance_failed",
                metadata={"report": report.to_dict(), "fixture": fixture},
            )
        )
    if "alpaca_paper_order_lifecycle" in check_ids:
        evidence.append(_paper_broker_proof_evidence(getattr(args, "paper_proof_output", "reports/alpaca-paper-broker-proof.json")))
    if "paper_broker_proof_schedule" in check_ids:
        evidence.append(_paper_broker_proof_schedule_evidence(getattr(args, "paper_proof_schedule_output", "reports/alpaca-paper-broker-proof-schedule.json")))
    if "broker_account_parity" in check_ids:
        evidence.append(_broker_account_parity_from_proof_evidence(getattr(args, "paper_proof_output", "reports/alpaca-paper-broker-proof.json")))
    if "paper_account_parity" in check_ids:
        evidence.append(_broker_account_parity_from_proof_evidence(getattr(args, "paper_proof_output", "reports/alpaca-paper-broker-proof.json"), check_id="paper_account_parity"))
    if "paper_account_cleanup" in check_ids:
        evidence.append(_paper_account_cleanup_evidence(getattr(args, "paper_cleanup_output", "reports/paper-cleanup-report.json")))
    if "real_alpaca_fill_polling" in check_ids:
        evidence.append(_real_alpaca_fill_polling_from_proof_evidence(getattr(args, "paper_proof_output", "reports/alpaca-paper-broker-proof.json")))
    if "failure_injection_suite" in check_ids:
        report = evaluate_failure_injection(_failure_injection_fixture())
        evidence.append(_report_evidence("failure_injection_suite", report, "failure_injection_suite_failed"))
    if "data_quality_torture" in check_ids:
        torture = evaluate_data_quality_torture()
        calendar = evaluate_calendar_torture()
        passed = torture.passed and calendar.passed
        evidence.append(
            ValidationEvidence(
                "data_quality_torture",
                "passed" if passed else "failed",
                reason="passed" if passed else "data_quality_torture_failed",
                metadata={"torture_report": torture.to_dict(), "calendar_report": calendar.to_dict()},
            )
        )
    if "backtester_differential" in check_ids:
        report = evaluate_backtest_differential(_backtest_differential_fixture())
        evidence.append(_report_evidence("backtester_differential", report, "backtester_differential_failed"))
    if "optimizer_validation" in check_ids:
        report = evaluate_optimizer_validation(_optimizer_validation_fixture())
        evidence.append(_report_evidence("optimizer_validation", report, "optimizer_validation_failed"))
    if "deployment_rehearsal" in check_ids:
        fixture = _deployment_rehearsal_fixture()
        report = evaluate_deployment_rehearsal(
            fixture["evidence_by_profile"],
            profiles=(local_windows_task_profile(), docker_profile(), small_server_profile()),
        )
        evidence.append(
            ValidationEvidence(
                "deployment_rehearsal",
                "passed" if report.passed else "failed",
                reason="passed" if report.passed else "deployment_rehearsal_failed",
                metadata={"report": report.to_dict(), "fixture": fixture},
            )
        )
    if "golden_artifacts" in check_ids:
        report = evaluate_golden_artifacts(_golden_artifact_fixture())
        evidence.append(_report_evidence("golden_artifacts", report, "golden_artifact_validation_failed"))
    if "release_checklist_bundle" in check_ids:
        checklist = default_release_checklist()
        evidence.append(
            ValidationEvidence(
                "release_checklist_bundle",
                "passed",
                artifact_path=checklist.output_bundle,
                reason="passed",
                metadata={"release_checklist": checklist.to_dict()},
            )
        )
    return tuple(evidence)


def _paper_broker_proof_evidence(path: str) -> ValidationEvidence:
    artifact = Path(path)
    if not artifact.exists():
        return ValidationEvidence(
            "alpaca_paper_order_lifecycle",
            "missing",
            artifact_path=str(artifact),
            reason="paper_broker_proof_artifact_missing",
        )
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception as exc:
        return ValidationEvidence(
            "alpaca_paper_order_lifecycle",
            "failed",
            artifact_path=str(artifact),
            reason="paper_broker_proof_artifact_invalid",
            metadata={"error": str(exc)},
        )
    passed = bool(payload.get("passed")) and bool(payload.get("submit_allowed")) and bool(payload.get("submitted"))
    return ValidationEvidence(
        "alpaca_paper_order_lifecycle",
        "passed" if passed else "failed",
        artifact_path=str(artifact),
        reason="passed" if passed else str(payload.get("reason") or "paper_broker_proof_failed"),
        metadata={"paper_broker_proof": payload},
    )


def _paper_broker_proof_schedule_evidence(path: str) -> ValidationEvidence:
    artifact = Path(path)
    if not artifact.exists():
        return ValidationEvidence(
            "paper_broker_proof_schedule",
            "missing",
            artifact_path=str(artifact),
            reason="paper_broker_proof_schedule_artifact_missing",
        )
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception as exc:
        return ValidationEvidence(
            "paper_broker_proof_schedule",
            "failed",
            artifact_path=str(artifact),
            reason="paper_broker_proof_schedule_artifact_invalid",
            metadata={"error": str(exc)},
        )
    passed = bool(payload.get("passed"))
    return ValidationEvidence(
        "paper_broker_proof_schedule",
        "passed" if passed else "failed",
        artifact_path=str(artifact),
        reason="passed" if passed else _artifact_reason(payload, "paper_broker_proof_schedule_failed"),
        metadata={"paper_broker_proof_schedule": payload},
    )


def _paper_session_schedule_evidence(path: str) -> ValidationEvidence:
    artifact = Path(path)
    if not artifact.exists():
        return ValidationEvidence(
            "paper_session_schedule",
            "missing",
            artifact_path=str(artifact),
            reason="paper_session_schedule_artifact_missing",
        )
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception as exc:
        return ValidationEvidence(
            "paper_session_schedule",
            "failed",
            artifact_path=str(artifact),
            reason="paper_session_schedule_artifact_invalid",
            metadata={"error": str(exc)},
        )
    passed = bool(payload.get("passed"))
    return ValidationEvidence(
        "paper_session_schedule",
        "passed" if passed else "failed",
        artifact_path=str(artifact),
        reason="passed" if passed else _artifact_reason(payload, "paper_session_schedule_failed"),
        metadata=payload,
    )


def _paper_account_cleanup_evidence(path: str) -> ValidationEvidence:
    artifact = Path(path)
    if not artifact.exists():
        return ValidationEvidence(
            "paper_account_cleanup",
            "missing",
            artifact_path=str(artifact),
            reason="paper_cleanup_artifact_missing",
        )
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception as exc:
        return ValidationEvidence(
            "paper_account_cleanup",
            "failed",
            artifact_path=str(artifact),
            reason="paper_cleanup_artifact_invalid",
            metadata={"error": str(exc)},
        )
    positions = tuple(payload.get("positions_seen") or ())
    planned_orders = tuple(payload.get("planned_orders") or ())
    submitted = bool(payload.get("submitted"))
    reconciliation_clean = payload.get("reconciliation_clean")
    flat_before_cleanup = len(positions) == 0
    flattened_cleanly = submitted and reconciliation_clean is True
    passed = flat_before_cleanup or flattened_cleanly
    return ValidationEvidence(
        "paper_account_cleanup",
        "passed" if passed else "failed",
        artifact_path=str(artifact),
        reason="passed" if passed else _paper_cleanup_reason(payload, positions, planned_orders),
        metadata={
            "paper_cleanup_artifact": str(artifact),
            "submit_requested": bool(payload.get("submit_requested")),
            "attempted": bool(payload.get("attempted")),
            "submitted": submitted,
            "reconciliation_clean": reconciliation_clean,
            "positions_seen": len(positions),
            "planned_orders": len(planned_orders),
            "submitted_orders": len(payload.get("submitted_orders") or ()),
            "polled_execution_reports": int(payload.get("polled_execution_reports") or 0),
            "position_summary": _paper_cleanup_position_summary(positions),
            "guard_reason": dict(payload.get("submission_guard") or {}).get("reason"),
        },
    )


def _paper_cleanup_reason(payload: dict, positions: tuple, planned_orders: tuple) -> str:
    if not positions:
        return "passed"
    if not planned_orders:
        return "paper_cleanup_no_flatten_orders"
    if payload.get("reason"):
        return str(payload["reason"])
    if payload.get("submit_requested") and not payload.get("submitted"):
        return "paper_cleanup_not_submitted"
    if payload.get("submitted") and payload.get("reconciliation_clean") is not True:
        return "paper_cleanup_reconciliation_not_clean"
    return "paper_cleanup_required"


def _paper_cleanup_position_summary(positions: tuple) -> list[dict]:
    return [
        {
            "symbol": position.get("symbol"),
            "quantity": position.get("quantity"),
            "market_value": position.get("market_value"),
        }
        for position in positions
        if isinstance(position, Mapping)
    ]


def _broker_account_parity_from_proof_evidence(path: str, check_id: str = "broker_account_parity") -> ValidationEvidence:
    artifact = Path(path)
    if not artifact.exists():
        return ValidationEvidence(
            check_id,
            "missing",
            artifact_path=str(artifact),
            reason="paper_broker_proof_artifact_missing",
        )
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception as exc:
        return ValidationEvidence(
            check_id,
            "failed",
            artifact_path=str(artifact),
            reason="paper_broker_proof_artifact_invalid",
            metadata={"error": str(exc)},
        )
    pre_account = payload.get("account_snapshot")
    post_account = payload.get("post_account_snapshot")
    submitted = bool(payload.get("submitted"))
    cleanup_ok = not payload.get("open_orders_after")
    account_ok = bool(pre_account) and bool(post_account) and not bool(post_account.get("account_blocked")) and not bool(post_account.get("trading_blocked"))
    passed = submitted and account_ok and cleanup_ok
    return ValidationEvidence(
        check_id,
        "passed" if passed else "failed",
        artifact_path=str(artifact),
        reason="passed" if passed else _broker_account_parity_reason(payload, pre_account, post_account, cleanup_ok),
        metadata={
            "paper_broker_proof_artifact": str(artifact),
            "submitted": submitted,
            "pre_account": pre_account,
            "post_account": post_account,
            "positions_before": payload.get("positions_before", []),
            "positions_after": payload.get("positions_after", []),
            "open_orders_before": payload.get("open_orders_before", []),
            "open_orders_after": payload.get("open_orders_after", []),
            "polled_execution_reports": payload.get("polled_execution_reports", []),
        },
    )


def _real_alpaca_fill_polling_from_proof_evidence(path: str) -> ValidationEvidence:
    artifact = Path(path)
    if not artifact.exists():
        return ValidationEvidence(
            "real_alpaca_fill_polling",
            "missing",
            artifact_path=str(artifact),
            reason="paper_broker_proof_artifact_missing",
        )
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception as exc:
        return ValidationEvidence(
            "real_alpaca_fill_polling",
            "failed",
            artifact_path=str(artifact),
            reason="paper_broker_proof_artifact_invalid",
            metadata={"error": str(exc)},
        )
    polling_probe = _probe_by_name(payload, "fill_polling_completed")
    polling_source = dict(polling_probe.get("evidence", {})).get("source") if polling_probe else None
    polled_reports = payload.get("polled_execution_reports", [])
    submitted = bool(payload.get("submitted"))
    passed = submitted and polling_source == "broker_poll_execution_reports" and bool(polled_reports)
    return ValidationEvidence(
        "real_alpaca_fill_polling",
        "passed" if passed else "failed",
        artifact_path=str(artifact),
        reason="passed" if passed else _real_fill_polling_reason(payload, polling_source, polled_reports),
        metadata={
            "paper_broker_proof_artifact": str(artifact),
            "submitted": submitted,
            "polling_source": polling_source,
            "polled_execution_reports": polled_reports,
            "polling_probe": polling_probe,
        },
    )


def _probe_by_name(payload: dict, name: str) -> dict | None:
    for probe in payload.get("probes", []):
        if probe.get("name") == name:
            return dict(probe)
    return None


def _real_fill_polling_reason(payload: dict, polling_source: str | None, polled_reports: list) -> str:
    if not payload.get("submitted"):
        return "paper_broker_proof_not_submitted"
    if polling_source != "broker_poll_execution_reports":
        return "real_fill_polling_not_used"
    if not polled_reports:
        return "missing_polled_execution_reports"
    return "real_alpaca_fill_polling_failed"


def _artifact_reason(payload: dict, fallback: str) -> str:
    if payload.get("reason"):
        return str(payload["reason"])
    for check in payload.get("checks", []):
        if not check.get("passed"):
            return str(check.get("reason") or fallback)
    return fallback


def _broker_account_parity_reason(payload: dict, pre_account, post_account, cleanup_ok: bool) -> str:
    if not payload.get("submitted"):
        return "paper_broker_proof_not_submitted"
    if not pre_account:
        return "missing_pre_account_snapshot"
    if not post_account:
        return "missing_post_account_snapshot"
    if post_account.get("account_blocked") or post_account.get("trading_blocked"):
        return "broker_account_blocked"
    if not cleanup_ok:
        return "open_orders_after_proof"
    return "broker_account_parity_failed"


def _validation_runtime_config(args: argparse.Namespace):
    return load_runtime_config(
        {
            "symbol": getattr(args, "symbol", "SPY"),
            "provider": getattr(args, "provider", "sample"),
            "period": getattr(args, "period", "2y"),
            "interval": getattr(args, "interval", "1d"),
            "start": getattr(args, "start", None),
            "end": getattr(args, "end", None),
            "strategy": getattr(args, "strategy", "buyHold"),
            "strategy_params": load_json_options(
                getattr(args, "strategy_params", "{}"),
                getattr(args, "strategy_params_file", None),
            ),
            "execution_mode": getattr(args, "execution_mode", None),
        }
    )


def _performance_validation_evidence(check_ids: set[str], app: TradingApplication | None) -> tuple[ValidationEvidence, ...]:
    budgets = tuple(budget for budget in default_performance_budgets() if budget.check_id in check_ids)
    benchmark_names = {budget.benchmark_name for budget in budgets}
    benchmark_config = {
        "provider": "sample",
        "symbol": getattr(app.config.data, "symbol", "SPY") if app else "SPY",
        "strategy": getattr(app.config.strategy, "name", "buyHold") if app else "buyHold",
        "strategy_params": dict(getattr(app.config.strategy, "params", {})) if app else {},
    }
    benchmark_app = TradingApplication(load_runtime_config(benchmark_config))
    data_cache = {}

    def data():
        if "data" not in data_cache:
            data_cache["data"] = benchmark_app.load_data()
        return data_cache["data"]

    task_builders = {
        "indicator-calculation": lambda: BenchmarkTask(
            "indicator-calculation",
            lambda: data()["Close"].rolling(20).mean().dropna(),
            category="indicator",
            repeats=1,
            warmups=1,
            metadata={"rows": len(data())},
        ),
        "strategy-generation": lambda: BenchmarkTask(
            "strategy-generation",
            lambda: benchmark_app.create_strategy().generate_signals(data()),
            category="strategy_generation",
            repeats=1,
            metadata={"rows": len(data()), "strategy": benchmark_app.config.strategy.name},
        ),
        "single-backtest": lambda: BenchmarkTask(
            "single-backtest",
            lambda: benchmark_app.run_backtest(data(), benchmark_app.create_strategy()),
            category="backtest_loop",
            repeats=1,
            metadata={"rows": len(data()), "strategy": benchmark_app.config.strategy.name},
        ),
        "bulk-research": lambda: BenchmarkTask(
            "bulk-research",
            lambda: run_bulk_backtests(
                symbols=("SPY", "QQQ"),
                strategies=(benchmark_app.config.strategy.name,),
                data_loader=lambda _: data(),
                strategy_params={benchmark_app.config.strategy.name: dict(benchmark_app.config.strategy.params)},
                config=BacktestConfig(),
            ),
            category="bulk_research",
            repeats=1,
            metadata={"symbols": 2, "strategy": benchmark_app.config.strategy.name},
        ),
        "storage-write": lambda: BenchmarkTask(
            "storage-write",
            lambda: JsonlStore("runs/validation-profile-storage").write_many(
                "profiling-storage",
                [{"index": index, "value": index * 2} for index in range(25)],
            ),
            category="storage_write",
            repeats=1,
        ),
        "paper-session-planning": lambda: BenchmarkTask(
            "paper-session-planning",
            lambda: run_autonomous_paper_session(
                benchmark_app,
                AutonomousPaperSessionOptions(artifact_root="runs/validation-profile-paper-session"),
            ),
            category="paper_session_planning",
            repeats=1,
            metadata={"provider": benchmark_app.config.data.provider},
        ),
        "broker-reconciliation": lambda: BenchmarkTask(
            "broker-reconciliation",
            lambda: BrokerReconciler().reconcile_orders(
                [Order(id=f"order-{index}", symbol="SPY", side="BUY", quantity=1, status="FILLED") for index in range(10)],
                [ExecutionReport(order_id=f"order-{index}", status="FILLED", broker_order_id=f"broker-{index}") for index in range(10)],
            ),
            category="broker_reconciliation",
            repeats=1,
            metadata={"orders": 10},
        ),
    }
    tasks = [task_builders[name]() for name in benchmark_names if name in task_builders]
    report = evaluate_performance_budgets(run_benchmark_suite(tasks), budgets=budgets)
    return report.evidence


def _report_evidence(check_id: str, report, failed_reason: str) -> ValidationEvidence:
    return ValidationEvidence(
        check_id,
        "passed" if report.passed else "failed",
        reason="passed" if report.passed else failed_reason,
        metadata={"report": report.to_dict()},
    )


def _failure_injection_fixture() -> tuple[FailureInjectionScenario, ...]:
    return (
        FailureInjectionScenario("rate_limit_response", lambda: _raise_validation_fixture(RuntimeError("429 rate limit")), RuntimeError, "429"),
        FailureInjectionScenario("broker_timeout", lambda: _raise_validation_fixture(TimeoutError("broker timeout")), TimeoutError, "timeout"),
        FailureInjectionScenario("malformed_payload", lambda: _raise_validation_fixture(ValueError("malformed payload")), ValueError, "malformed"),
    )


def _raise_validation_fixture(exc: BaseException) -> None:
    raise exc


def _backtest_differential_fixture() -> tuple[BacktestDifferentialScenario, ...]:
    reference = {"total_return": 0.05, "ending_equity": 105_000.0, "fills": 2}
    return (
        BacktestDifferentialScenario(
            "buy_hold_reference_fixture",
            observed=dict(reference),
            reference=reference,
            tolerances={"total_return": 0.0001, "ending_equity": 0.01},
        ),
    )


def _optimizer_validation_fixture() -> tuple[OptimizerValidationCase, ...]:
    return (
        OptimizerValidationCase(
            "seeded_walk_forward_fixture",
            seeded_reproducible=True,
            train_test_separated=True,
            no_lookahead_detected=True,
            persistence_reloaded=True,
            failed_trials_handled=True,
            objective_metric_correct=True,
            evidence={"optimizer_backend": "fixture", "trial_count": 3},
        ),
    )


def _deployment_rehearsal_fixture() -> dict:
    checks = {
        "startup": True,
        "graceful_stop": True,
        "watchdog_timeout": True,
        "log_rotation": True,
        "artifact_persistence": True,
        "state_db_persistence": True,
        "restart_recovery": True,
    }
    return {
        "evidence_by_profile": {
            "windows-task": dict(checks),
            "docker": dict(checks),
            "small-server": dict(checks),
        }
    }


def _golden_artifact_fixture() -> tuple[GoldenArtifactCase, ...]:
    readiness_summary = {
        "decision": "blocked_until_evidence_complete",
        "readiness_score": 0.25,
        "missing_checks": 9,
    }
    paper_summary = {
        "sessions": 3,
        "submitted_orders": 0,
        "warnings": [],
    }
    return (
        GoldenArtifactCase("readiness_summary_fixture", observed=readiness_summary, expected=dict(readiness_summary)),
        GoldenArtifactCase("paper_summary_fixture", observed=paper_summary, expected=dict(paper_summary)),
    )


def _paper_soak_tier_fixture() -> dict:
    return {
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


def _paper_session_schedule_fixture() -> tuple[ScheduledPaperSessionRecord, ...]:
    ready = {"ready_for_submission": True, "warnings": (), "submitted": False}
    return (
        ScheduledPaperSessionRecord("pre_market", datetime(2026, 7, 15, 8, 15, tzinfo=timezone.utc), ready),
        ScheduledPaperSessionRecord("market_open", datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc), ready),
        ScheduledPaperSessionRecord("intraday", datetime(2026, 7, 15, 11, 0, tzinfo=timezone.utc), ready),
        ScheduledPaperSessionRecord("market_close", datetime(2026, 7, 15, 15, 0, tzinfo=timezone.utc), ready),
        ScheduledPaperSessionRecord("end_of_day", datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc), ready),
    )


def _daily_ops_acceptance_fixture() -> dict:
    return {
        "summary": {"promotion_enabled": 0, "sessions": 3, "submitted_orders": 0},
        "recommendations": ["Continue dry-run evidence collection before broker-backed submission."],
        "reconciliation": {"unresolved_sessions": 0},
        "fills": {"missed_or_unsubmitted_sessions": 0},
        "scorecards": {"passed": 3, "failed": 0},
        "promotion_queue": {},
        "warnings": [],
    }


def _observability_acceptance_fixture() -> dict:
    return {
        "metrics_snapshot": {
            "counters": {"orders": 0, "paper_sessions": 3},
            "gauges": {"equity": 100_000.0},
            "timings": {"paper_session_seconds": 1.0},
        },
        "health_statuses": [{"name": "data", "healthy": True}, {"name": "execution", "healthy": True}],
        "notification_events": [
            {"topic": "startup", "severity": "INFO"},
            {"topic": "halt", "severity": "CRITICAL"},
        ],
        "dashboard_snapshot": {
            "account": {"equity": 100_000.0},
            "risk_halt": {"halted": True, "reason": "operator validation fixture"},
        },
    }


def _paper_soak_config(args: argparse.Namespace) -> PaperSessionSoakConfig:
    if not args.paper_profile:
        return PaperSessionSoakConfig(
            sessions=args.soak_sessions or 3,
            min_clean_streak_for_promotion=getattr(args, "paper_soak_min_clean_streak", 10),
            operator_acknowledged_failure=getattr(args, "paper_soak_acknowledge_failure", False),
            operator_failure_action=getattr(args, "paper_soak_operator_action", None),
        )
    profile_config = alpaca_paper_soak_profiles()[args.paper_profile].soak_config()
    return PaperSessionSoakConfig(
        sessions=args.soak_sessions or profile_config.sessions,
        require_ready=profile_config.require_ready,
        require_no_warnings=profile_config.require_no_warnings,
        require_artifacts=profile_config.require_artifacts,
        require_reconciliation_when_submitted=profile_config.require_reconciliation_when_submitted,
        require_scorecard_when_submitted=profile_config.require_scorecard_when_submitted,
        stop_on_failure=profile_config.stop_on_failure,
        min_clean_streak_for_promotion=getattr(args, "paper_soak_min_clean_streak", 10),
        operator_acknowledged_failure=getattr(args, "paper_soak_acknowledge_failure", False),
        operator_failure_action=getattr(args, "paper_soak_operator_action", None),
    )


def _camel_to_snake(value: str) -> str:
    output = []
    for char in value:
        if char.isupper() and output:
            output.append("_")
        output.append(char.lower())
    return "".join(output)


def _format_optional_pct(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.2f}%"


def _format_optional_value(value: object) -> str:
    return "n/a" if value is None else str(value)


def default_timeout_seconds(mode: str) -> float:
    if mode in {"optimize", "bulk", "matrix", "replicate", "profile", "validate-profile", "release-rehearsal"}:
        return 900.0
    if mode == "paper-daemon":
        return 86_400.0
    if mode in {"stream", "paper", "paper-session", "paper-session-schedule", "paper-broker-proof", "paper-broker-schedule", "paper-cleanup", "paper-monitor", "paper-pilot", "paper-daemon-stop", "paper-daemon-clear-stop", "paper-daemon-status", "paper-daemon-ops", "paper-command-center", "paper-activation-report", "paper-soak", "paper-portfolio"}:
        return 300.0
    return 180.0


def run_selected_mode(app: TradingApplication, args: argparse.Namespace) -> None:
    if args.mode == "validate":
        run_validate_app(args)
    elif args.mode == "validate-profile":
        run_validation_profile_app(args, app=app)
    elif args.mode == "profile":
        run_profile_app(app, args)
    elif args.mode == "release-checklist":
        run_release_checklist_app(args)
    elif args.mode == "release-rehearsal":
        run_release_rehearsal_app(args, app=app)
    elif args.mode == "stream":
        run_stream_app(app, store_dir=args.store_dir, label="Stream", flatten_on_stop=args.flatten_on_stop)
    elif args.mode == "paper":
        run_stream_app(app, store_dir=args.store_dir, label="Paper", flatten_on_stop=args.flatten_on_stop)
    elif args.mode == "paper-session":
        run_paper_session_app(app, args)
    elif args.mode == "paper-session-schedule":
        run_paper_session_schedule_app(app, args)
    elif args.mode == "paper-broker-proof":
        run_paper_broker_proof_app(app, args)
    elif args.mode == "paper-broker-schedule":
        run_paper_broker_schedule_app(app, args)
    elif args.mode == "paper-cleanup":
        run_paper_cleanup_app(app, args)
    elif args.mode == "paper-monitor":
        run_paper_monitor_app(app, args)
    elif args.mode == "paper-pilot":
        run_paper_pilot_app(app, args)
    elif args.mode == "paper-daemon":
        run_paper_daemon_app(app, args)
    elif args.mode == "paper-daemon-stop":
        run_paper_daemon_stop_app(args)
    elif args.mode == "paper-daemon-clear-stop":
        run_paper_daemon_clear_stop_app(args)
    elif args.mode == "paper-daemon-status":
        run_paper_daemon_status_app(args)
    elif args.mode == "paper-daemon-ops":
        run_paper_daemon_ops_app(args)
    elif args.mode == "paper-command-center":
        run_paper_command_center_app(args)
    elif args.mode == "paper-activation-report":
        run_paper_activation_report_app(args)
    elif args.mode == "paper-soak":
        run_paper_soak_app(app, args)
    elif args.mode == "paper-portfolio":
        run_paper_portfolio_app(app, args)
    elif args.mode == "report":
        run_report_app(app, args.html_output)
    elif args.mode == "optimize":
        run_optimize_app(app, args.param_grid, args.metric, store_dir=args.store_dir, param_grid_file=args.param_grid_file)
    elif args.mode == "bulk":
        run_bulk_backtest_app(args)
    elif args.mode == "matrix":
        run_research_matrix_app(args)
    elif args.mode == "replicate":
        run_replication_app(args)
    else:
        run_backtest_app(app, show_plot=args.plot, output=args.output, store_dir=args.store_dir)


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    timeout_seconds = args.timeout_seconds or default_timeout_seconds(args.mode)
    app = TradingApplication(build_config(args))
    with RuntimeWatchdog(RuntimeTimeoutPolicy(timeout_seconds)) as watchdog:
        try:
            run_selected_mode(app, args)
        except KeyboardInterrupt as exc:
            if watchdog.triggered:
                print(f"Runtime timed out after {timeout_seconds:.0f}s.", file=sys.stderr)
                raise SystemExit(TIMEOUT_EXIT_CODE)
            raise


if __name__ == "__main__":
    main()
