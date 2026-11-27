from dataclasses import dataclass, field
from typing import Mapping

from src.config import RuntimeConfig
from src.engine import CommitteeExecutionPolicy

from .paper_daemon import PaperTradingDaemonOptions
from .paper_session import AutonomousPaperSessionOptions, PaperSessionRiskBudget
from .soak import PaperSessionSoakConfig


@dataclass(frozen=True)
class AlpacaPaperSoakProfile:
    name: str
    submit_orders: bool
    sessions: int
    risk_budget: PaperSessionRiskBudget
    required_execution_mode: str = "dry-run"
    require_alpaca_provider: bool = True
    require_paper_trading: bool = True
    require_paper_url: bool = True
    recover_state: bool = True
    max_position_weight: float = 0.25
    execution_policy: CommitteeExecutionPolicy = field(default_factory=CommitteeExecutionPolicy)
    comparison_provider: str | None = None
    description: str = ""
    daemon_interval_seconds: float = 300.0
    daemon_max_iterations: int | None = None
    daemon_cleanup_each_iteration: bool = False
    daemon_monitor_each_iteration: bool = False
    daemon_data_parity_each_iteration: bool = False
    daemon_data_parity_max_close_drift_bps: float = 5.0

    def session_options(self, artifact_root: str, state_db_path: str | None = None) -> AutonomousPaperSessionOptions:
        return AutonomousPaperSessionOptions(
            submit_orders=self.submit_orders,
            artifact_root=artifact_root,
            comparison_provider=self.comparison_provider,
            recover_state=self.recover_state,
            state_db_path=state_db_path,
            risk_budget=self.risk_budget,
            max_position_weight=self.max_position_weight,
            execution_policy=self.execution_policy,
        )

    def soak_config(self) -> PaperSessionSoakConfig:
        return PaperSessionSoakConfig(sessions=self.sessions, stop_on_failure=True)

    def daemon_options(
        self,
        *,
        artifact_root: str = "runs/paper-daemon",
        schedule_output_path: str = "reports/paper-daemon-schedule.json",
        report_path: str = "reports/paper-daemon-report.json",
        state_path: str = "runs/paper-daemon-state.json",
        heartbeat_path: str = "runs/paper-daemon-heartbeat.json",
        kill_switch_path: str = "runs/paper-daemon.kill",
        lock_path: str = "runs/paper-daemon.lock",
        cleanup_output_path: str = "reports/paper-daemon-cleanup.json",
        monitor_output_path: str = "reports/paper-daemon-monitor.json",
        data_parity_output_path: str = "reports/paper-daemon-data-parity.json",
        submit_orders: bool | None = None,
    ) -> PaperTradingDaemonOptions:
        return PaperTradingDaemonOptions(
            interval_seconds=self.daemon_interval_seconds,
            max_iterations=self.daemon_max_iterations or self.sessions,
            kill_switch_path=kill_switch_path,
            state_path=state_path,
            heartbeat_path=heartbeat_path,
            lock_path=lock_path,
            artifact_root=artifact_root,
            schedule_output_path=schedule_output_path,
            report_path=report_path,
            cleanup_each_iteration=self.daemon_cleanup_each_iteration,
            cleanup_submit_orders=False,
            cleanup_output_path=cleanup_output_path,
            monitor_each_iteration=self.daemon_monitor_each_iteration,
            monitor_output_path=monitor_output_path,
            data_parity_each_iteration=self.daemon_data_parity_each_iteration,
            data_parity_output_path=data_parity_output_path,
            data_parity_max_close_drift_bps=self.daemon_data_parity_max_close_drift_bps,
            submit_orders=self.submit_orders if submit_orders is None else submit_orders,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "submit_orders": self.submit_orders,
            "sessions": self.sessions,
            "required_execution_mode": self.required_execution_mode,
            "require_alpaca_provider": self.require_alpaca_provider,
            "require_paper_trading": self.require_paper_trading,
            "require_paper_url": self.require_paper_url,
            "recover_state": self.recover_state,
            "max_position_weight": self.max_position_weight,
            "comparison_provider": self.comparison_provider,
            "description": self.description,
            "daemon": {
                "interval_seconds": self.daemon_interval_seconds,
                "max_iterations": self.daemon_max_iterations or self.sessions,
                "cleanup_each_iteration": self.daemon_cleanup_each_iteration,
                "monitor_each_iteration": self.daemon_monitor_each_iteration,
                "data_parity_each_iteration": self.daemon_data_parity_each_iteration,
                "data_parity_max_close_drift_bps": self.daemon_data_parity_max_close_drift_bps,
            },
            "execution_policy": {
                "allow_fractional_quantity": self.execution_policy.allow_fractional_quantity,
                "min_order_quantity": self.execution_policy.min_order_quantity,
                "default_hedge_symbol": self.execution_policy.default_hedge_symbol,
                "flatten_on_cash": self.execution_policy.flatten_on_cash,
                "max_target_notional": self.execution_policy.max_target_notional,
            },
            "risk_budget": self.risk_budget.to_dict(),
        }


@dataclass(frozen=True)
class AlpacaPaperSoakProfileValidation:
    profile: AlpacaPaperSoakProfile
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "profile": self.profile.to_dict(),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def alpaca_paper_soak_profiles() -> Mapping[str, AlpacaPaperSoakProfile]:
    profiles = (
        AlpacaPaperSoakProfile(
            name="sample-data",
            submit_orders=False,
            sessions=3,
            required_execution_mode="dry-run",
            require_alpaca_provider=False,
            require_paper_trading=False,
            require_paper_url=False,
            recover_state=False,
            risk_budget=PaperSessionRiskBudget(cash_reserve=0.0),
            daemon_interval_seconds=0.0,
            daemon_max_iterations=3,
            daemon_data_parity_each_iteration=True,
            description="Offline sample-data daemon soak for local scheduling, artifact, and parity plumbing.",
        ),
        AlpacaPaperSoakProfile(
            name="dry-run",
            submit_orders=False,
            sessions=3,
            required_execution_mode="dry-run",
            risk_budget=PaperSessionRiskBudget(cash_reserve=0.0),
            daemon_max_iterations=3,
            daemon_data_parity_each_iteration=True,
            description="No broker orders; validates data, committee, planning, recovery, and artifacts.",
        ),
        AlpacaPaperSoakProfile(
            name="alpaca-data-only",
            submit_orders=False,
            sessions=3,
            required_execution_mode="dry-run",
            risk_budget=PaperSessionRiskBudget(cash_reserve=0.0),
            comparison_provider="sample",
            daemon_max_iterations=3,
            daemon_data_parity_each_iteration=True,
            description="Alpaca data-only daemon dry run with no broker submission intent.",
        ),
        AlpacaPaperSoakProfile(
            name="micro-notional",
            submit_orders=True,
            sessions=3,
            required_execution_mode="paper",
            max_position_weight=0.0025,
            execution_policy=CommitteeExecutionPolicy(
                allow_fractional_quantity=True,
                min_order_quantity=0.000001,
                max_target_notional=25.0,
            ),
            risk_budget=PaperSessionRiskBudget(
                min_order_quantity=0.0,
                max_session_notional=25.0,
                max_new_exposure=0.0025,
                max_turnover=0.0025,
                cash_reserve=0.95,
            ),
            daemon_max_iterations=3,
            daemon_cleanup_each_iteration=True,
            daemon_monitor_each_iteration=True,
            daemon_data_parity_each_iteration=True,
            description="Tiny paper submissions to prove broker lifecycle, reconciliation, and scorecards.",
        ),
        AlpacaPaperSoakProfile(
            name="full-paper-rehearsal",
            submit_orders=True,
            sessions=5,
            required_execution_mode="paper",
            max_position_weight=0.10,
            risk_budget=PaperSessionRiskBudget(
                max_session_notional=2_500.0,
                max_new_exposure=0.10,
                max_turnover=0.20,
                cash_reserve=0.50,
            ),
            daemon_max_iterations=5,
            daemon_cleanup_each_iteration=True,
            daemon_monitor_each_iteration=True,
            daemon_data_parity_each_iteration=True,
            description="Guarded full paper rehearsal after dry-run and micro-notional profiles pass.",
        ),
    )
    return {profile.name: profile for profile in profiles}


def validate_alpaca_paper_soak_profile(
    profile: AlpacaPaperSoakProfile,
    config: RuntimeConfig,
) -> AlpacaPaperSoakProfileValidation:
    errors: list[str] = []
    warnings: list[str] = []
    provider = config.data.provider.lower()
    execution_mode = config.execution.mode.lower()
    base_url = config.alpaca.base_url.lower()

    if profile.require_alpaca_provider and provider != "alpaca":
        errors.append("DATA_PROVIDER must be alpaca for this soak profile.")
    if execution_mode != profile.required_execution_mode:
        errors.append(f"EXECUTION_MODE must be {profile.required_execution_mode} for {profile.name}.")
    if profile.require_paper_trading and not config.paper_trading:
        errors.append("PAPER_TRADING must be true for Alpaca paper soak profiles.")
    if profile.require_paper_url and "paper-api.alpaca.markets" not in base_url:
        errors.append("ALPACA_BASE_URL must point to https://paper-api.alpaca.markets.")
    if profile.submit_orders and not config.alpaca.api_key:
        errors.append("ALPACA_API_KEY is required for submitting paper orders.")
    if profile.submit_orders and not config.alpaca.secret_key:
        errors.append("ALPACA_SECRET_KEY is required for submitting paper orders.")
    if config.execution.allow_live_trading:
        warnings.append("ALLOW_LIVE_TRADING is enabled; this profile is intended for paper-only operation.")
    return AlpacaPaperSoakProfileValidation(profile, tuple(errors), tuple(warnings))
