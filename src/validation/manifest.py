from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from src.config import AlpacaConfig, ExecutionConfig, MarketDataConfig, RuntimeConfig
from src.operations import alpaca_paper_soak_profiles, validate_alpaca_paper_soak_profile

from src.utils.acceleration import AccelerationPlan, build_acceleration_plan
from src.utils.profiling import BenchmarkSuiteReport


VALIDATION_STATUSES = {"passed", "failed", "missing", "skipped"}


@dataclass(frozen=True)
class ValidationCheckSpec:
    check_id: str
    category: str
    subsystem: str
    description: str
    command: str | None = None
    required_for: tuple[str, ...] = ("paper_readiness",)
    threshold: Mapping[str, Any] = field(default_factory=dict)
    expected_artifacts: tuple[str, ...] = ()
    timeout_seconds: float | None = None

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "subsystem": self.subsystem,
            "description": self.description,
            "command": self.command,
            "required_for": list(self.required_for),
            "threshold": dict(self.threshold),
            "expected_artifacts": list(self.expected_artifacts),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class ValidationEvidence:
    check_id: str
    status: str
    artifact_path: str | None = None
    elapsed_seconds: float | None = None
    reason: str = ""
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def __post_init__(self) -> None:
        if self.status not in VALIDATION_STATUSES:
            raise ValueError(f"Validation status must be one of {sorted(VALIDATION_STATUSES)}.")

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "passed": self.passed,
            "artifact_path": self.artifact_path,
            "elapsed_seconds": self.elapsed_seconds,
            "reason": self.reason,
            "captured_at": self.captured_at.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ValidationManifest:
    checks: tuple[ValidationCheckSpec, ...]
    name: str = "tradingbot-validation-manifest"
    version: str = "1"

    def by_id(self) -> dict[str, ValidationCheckSpec]:
        return {check.check_id: check for check in self.checks}

    def required_checks(self, target: str) -> tuple[ValidationCheckSpec, ...]:
        return tuple(check for check in self.checks if target in check.required_for)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class ValidationProfile:
    name: str
    target: str
    check_ids: tuple[str, ...]
    max_age_hours: float = 24.0
    output_path: str = "reports/evidence/validation-evidence.json"
    description: str = ""

    def select_checks(self, manifest: ValidationManifest) -> tuple[ValidationCheckSpec, ...]:
        checks_by_id = manifest.by_id()
        return tuple(checks_by_id[check_id] for check_id in self.check_ids if check_id in checks_by_id)

    def missing_check_ids(self, manifest: ValidationManifest) -> tuple[str, ...]:
        checks_by_id = manifest.by_id()
        return tuple(check_id for check_id in self.check_ids if check_id not in checks_by_id)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target": self.target,
            "check_ids": list(self.check_ids),
            "max_age_hours": self.max_age_hours,
            "output_path": self.output_path,
            "description": self.description,
        }


@dataclass(frozen=True)
class ValidationReadinessIndex:
    manifest: ValidationManifest
    evidence: tuple[ValidationEvidence, ...] = ()
    target: str = "paper_readiness"

    @property
    def evidence_by_id(self) -> dict[str, ValidationEvidence]:
        return {item.check_id: item for item in self.evidence}

    @property
    def required_checks(self) -> tuple[ValidationCheckSpec, ...]:
        return self.manifest.required_checks(self.target)

    @property
    def passed_required(self) -> int:
        evidence = self.evidence_by_id
        return sum(1 for check in self.required_checks if evidence.get(check.check_id, _missing(check)).passed)

    @property
    def missing_required(self) -> tuple[ValidationCheckSpec, ...]:
        evidence = self.evidence_by_id
        return tuple(
            check
            for check in self.required_checks
            if evidence.get(check.check_id, _missing(check)).status == "missing"
        )

    @property
    def failed_required(self) -> tuple[ValidationCheckSpec, ...]:
        evidence = self.evidence_by_id
        return tuple(
            check
            for check in self.required_checks
            if evidence.get(check.check_id, _missing(check)).status == "failed"
        )

    @property
    def passed(self) -> bool:
        return self.passed_required == len(self.required_checks)

    @property
    def readiness_score(self) -> float:
        required = len(self.required_checks)
        return self.passed_required / required if required else 1.0

    def to_dict(self) -> dict:
        evidence = self.evidence_by_id
        return {
            "target": self.target,
            "passed": self.passed,
            "readiness_score": self.readiness_score,
            "required_checks": len(self.required_checks),
            "passed_required": self.passed_required,
            "missing_required": [check.check_id for check in self.missing_required],
            "failed_required": [check.check_id for check in self.failed_required],
            "checks": [
                {
                    "spec": check.to_dict(),
                    "evidence": evidence.get(check.check_id, _missing(check)).to_dict(),
                }
                for check in self.required_checks
            ],
        }


@dataclass(frozen=True)
class CliSmokeSpec:
    mode: str
    command: str
    expected_exit_code: int = 0
    expected_artifacts: tuple[str, ...] = ()
    timeout_seconds: float = 60.0

    @property
    def check_id(self) -> str:
        return f"cli_smoke_{self.mode.replace('-', '_')}"

    def to_check_spec(self) -> ValidationCheckSpec:
        return ValidationCheckSpec(
            check_id=self.check_id,
            category="cli_smoke",
            subsystem="cli",
            description=f"CLI smoke test for `{self.mode}` mode.",
            command=self.command,
            threshold={"expected_exit_code": self.expected_exit_code},
            expected_artifacts=self.expected_artifacts,
            timeout_seconds=self.timeout_seconds,
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "check_id": self.check_id,
            "command": self.command,
            "expected_exit_code": self.expected_exit_code,
            "expected_artifacts": list(self.expected_artifacts),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class PerformanceBudget:
    check_id: str
    benchmark_name: str
    category: str
    max_mean_seconds: float
    max_total_seconds: float | None = None

    def to_check_spec(self) -> ValidationCheckSpec:
        return ValidationCheckSpec(
            check_id=self.check_id,
            category="performance_budget",
            subsystem=self.category,
            description=f"Performance budget for benchmark `{self.benchmark_name}`.",
            threshold={
                "max_mean_seconds": self.max_mean_seconds,
                "max_total_seconds": self.max_total_seconds,
            },
            required_for=("paper_readiness", "optimization_readiness"),
        )

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "benchmark_name": self.benchmark_name,
            "category": self.category,
            "max_mean_seconds": self.max_mean_seconds,
            "max_total_seconds": self.max_total_seconds,
        }


@dataclass(frozen=True)
class PerformanceBudgetReport:
    budgets: tuple[PerformanceBudget, ...]
    benchmark_report: BenchmarkSuiteReport
    acceleration_plan: AccelerationPlan
    evidence: tuple[ValidationEvidence, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.evidence)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "budgets": [budget.to_dict() for budget in self.budgets],
            "benchmark_report": self.benchmark_report.to_dict(),
            "acceleration_plan": self.acceleration_plan.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class PaperProfileValidationReport:
    profile_results: Mapping[str, Mapping[str, Any]]
    unsafe_combination_results: Mapping[str, Mapping[str, Any]]

    @property
    def passed(self) -> bool:
        return all(result["passed"] for result in self.profile_results.values()) and all(
            result["blocked"] for result in self.unsafe_combination_results.values()
        )

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "profile_results": {name: dict(result) for name, result in self.profile_results.items()},
            "unsafe_combination_results": {name: dict(result) for name, result in self.unsafe_combination_results.items()},
        }


@dataclass(frozen=True)
class ReleaseChecklistStep:
    name: str
    command: str | None
    required: bool = True
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "required": self.required,
            "description": self.description,
        }


@dataclass(frozen=True)
class ReleaseChecklist:
    steps: tuple[ReleaseChecklistStep, ...]
    output_bundle: str = "reports/release-validation-bundle.json"

    def to_dict(self) -> dict:
        return {
            "output_bundle": self.output_bundle,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class NotLiveReadyReport:
    readiness_index: ValidationReadinessIndex
    live_readiness: Mapping[str, Any] | None = None
    missing_checks: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()
    next_commands: tuple[str, ...] = ()

    @property
    def live_ready(self) -> bool:
        live_passed = bool(self.live_readiness and self.live_readiness.get("live_unlock_allowed"))
        return self.readiness_index.passed and live_passed and not self.missing_checks and not self.failed_checks

    def to_dict(self) -> dict:
        return {
            "live_ready": self.live_ready,
            "status": "live_ready" if self.live_ready else "not_live_ready",
            "missing_checks": list(self.missing_checks),
            "failed_checks": list(self.failed_checks),
            "next_commands": list(self.next_commands),
            "readiness_index": self.readiness_index.to_dict(),
            "live_readiness": dict(self.live_readiness or {}),
        }


def default_cli_smoke_specs() -> tuple[CliSmokeSpec, ...]:
    return (
        CliSmokeSpec("backtest", "trading_env\\Scripts\\python.exe main.py backtest --provider sample --symbol SPY --timeout-seconds 60", expected_artifacts=("runs/equity.jsonl", "runs/fills.jsonl")),
        CliSmokeSpec("report", "trading_env\\Scripts\\python.exe main.py report --provider sample --symbol SPY --html-output reports/smoke-backtest.html --timeout-seconds 60", expected_artifacts=("reports/smoke-backtest.html",)),
        CliSmokeSpec("optimize", "trading_env\\Scripts\\python.exe main.py optimize --provider sample --symbol SPY --param-grid-file configs/optimization/mean_reversion_daily.json --timeout-seconds 180", expected_artifacts=("runs/optimization-results.jsonl",), timeout_seconds=180),
        CliSmokeSpec("bulk", "trading_env\\Scripts\\python.exe main.py bulk --provider sample --symbols SPY,QQQ --strategies buyHold --max-symbols 2 --timeout-seconds 180", expected_artifacts=("reports/bulk-backtest-summary.json",), timeout_seconds=180),
        CliSmokeSpec("matrix", "trading_env\\Scripts\\python.exe main.py matrix --research-matrix-file configs/research/sample_cross_asset_matrix.json --strategies buyHold --max-symbols 1 --timeout-seconds 180", expected_artifacts=("reports/research-matrix-summary.json",), timeout_seconds=180),
        CliSmokeSpec("replicate", "trading_env\\Scripts\\python.exe main.py replicate --replication-file configs/research/published_strategy_replications.json --timeout-seconds 180", expected_artifacts=("reports/published-strategy-replication.json",), timeout_seconds=180),
        CliSmokeSpec("stream", "trading_env\\Scripts\\python.exe main.py stream --provider sample --symbol SPY --timeout-seconds 60", expected_artifacts=("runs/engine-events.jsonl",)),
        CliSmokeSpec("paper", "trading_env\\Scripts\\python.exe main.py paper --provider sample --symbol SPY --timeout-seconds 60", expected_artifacts=("runs/engine-events.jsonl",)),
        CliSmokeSpec("paper-session", "trading_env\\Scripts\\python.exe main.py paper-session --provider sample --symbol SPY --store-dir runs/paper-session-smoke --timeout-seconds 60", expected_artifacts=("runs/paper-session-smoke",)),
        CliSmokeSpec("paper-session-schedule", "trading_env\\Scripts\\python.exe main.py paper-session-schedule --provider sample --symbol SPY --store-dir runs/paper-session-schedule-smoke --paper-session-schedule-output reports/smoke-paper-session-schedule.json --timeout-seconds 60", expected_artifacts=("reports/smoke-paper-session-schedule.json",)),
        CliSmokeSpec("paper-broker-proof", "trading_env\\Scripts\\python.exe main.py paper-broker-proof --provider sample --symbol SPY --paper-proof-output reports/smoke-paper-broker-proof.json --timeout-seconds 60", expected_artifacts=("reports/smoke-paper-broker-proof.json",)),
        CliSmokeSpec("paper-broker-schedule", "trading_env\\Scripts\\python.exe main.py paper-broker-schedule --provider sample --symbol SPY --paper-proof-schedule-output reports/smoke-paper-broker-schedule.json --timeout-seconds 60", expected_artifacts=("reports/smoke-paper-broker-schedule.json",)),
        CliSmokeSpec("paper-activation-report", "trading_env\\Scripts\\python.exe main.py paper-activation-report --paper-proof-output reports/alpaca-paper-broker-proof.json --paper-proof-schedule-output reports/alpaca-paper-broker-proof-schedule.json --paper-submit-evidence reports/evidence/paper-submit-activation-check.json --paper-activation-output reports/smoke-paper-activation-report.json --timeout-seconds 60", expected_artifacts=("reports/smoke-paper-activation-report.json",)),
        CliSmokeSpec("paper-soak", "trading_env\\Scripts\\python.exe main.py paper-soak --provider sample --symbol SPY --soak-sessions 2 --store-dir runs/paper-soak-smoke --timeout-seconds 120", expected_artifacts=("runs/paper-soak-smoke",), timeout_seconds=120),
        CliSmokeSpec("paper-portfolio", "trading_env\\Scripts\\python.exe main.py paper-portfolio --provider sample --symbols SPY,QQQ --max-symbols 2 --store-dir runs/paper-portfolio-smoke --timeout-seconds 120", expected_artifacts=("runs/paper-portfolio-smoke",), timeout_seconds=120),
        CliSmokeSpec("paper-pilot", "trading_env\\Scripts\\python.exe main.py paper-pilot --provider sample --symbol SPY --store-dir runs/paper-pilot-smoke --paper-cleanup-output reports/smoke-paper-cleanup.json --paper-pilot-validation-output reports/evidence/smoke-paper-pilot-validation.json --paper-pilot-output reports/smoke-paper-pilot.json --timeout-seconds 120", expected_artifacts=("reports/smoke-paper-pilot.json",), timeout_seconds=120),
        CliSmokeSpec("validate", "trading_env\\Scripts\\python.exe main.py validate --validation-output reports/smoke-validation-readiness.json --readiness-html-output reports/smoke-readiness.html --timeout-seconds 60", expected_artifacts=("reports/smoke-validation-readiness.json", "reports/smoke-readiness.html")),
        CliSmokeSpec("validate-profile", "trading_env\\Scripts\\python.exe main.py validate-profile --validation-profile smoke --validation-profile-output reports/smoke-validation-profile.json --validation-run-id cli-smoke --timeout-seconds 60", expected_artifacts=("reports/smoke-validation-profile.json",)),
        CliSmokeSpec("profile", "trading_env\\Scripts\\python.exe main.py profile --provider sample --symbol SPY --profiling-output reports/smoke-profiling-report.json --profiling-repeats 1 --timeout-seconds 180", expected_artifacts=("reports/smoke-profiling-report.json",), timeout_seconds=180),
        CliSmokeSpec("release-checklist", "trading_env\\Scripts\\python.exe main.py release-checklist --release-output reports/smoke-release-validation-bundle.json --readiness-html-output reports/smoke-release-readiness.html --release-candidate-output reports/smoke-release-candidate.json --timeout-seconds 60", expected_artifacts=("reports/smoke-release-validation-bundle.json", "reports/smoke-release-readiness.html", "reports/smoke-release-candidate.json")),
    )


def default_performance_budgets() -> tuple[PerformanceBudget, ...]:
    return (
        PerformanceBudget("perf_indicator_calculation", "indicator-calculation", "indicator", 0.10),
        PerformanceBudget("perf_strategy_generation", "strategy-generation", "strategy_generation", 0.10),
        PerformanceBudget("perf_single_backtest", "single-backtest", "backtest_loop", 1.00),
        PerformanceBudget("perf_bulk_research", "bulk-research", "bulk_research", 10.00),
        PerformanceBudget("perf_storage_write", "storage-write", "storage_write", 0.25),
        PerformanceBudget("perf_paper_session_planning", "paper-session-planning", "paper_session_planning", 2.00),
        PerformanceBudget("perf_broker_reconciliation", "broker-reconciliation", "broker_reconciliation", 0.25),
    )


def evaluate_paper_profile_validation(artifact_root: str = "runs/paper-profile-validation") -> PaperProfileValidationReport:
    profiles = alpaca_paper_soak_profiles()
    safe_configs = {
        "sample-data": RuntimeConfig(
            data=MarketDataConfig(provider="sample"),
            execution=ExecutionConfig(mode="dry-run"),
        ),
        "dry-run": RuntimeConfig(
            data=MarketDataConfig(provider="alpaca"),
            alpaca=AlpacaConfig(base_url="https://paper-api.alpaca.markets"),
            execution=ExecutionConfig(mode="dry-run"),
        ),
        "alpaca-data-only": RuntimeConfig(
            data=MarketDataConfig(provider="alpaca"),
            alpaca=AlpacaConfig(base_url="https://paper-api.alpaca.markets"),
            execution=ExecutionConfig(mode="dry-run"),
        ),
        "micro-notional": RuntimeConfig(
            data=MarketDataConfig(provider="alpaca"),
            alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
            execution=ExecutionConfig(mode="paper"),
        ),
        "full-paper-rehearsal": RuntimeConfig(
            data=MarketDataConfig(provider="alpaca"),
            alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
            execution=ExecutionConfig(mode="paper"),
        ),
    }
    profile_results = {}
    for name, profile in profiles.items():
        validation = validate_alpaca_paper_soak_profile(profile, safe_configs[name])
        options = profile.session_options(f"{artifact_root}/{name}", state_db_path=f"{artifact_root}/{name}.sqlite3")
        daemon_options = profile.daemon_options(
            artifact_root=f"{artifact_root}/daemon/{name}",
            schedule_output_path=f"{artifact_root}/daemon/{name}-schedule.json",
            report_path=f"{artifact_root}/daemon/{name}-report.json",
            state_path=f"{artifact_root}/daemon/{name}-state.json",
            heartbeat_path=f"{artifact_root}/daemon/{name}-heartbeat.json",
            kill_switch_path=f"{artifact_root}/daemon/{name}.kill",
            lock_path=f"{artifact_root}/daemon/{name}.lock",
            cleanup_output_path=f"{artifact_root}/daemon/{name}-cleanup.json",
            monitor_output_path=f"{artifact_root}/daemon/{name}-monitor.json",
            data_parity_output_path=f"{artifact_root}/daemon/{name}-data-parity.json",
        )
        profile_results[name] = {
            "passed": validation.passed and options.risk_budget is not None,
            "validation": validation.to_dict(),
            "session_options": {
                "submit_orders": options.submit_orders,
                "artifact_root": options.artifact_root,
                "recover_state": options.recover_state,
                "state_db_path": options.state_db_path,
                "risk_budget": options.risk_budget.to_dict() if options.risk_budget else None,
            },
            "daemon_options": daemon_options.to_dict(),
            "soak_config": profile.soak_config().to_dict() if hasattr(profile.soak_config(), "to_dict") else {
                "sessions": profile.soak_config().sessions,
                "stop_on_failure": profile.soak_config().stop_on_failure,
            },
        }

    unsafe_configs = {
        "micro_notional_live_url": (
            profiles["micro-notional"],
            RuntimeConfig(
                data=MarketDataConfig(provider="alpaca"),
                alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://api.alpaca.markets"),
                execution=ExecutionConfig(mode="paper"),
            ),
        ),
        "micro_notional_dry_run_mode": (
            profiles["micro-notional"],
            RuntimeConfig(
                data=MarketDataConfig(provider="alpaca"),
                alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
                execution=ExecutionConfig(mode="dry-run"),
            ),
        ),
        "full_rehearsal_missing_keys": (
            profiles["full-paper-rehearsal"],
            RuntimeConfig(
                data=MarketDataConfig(provider="alpaca"),
                alpaca=AlpacaConfig(api_key="", secret_key="", base_url="https://paper-api.alpaca.markets"),
                execution=ExecutionConfig(mode="paper"),
            ),
        ),
    }
    unsafe_results = {}
    for name, (profile, config) in unsafe_configs.items():
        validation = validate_alpaca_paper_soak_profile(profile, config)
        unsafe_results[name] = {
            "blocked": not validation.passed,
            "validation": validation.to_dict(),
        }
    return PaperProfileValidationReport(profile_results, unsafe_results)


def default_release_checklist() -> ReleaseChecklist:
    return ReleaseChecklist(
        steps=(
            ReleaseChecklistStep("fast_unit_suite", "trading_env\\Scripts\\python.exe -m pytest src\\tests", description="Run the full local automated suite."),
            ReleaseChecklistStep("validation_manifest", "trading_env\\Scripts\\python.exe main.py validate --validation-output reports/validation-readiness.json", description="Write the current readiness index and not-live-ready report."),
            ReleaseChecklistStep("performance_profile", "trading_env\\Scripts\\python.exe main.py profile --profiling-output reports/profiling-report.json", description="Run critical-path benchmark tasks and budget checks."),
            ReleaseChecklistStep("paper_dry_run", "trading_env\\Scripts\\python.exe main.py paper-session --provider sample --symbol SPY --store-dir runs/release-paper-dry-run --timeout-seconds 60", description="Prove local paper-session artifact generation."),
            ReleaseChecklistStep("paper_profile_validation", None, description="Review paper-profile validation evidence in the release bundle."),
            ReleaseChecklistStep("alpaca_micro_notional_submit", "trading_env\\Scripts\\python.exe main.py paper-broker-proof --provider alpaca --execution-mode paper --symbol SPY --paper-proof-limit-price 1 --paper-proof-max-notional 25 --submit-orders --paper-proof-output reports/alpaca-paper-broker-proof.json --timeout-seconds 180", required=False, description="Optional broker-backed micro-notional paper submit/cancel proof when credentials and market conditions are available."),
            ReleaseChecklistStep("scheduled_alpaca_micro_notional_submit", "trading_env\\Scripts\\python.exe main.py paper-broker-schedule --provider alpaca --execution-mode paper --symbol SPY --paper-proof-limit-price 1 --paper-proof-max-notional 25 --submit-orders --paper-proof-schedule-output reports/alpaca-paper-broker-proof-schedule.json --timeout-seconds 180", required=False, description="Optional scheduled broker-proof run for the active market-session window."),
            ReleaseChecklistStep("paper_account_cleanup", "trading_env\\Scripts\\python.exe main.py paper-cleanup --provider alpaca --execution-mode paper --paper-cleanup-output reports/paper-cleanup-report.json --timeout-seconds 120", required=False, description="Preview or submit guarded flatten orders so promoted paper sessions start from a clean account state."),
            ReleaseChecklistStep("deployment_rehearsal", None, required=False, description="Manual/deployment environment rehearsal until automated deployment runners exist."),
        )
    )


def default_validation_manifest() -> ValidationManifest:
    static_checks = (
        ValidationCheckSpec("unit_test_suite", "code_tests", "tests", "Full unit and integration suite passes.", "trading_env\\Scripts\\python.exe -m pytest src\\tests", required_for=("paper_readiness", "release_readiness"), timeout_seconds=300),
        ValidationCheckSpec("alpaca_data_connectivity", "live_data", "data", "Alpaca historical/latest/websocket data connectivity passes.", required_for=("paper_readiness", "live_readiness"), timeout_seconds=120),
        ValidationCheckSpec("alpaca_paper_order_lifecycle", "broker_lifecycle", "execution", "Tiny-notional Alpaca paper submit/cancel/reconcile lifecycle passes.", "trading_env\\Scripts\\python.exe main.py paper-broker-proof --provider alpaca --execution-mode paper --symbol SPY --paper-proof-limit-price 1 --paper-proof-max-notional 25 --submit-orders --paper-proof-output reports/alpaca-paper-broker-proof.json --timeout-seconds 180", required_for=("paper_readiness", "live_readiness"), expected_artifacts=("reports/alpaca-paper-broker-proof.json",), timeout_seconds=180),
        ValidationCheckSpec("real_alpaca_fill_polling", "broker_lifecycle", "execution", "Submitted Alpaca paper orders are polled back from broker REST order state.", "trading_env\\Scripts\\python.exe main.py paper-broker-proof --provider alpaca --execution-mode paper --symbol SPY --paper-proof-limit-price 1 --paper-proof-max-notional 25 --submit-orders --paper-proof-output reports/alpaca-paper-broker-proof.json --timeout-seconds 180", required_for=("live_readiness",), expected_artifacts=("reports/alpaca-paper-broker-proof.json",), timeout_seconds=180),
        ValidationCheckSpec("paper_broker_proof_schedule", "broker_schedule", "operations", "Scheduled Alpaca paper broker proof runs only during allowed windows and records blocked-window no-submit evidence.", "trading_env\\Scripts\\python.exe main.py paper-broker-schedule --provider alpaca --execution-mode paper --symbol SPY --paper-proof-limit-price 1 --paper-proof-max-notional 25 --submit-orders --paper-proof-schedule-output reports/alpaca-paper-broker-proof-schedule.json --timeout-seconds 180", required_for=("live_readiness",), expected_artifacts=("reports/alpaca-paper-broker-proof-schedule.json",), timeout_seconds=180),
        ValidationCheckSpec("broker_account_parity", "broker_parity", "execution", "Local account state matches Alpaca paper account snapshots.", required_for=("paper_readiness", "live_readiness"), timeout_seconds=120),
        ValidationCheckSpec("paper_account_parity", "broker_parity", "execution", "Paper account snapshots, positions, open orders, and polled reports are present after broker proof.", required_for=("live_readiness",), expected_artifacts=("reports/alpaca-paper-broker-proof.json",), timeout_seconds=120),
        ValidationCheckSpec("paper_account_cleanup", "broker_cleanup", "execution", "Paper account cleanup proof shows no leftover positions or a submitted/reconciled flatten run.", "trading_env\\Scripts\\python.exe main.py paper-cleanup --provider alpaca --execution-mode paper --paper-cleanup-output reports/paper-cleanup-report.json --timeout-seconds 120", required_for=("paper_readiness", "live_readiness"), expected_artifacts=("reports/paper-cleanup-report.json",), timeout_seconds=120),
        ValidationCheckSpec("failure_injection_suite", "failure_injection", "runtime", "Network, broker, stale-data, malformed-payload, and lifecycle fault tests pass.", required_for=("paper_readiness", "release_readiness"), timeout_seconds=180),
        ValidationCheckSpec("restart_recovery_drill", "recovery", "storage", "Crash/restart drills prove state reload and unresolved-order blocking.", required_for=("paper_readiness", "live_readiness"), timeout_seconds=180),
        ValidationCheckSpec("data_quality_torture", "data_quality", "data", "Adjusted/raw, missing/duplicate bar, calendar, gap, and zero-volume tests pass.", required_for=("paper_readiness", "release_readiness"), timeout_seconds=180),
        ValidationCheckSpec("backtester_differential", "backtest_validation", "backtesting", "Backtester output matches independent/reference calculations for simple scenarios.", required_for=("paper_readiness", "release_readiness"), timeout_seconds=180),
        ValidationCheckSpec("strategy_robustness", "strategy_validation", "strategies", "Walk-forward, perturbation, cluster, cost-stress, and benchmark-relative gates pass.", required_for=("paper_readiness", "optimization_readiness"), timeout_seconds=300),
        ValidationCheckSpec("optimizer_validation", "optimizer_validation", "backtesting", "Optimizer reproducibility, leakage, persistence, pruning, and metric tests pass.", required_for=("optimization_readiness", "release_readiness"), timeout_seconds=300),
        ValidationCheckSpec("portfolio_risk_stress", "risk_stress", "risk", "Concentration, exposure, cash, margin, correlation shock, and kill-switch tests pass.", required_for=("paper_readiness", "live_readiness"), timeout_seconds=180),
        ValidationCheckSpec("paper_soak_tiers", "paper_soak", "operations", "Local, data-only, micro-notional, portfolio, recovery, and rehearsal soaks pass.", required_for=("paper_readiness", "live_readiness"), timeout_seconds=900),
        ValidationCheckSpec("paper_session_schedule", "paper_schedule", "operations", "Scheduled paper-session windows produce required readiness evidence without blocked-window submissions.", "trading_env\\Scripts\\python.exe main.py paper-session-schedule --provider sample --symbol SPY --store-dir runs/paper-session-schedule --paper-session-schedule-output reports/paper-session-schedule.json --timeout-seconds 120", required_for=("paper_readiness",), expected_artifacts=("reports/paper-session-schedule.json",), timeout_seconds=120),
        ValidationCheckSpec("daily_ops_acceptance", "operator_reports", "reporting", "Daily paper report scenarios produce correct decisions and recommendations.", required_for=("paper_readiness", "release_readiness"), timeout_seconds=120),
        ValidationCheckSpec("observability_acceptance", "observability", "monitoring", "Logs, metrics, health checks, notifications, audit IDs, and halt reasons pass.", required_for=("paper_readiness", "release_readiness"), timeout_seconds=120),
        ValidationCheckSpec("security_configuration", "security", "config", "Secrets, paper/live URL, env, and deployment safety checks pass.", required_for=("paper_readiness", "live_readiness", "release_readiness"), timeout_seconds=120),
        ValidationCheckSpec("deployment_rehearsal", "deployment", "deployment", "Windows, Docker, server, persistence, watchdog, and restart rehearsals pass.", required_for=("release_readiness", "live_readiness"), timeout_seconds=600),
        ValidationCheckSpec("golden_artifacts", "golden_artifacts", "storage", "Frozen input/output artifacts match for critical reports and decisions.", required_for=("release_readiness",), timeout_seconds=120),
        ValidationCheckSpec("paper_profile_validation", "paper_profiles", "operations", "Alpaca paper profiles validate risk budgets and block unsafe combinations.", required_for=("paper_readiness", "release_readiness"), timeout_seconds=60),
        ValidationCheckSpec("release_checklist_bundle", "release", "validation", "Release checklist bundle is generated with fast, full, paper, performance, and deployment gates.", required_for=("release_readiness",), timeout_seconds=60),
    )
    return ValidationManifest(
        checks=tuple(
            list(static_checks)
            + [spec.to_check_spec() for spec in default_cli_smoke_specs()]
            + [budget.to_check_spec() for budget in default_performance_budgets()]
        )
    )


def default_validation_profiles(manifest: ValidationManifest | None = None) -> tuple[ValidationProfile, ...]:
    manifest = manifest or default_validation_manifest()
    paper_check_ids = tuple(check.check_id for check in manifest.required_checks("paper_readiness"))
    release_check_ids = tuple(check.check_id for check in manifest.required_checks("release_readiness"))
    live_check_ids = tuple(check.check_id for check in manifest.required_checks("live_readiness"))
    smoke_check_ids = (
        "paper_profile_validation",
        "security_configuration",
    )
    fast_check_ids = (
        "unit_test_suite",
        "paper_profile_validation",
        "security_configuration",
        "cli_smoke_backtest",
        "cli_smoke_report",
        "perf_indicator_calculation",
        "perf_single_backtest",
    )
    paper_dry_run_check_ids = (
        "unit_test_suite",
        "paper_profile_validation",
        "security_configuration",
        "paper_soak_tiers",
        "paper_session_schedule",
        "daily_ops_acceptance",
        "observability_acceptance",
        "cli_smoke_paper_session",
        "cli_smoke_paper_session_schedule",
        "cli_smoke_paper_soak",
        "perf_paper_session_planning",
    )
    paper_submit_check_ids = tuple(dict.fromkeys(paper_dry_run_check_ids + (
        "alpaca_data_connectivity",
        "alpaca_paper_order_lifecycle",
        "paper_broker_proof_schedule",
        "real_alpaca_fill_polling",
        "broker_account_parity",
        "paper_account_parity",
        "paper_account_cleanup",
        "restart_recovery_drill",
    )))
    return (
        ValidationProfile(
            "smoke",
            "release_readiness",
            tuple(check_id for check_id in smoke_check_ids if check_id in manifest.by_id()),
            max_age_hours=24,
            output_path="reports/evidence/smoke-validation.json",
            description="Ultra-light CLI validation-profile smoke that avoids recursive test execution.",
        ),
        ValidationProfile(
            "fast",
            "release_readiness",
            tuple(check_id for check_id in fast_check_ids if check_id in manifest.by_id()),
            max_age_hours=24,
            output_path="reports/evidence/fast-validation.json",
            description="Local fast checks for code, config, CLI smoke, and basic performance evidence.",
        ),
        ValidationProfile(
            "full",
            "paper_readiness",
            paper_check_ids,
            max_age_hours=24,
            output_path="reports/evidence/full-validation.json",
            description="All paper-readiness checks in the manifest.",
        ),
        ValidationProfile(
            "paper-dry-run",
            "paper_readiness",
            tuple(check_id for check_id in paper_dry_run_check_ids if check_id in manifest.by_id()),
            max_age_hours=12,
            output_path="reports/evidence/paper-dry-run-validation.json",
            description="Paper-session dry-run checks that do not submit broker orders.",
        ),
        ValidationProfile(
            "paper-submit",
            "paper_readiness",
            tuple(check_id for check_id in paper_submit_check_ids if check_id in manifest.by_id()),
            max_age_hours=12,
            output_path="reports/evidence/paper-submit-validation.json",
            description="Broker-backed Alpaca paper submission evidence profile.",
        ),
        ValidationProfile(
            "release",
            "release_readiness",
            release_check_ids,
            max_age_hours=24,
            output_path="reports/evidence/release-validation.json",
            description="Release-readiness checks and productization evidence.",
        ),
        ValidationProfile(
            "live-gate",
            "live_readiness",
            live_check_ids,
            max_age_hours=12,
            output_path="reports/evidence/live-gate-validation.json",
            description="Hard live-readiness gates. This does not enable live trading by itself.",
        ),
    )


def build_readiness_index(
    evidence: Sequence[ValidationEvidence] = (),
    manifest: ValidationManifest | None = None,
    target: str = "paper_readiness",
) -> ValidationReadinessIndex:
    return ValidationReadinessIndex(manifest or default_validation_manifest(), tuple(evidence), target)


def evaluate_performance_budgets(
    benchmark_report: BenchmarkSuiteReport,
    budgets: Sequence[PerformanceBudget] | None = None,
    min_acceleration_mean_seconds: float = 0.10,
) -> PerformanceBudgetReport:
    budgets = tuple(budgets or default_performance_budgets())
    summaries = {summary.name: summary for summary in benchmark_report.summaries}
    evidence: list[ValidationEvidence] = []
    for budget in budgets:
        summary = summaries.get(budget.benchmark_name)
        if summary is None:
            evidence.append(ValidationEvidence(budget.check_id, "missing", reason="benchmark_not_run"))
            continue
        mean_ok = summary.mean_seconds <= budget.max_mean_seconds
        total_ok = budget.max_total_seconds is None or summary.total_seconds <= budget.max_total_seconds
        passed = mean_ok and total_ok
        evidence.append(
            ValidationEvidence(
                budget.check_id,
                "passed" if passed else "failed",
                elapsed_seconds=summary.mean_seconds,
                reason="passed" if passed else "performance_budget_exceeded",
                metadata={
                    "benchmark_name": budget.benchmark_name,
                    "mean_seconds": summary.mean_seconds,
                    "max_mean_seconds": budget.max_mean_seconds,
                    "total_seconds": summary.total_seconds,
                    "max_total_seconds": budget.max_total_seconds,
                },
            )
        )
    return PerformanceBudgetReport(
        budgets=tuple(budgets),
        benchmark_report=benchmark_report,
        acceleration_plan=build_acceleration_plan(benchmark_report, min_acceleration_mean_seconds),
        evidence=tuple(evidence),
    )


def build_not_live_ready_report(
    readiness_index: ValidationReadinessIndex,
    live_readiness: Mapping[str, Any] | None = None,
) -> NotLiveReadyReport:
    missing = tuple(check.check_id for check in readiness_index.missing_required)
    failed = tuple(check.check_id for check in readiness_index.failed_required)
    commands = tuple(
        check.command
        for check in readiness_index.required_checks
        if check.check_id in {*missing, *failed} and check.command
    )
    return NotLiveReadyReport(readiness_index, live_readiness, missing, failed, commands)


def _missing(check: ValidationCheckSpec) -> ValidationEvidence:
    return ValidationEvidence(check.check_id, "missing", reason="no_current_evidence")
