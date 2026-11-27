from dataclasses import dataclass, field
from datetime import datetime, time, timezone
import json
from pathlib import Path
from time import sleep
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from src.config import RuntimeConfig, validate_runtime_environment
from src.data import MarketSession, MarketSessionCalendar, MarketSessionPolicy
from src.execution import Broker
from src.models import Order


@dataclass(frozen=True)
class PaperBrokerProofProbe:
    name: str
    passed: bool
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PaperBrokerOrderPlan:
    symbol: str
    side: str = "BUY"
    quantity: float = 1.0
    order_type: str = "LIMIT"
    limit_price: float = 1.0
    max_notional: float = 25.0
    client_order_id: str | None = None

    @property
    def planned_notional(self) -> float:
        return abs(float(self.quantity) * float(self.limit_price))

    def to_order(self) -> Order:
        return Order(
            symbol=self.symbol.upper(),
            side=self.side.upper(),
            quantity=float(self.quantity),
            order_type=self.order_type.upper(),
            limit_price=float(self.limit_price) if self.order_type.upper() == "LIMIT" else None,
            client_order_id=self.client_order_id,
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol.upper(),
            "side": self.side.upper(),
            "quantity": self.quantity,
            "order_type": self.order_type.upper(),
            "limit_price": self.limit_price,
            "planned_notional": self.planned_notional,
            "max_notional": self.max_notional,
            "client_order_id": self.client_order_id,
        }


@dataclass(frozen=True)
class PaperBrokerProofApprovalPolicy:
    symbol_allowlist: tuple[str, ...] = ()
    max_daily_submissions: int | None = None
    kill_switch_enabled: bool = False
    repeated_reject_lockout_threshold: int | None = None
    require_cleanup: bool = True

    def to_dict(self) -> dict:
        return {
            "symbol_allowlist": list(self.symbol_allowlist),
            "max_daily_submissions": self.max_daily_submissions,
            "kill_switch_enabled": self.kill_switch_enabled,
            "repeated_reject_lockout_threshold": self.repeated_reject_lockout_threshold,
            "require_cleanup": self.require_cleanup,
        }


@dataclass(frozen=True)
class PaperBrokerProofOptions:
    submit_orders: bool = False
    cancel_after_submit: bool = True
    allow_pre_market: bool = False
    allow_after_hours: bool = False
    fill_poll_attempts: int = 1
    fill_poll_interval_seconds: float = 0.0
    approval_policy: PaperBrokerProofApprovalPolicy | None = None
    prior_reports: tuple[Mapping[str, Any], ...] = ()
    now: datetime | None = None


@dataclass(frozen=True)
class PaperBrokerProofReport:
    generated_at: datetime
    order_plan: PaperBrokerOrderPlan
    session: str
    submit_requested: bool
    submit_allowed: bool
    submitted: bool
    cancelled: bool
    reason: str
    probes: tuple[PaperBrokerProofProbe, ...]
    orders: tuple[Mapping[str, Any], ...] = ()
    execution_reports: tuple[Mapping[str, Any], ...] = ()
    polled_execution_reports: tuple[Mapping[str, Any], ...] = ()
    account_snapshot: Mapping[str, Any] | None = None
    post_account_snapshot: Mapping[str, Any] | None = None
    positions_before: tuple[Mapping[str, Any], ...] = ()
    positions_after: tuple[Mapping[str, Any], ...] = ()
    open_orders_before: tuple[Mapping[str, Any], ...] = ()
    open_orders_after: tuple[Mapping[str, Any], ...] = ()
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "generated_at": self.generated_at.isoformat(),
            "order_plan": self.order_plan.to_dict(),
            "session": self.session,
            "submit_requested": self.submit_requested,
            "submit_allowed": self.submit_allowed,
            "submitted": self.submitted,
            "cancelled": self.cancelled,
            "reason": self.reason,
            "probes": [probe.to_dict() for probe in self.probes],
            "orders": [dict(order) for order in self.orders],
            "execution_reports": [dict(report) for report in self.execution_reports],
            "polled_execution_reports": [dict(report) for report in self.polled_execution_reports],
            "account_snapshot": dict(self.account_snapshot) if self.account_snapshot else None,
            "post_account_snapshot": dict(self.post_account_snapshot) if self.post_account_snapshot else None,
            "positions_before": [dict(position) for position in self.positions_before],
            "positions_after": [dict(position) for position in self.positions_after],
            "open_orders_before": [dict(order) for order in self.open_orders_before],
            "open_orders_after": [dict(order) for order in self.open_orders_after],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PaperBrokerProofScheduleWindow:
    name: str
    start_time: time
    end_time: time
    submit_orders_allowed: bool = True
    required: bool = True
    description: str = ""

    def contains(self, value: datetime) -> bool:
        current = value.timetz().replace(tzinfo=None)
        return self.start_time <= current <= self.end_time

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "submit_orders_allowed": self.submit_orders_allowed,
            "required": self.required,
            "description": self.description,
        }


@dataclass(frozen=True)
class ScheduledPaperBrokerProofRecord:
    window_name: str
    ran_at: datetime
    report: PaperBrokerProofReport | Mapping[str, Any]

    @property
    def submitted(self) -> bool:
        return bool(_proof_payload(self.report).get("submitted", False))

    @property
    def passed(self) -> bool:
        return bool(_proof_payload(self.report).get("passed", False))

    def to_dict(self) -> dict:
        return {
            "window_name": self.window_name,
            "ran_at": self.ran_at.isoformat(),
            "passed": self.passed,
            "submitted": self.submitted,
            "report": _proof_payload(self.report),
        }


@dataclass(frozen=True)
class PaperBrokerProofScheduleReport:
    windows: tuple[PaperBrokerProofScheduleWindow, ...]
    records: tuple[ScheduledPaperBrokerProofRecord, ...]
    checks: tuple[Mapping[str, Any], ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(bool(check["passed"]) for check in self.checks)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "windows": [window.to_dict() for window in self.windows],
            "records": [record.to_dict() for record in self.records],
            "checks": [dict(check) for check in self.checks],
            "artifact_path": self.artifact_path,
        }

    def to_evidence(self, check_id: str = "paper_broker_proof_schedule") -> "ValidationEvidence":
        from src.validation.manifest import ValidationEvidence

        return ValidationEvidence(
            check_id,
            "passed" if self.passed else "failed",
            artifact_path=self.artifact_path,
            reason="passed" if self.passed else "paper_broker_proof_schedule_failed",
            metadata=self.to_dict(),
        )


def run_paper_broker_proof(
    config: RuntimeConfig,
    broker_factory: Callable[[], Broker],
    order_plan: PaperBrokerOrderPlan,
    options: PaperBrokerProofOptions | None = None,
    output_path: str | Path | None = None,
) -> PaperBrokerProofReport:
    """Run a guarded broker-facing paper proof without bypassing session or safety gates."""

    options = options or PaperBrokerProofOptions()
    now = options.now or datetime.now(timezone.utc)
    calendar = MarketSessionCalendar()
    policy = MarketSessionPolicy(
        allow_pre_market=options.allow_pre_market,
        allow_regular=True,
        allow_after_hours=options.allow_after_hours,
    )
    session = calendar.session_at(now).value
    tradable = calendar.is_tradable_at(now, policy)
    env_validation = validate_runtime_environment(config)

    probes = [
        PaperBrokerProofProbe(
            "paper_environment",
            env_validation.passed,
            "passed" if env_validation.passed else "runtime_environment_invalid",
            {"errors": list(env_validation.errors), "warnings": list(env_validation.warnings)},
        ),
        PaperBrokerProofProbe(
            "alpaca_provider",
            config.data.provider.lower() == "alpaca",
            "passed" if config.data.provider.lower() == "alpaca" else "provider_is_not_alpaca",
            {"provider": config.data.provider},
        ),
        PaperBrokerProofProbe(
            "paper_execution_mode",
            config.execution.mode.lower() == "paper",
            "passed" if config.execution.mode.lower() == "paper" else "execution_mode_is_not_paper",
            {"execution_mode": config.execution.mode, "paper_trading": config.paper_trading},
        ),
        PaperBrokerProofProbe(
            "paper_endpoint",
            "paper-api.alpaca.markets" in config.alpaca.base_url.lower(),
            "passed" if "paper-api.alpaca.markets" in config.alpaca.base_url.lower() else "alpaca_base_url_not_paper",
            {"base_url": config.alpaca.base_url},
        ),
        PaperBrokerProofProbe(
            "market_session",
            tradable,
            "passed" if tradable else "market_session_not_tradable",
            {"timestamp": now.isoformat(), "session": session, "policy": _policy_payload(policy)},
        ),
        PaperBrokerProofProbe(
            "submit_flag",
            options.submit_orders,
            "passed" if options.submit_orders else "submit_orders_flag_not_set",
            {"submit_orders": options.submit_orders},
        ),
        PaperBrokerProofProbe(
            "tiny_notional",
            order_plan.planned_notional <= order_plan.max_notional,
            "passed" if order_plan.planned_notional <= order_plan.max_notional else "planned_notional_exceeds_cap",
            {"planned_notional": order_plan.planned_notional, "max_notional": order_plan.max_notional},
        ),
    ]
    probes.extend(_approval_policy_probes(order_plan, options, now))
    submit_allowed = all(probe.passed for probe in probes)
    if not submit_allowed:
        report = PaperBrokerProofReport(
            generated_at=now,
            order_plan=order_plan,
            session=session,
            submit_requested=options.submit_orders,
            submit_allowed=False,
            submitted=False,
            cancelled=False,
            reason=_first_failed_reason(probes),
            probes=tuple(probes),
        )
        return _write_report(report, output_path)

    orders: list[Mapping[str, Any]] = []
    reports: list[Mapping[str, Any]] = []
    polled_reports: list[Mapping[str, Any]] = []
    account_snapshot: Mapping[str, Any] | None = None
    post_account_snapshot: Mapping[str, Any] | None = None
    positions_before: list[Mapping[str, Any]] = []
    positions_after: list[Mapping[str, Any]] = []
    open_orders_before: list[Mapping[str, Any]] = []
    open_orders_after: list[Mapping[str, Any]] = []
    cancelled = False
    try:
        broker = broker_factory()
        try:
            account_snapshot = _account_payload(broker.account_snapshot())
            positions_before = [_position_payload(position) for position in broker.positions()]
            open_orders_before = [_order_payload(order) for order in broker.open_orders()]
        except Exception as exc:
            probes.append(PaperBrokerProofProbe("account_snapshot", False, "account_snapshot_failed", {"error": str(exc)}))
            report = PaperBrokerProofReport(
                generated_at=now,
                order_plan=order_plan,
                session=session,
                submit_requested=True,
                submit_allowed=True,
                submitted=False,
                cancelled=False,
                reason="account_snapshot_failed",
                probes=tuple(probes),
                account_snapshot=account_snapshot,
                positions_before=tuple(positions_before),
                open_orders_before=tuple(open_orders_before),
            )
            return _write_report(report, output_path)

        submitted = broker.submit_order(order_plan.to_order())
        orders.append(_order_payload(submitted))
        probes.append(
            PaperBrokerProofProbe(
                "submit_acknowledged",
                submitted.status in {"PENDING", "FILLED", "REJECTED"},
                "passed" if submitted.status in {"PENDING", "FILLED", "REJECTED"} else "unexpected_submit_status",
                {"status": submitted.status, "order_id": submitted.id},
            )
        )
        probes.append(
            PaperBrokerProofProbe(
                "order_not_rejected",
                submitted.status != "REJECTED",
                "passed" if submitted.status != "REJECTED" else "paper_order_rejected",
                {"status": submitted.status, "order_id": submitted.id},
            )
        )
        if options.cancel_after_submit and submitted.status == "PENDING":
            cancelled_order = broker.cancel_order(submitted.id)
            cancelled = cancelled_order is not None and cancelled_order.status == "CANCELLED"
            if cancelled_order is not None:
                orders.append(_order_payload(cancelled_order))
            probes.append(
                PaperBrokerProofProbe(
                    "cancel_acknowledged",
                    cancelled,
                    "passed" if cancelled else "cancel_failed",
                    {"status": cancelled_order.status if cancelled_order else None, "order_id": submitted.id},
                )
            )
        reports = [_execution_report_payload(report) for report in broker.execution_reports()]
        probes.append(
            PaperBrokerProofProbe(
                "execution_report_recorded",
                any(report.get("order_id") == submitted.id for report in reports),
                "passed" if any(report.get("order_id") == submitted.id for report in reports) else "missing_execution_report",
                {"reports": len(reports)},
            )
        )
        polled_reports, polling_source, polling_error = _poll_execution_reports(
            broker,
            [submitted],
            attempts=options.fill_poll_attempts,
            interval_seconds=options.fill_poll_interval_seconds,
        )
        known_polled_statuses = {report.get("status") for report in polled_reports}
        probes.extend(
            [
                PaperBrokerProofProbe(
                    "fill_polling_completed",
                    polling_error is None and bool(polled_reports),
                    "passed" if polling_error is None and bool(polled_reports) else "fill_polling_failed",
                    {"reports": len(polled_reports), "source": polling_source, "error": polling_error},
                ),
                PaperBrokerProofProbe(
                    "polled_order_converged",
                    submitted.id in {report.get("order_id") for report in polled_reports}
                    and bool(known_polled_statuses & {"FILLED", "CANCELLED", "REJECTED", "PENDING"}),
                    "passed"
                    if submitted.id in {report.get("order_id") for report in polled_reports}
                    and bool(known_polled_statuses & {"FILLED", "CANCELLED", "REJECTED", "PENDING"})
                    else "polled_order_not_converged",
                    {"order_id": submitted.id, "statuses": sorted(str(status) for status in known_polled_statuses if status)},
                ),
            ]
        )
        try:
            post_account_snapshot = _account_payload(broker.account_snapshot())
            positions_after = [_position_payload(position) for position in broker.positions()]
            open_orders_after = [_order_payload(order) for order in broker.open_orders()]
            pending_proof_order = any(order.get("id") == submitted.id for order in open_orders_after)
            cleanup_required = options.approval_policy.require_cleanup if options.approval_policy else True
            probes.extend(
                [
                    PaperBrokerProofProbe(
                        "post_account_snapshot",
                        True,
                        "passed",
                        {"cash": post_account_snapshot["cash"], "equity": post_account_snapshot["equity"]},
                    ),
                    PaperBrokerProofProbe(
                        "proof_order_cleanup",
                        (not cleanup_required) or (not pending_proof_order),
                        "passed" if (not cleanup_required) or (not pending_proof_order) else "proof_order_still_open",
                        {"open_orders_after": len(open_orders_after), "proof_order_id": submitted.id, "cleanup_required": cleanup_required},
                    ),
                ]
            )
        except Exception as exc:
            probes.append(PaperBrokerProofProbe("post_broker_snapshot", False, "post_broker_snapshot_failed", {"error": str(exc)}))
    except Exception as exc:
        probes.append(PaperBrokerProofProbe("broker_lifecycle", False, "broker_lifecycle_failed", {"error": str(exc)}))

    report = PaperBrokerProofReport(
        generated_at=now,
        order_plan=order_plan,
        session=session,
        submit_requested=True,
        submit_allowed=True,
        submitted=any(probe.name == "submit_acknowledged" and probe.passed for probe in probes),
        cancelled=cancelled,
        reason="passed" if all(probe.passed for probe in probes) else _first_failed_reason(probes),
        probes=tuple(probes),
        orders=tuple(orders),
        execution_reports=tuple(reports),
        polled_execution_reports=tuple(polled_reports),
        account_snapshot=account_snapshot,
        post_account_snapshot=post_account_snapshot,
        positions_before=tuple(positions_before),
        positions_after=tuple(positions_after),
        open_orders_before=tuple(open_orders_before),
        open_orders_after=tuple(open_orders_after),
    )
    return _write_report(report, output_path)


def _write_report(report: PaperBrokerProofReport, output_path: str | Path | None) -> PaperBrokerProofReport:
    if output_path is None:
        return report
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return PaperBrokerProofReport(
        generated_at=report.generated_at,
        order_plan=report.order_plan,
        session=report.session,
        submit_requested=report.submit_requested,
        submit_allowed=report.submit_allowed,
        submitted=report.submitted,
        cancelled=report.cancelled,
        reason=report.reason,
        probes=report.probes,
        orders=report.orders,
        execution_reports=report.execution_reports,
        polled_execution_reports=report.polled_execution_reports,
        account_snapshot=report.account_snapshot,
        post_account_snapshot=report.post_account_snapshot,
        positions_before=report.positions_before,
        positions_after=report.positions_after,
        open_orders_before=report.open_orders_before,
        open_orders_after=report.open_orders_after,
        artifact_path=str(path),
    )


def default_paper_broker_proof_schedule_windows() -> tuple[PaperBrokerProofScheduleWindow, ...]:
    return (
        PaperBrokerProofScheduleWindow("market_open", time(8, 30), time(10, 0), description="Opening regular-session micro-order broker proof."),
        PaperBrokerProofScheduleWindow("intraday", time(10, 0), time(14, 30), description="Intraday micro-order broker proof and cleanup."),
        PaperBrokerProofScheduleWindow("market_close", time(14, 30), time(15, 15), description="Closing regular-session broker proof before end-of-day reporting."),
        PaperBrokerProofScheduleWindow("end_of_day", time(15, 15), time(17, 0), submit_orders_allowed=False, required=False, description="No-submit broker-proof audit window."),
    )


def run_scheduled_paper_broker_proof(
    config: RuntimeConfig,
    broker_factory: Callable[[], Broker],
    order_plan: PaperBrokerOrderPlan,
    artifact_root: str | Path = "runs/paper-broker-proof",
    schedule_output_path: str | Path | None = None,
    options: PaperBrokerProofOptions | None = None,
    windows: tuple[PaperBrokerProofScheduleWindow, ...] | None = None,
) -> PaperBrokerProofScheduleReport:
    options = options or PaperBrokerProofOptions()
    now = options.now or datetime.now(timezone.utc)
    windows = tuple(windows or default_paper_broker_proof_schedule_windows())
    local_now = now.astimezone(ZoneInfo("America/Chicago")) if now.tzinfo else now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Chicago"))
    market_session = MarketSessionCalendar().session_at(now)
    active_window = None
    if market_session != MarketSession.CLOSED:
        active_window = next((window for window in windows if window.contains(local_now)), None)
    window_name = active_window.name if active_window else "outside_window"
    proof_output = Path(artifact_root) / f"{now.strftime('%Y%m%dT%H%M%SZ')}-{window_name}-paper-broker-proof.json"
    proof_options = PaperBrokerProofOptions(
        submit_orders=bool(active_window and active_window.submit_orders_allowed and options.submit_orders),
        cancel_after_submit=options.cancel_after_submit,
        allow_pre_market=options.allow_pre_market,
        allow_after_hours=options.allow_after_hours,
        fill_poll_attempts=options.fill_poll_attempts,
        fill_poll_interval_seconds=options.fill_poll_interval_seconds,
        approval_policy=options.approval_policy,
        prior_reports=options.prior_reports,
        now=now,
    )
    proof_report = run_paper_broker_proof(config, broker_factory, order_plan, proof_options, proof_output)
    record = ScheduledPaperBrokerProofRecord(window_name, now, proof_report)
    return evaluate_paper_broker_proof_schedule((record,), windows, active_window, schedule_output_path)


def run_scheduled_paper_broker_proof_from_artifact(
    proof_artifact_path: str | Path,
    schedule_output_path: str | Path | None = None,
    windows: tuple[PaperBrokerProofScheduleWindow, ...] | None = None,
) -> PaperBrokerProofScheduleReport:
    proof_path = Path(proof_artifact_path)
    payload = json.loads(proof_path.read_text(encoding="utf-8"))
    generated_at = _parse_report_datetime(payload.get("generated_at")) or datetime.now(timezone.utc)
    generated_at = generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=timezone.utc)
    windows = tuple(windows or default_paper_broker_proof_schedule_windows())
    local_generated_at = generated_at.astimezone(ZoneInfo("America/Chicago"))
    session = str(payload.get("session") or "")
    active_window = None
    if session != MarketSession.CLOSED.value:
        active_window = next((window for window in windows if window.contains(local_generated_at)), None)
    window_name = active_window.name if active_window else "outside_window"
    record = ScheduledPaperBrokerProofRecord(window_name, generated_at, payload)
    return evaluate_paper_broker_proof_schedule((record,), windows, active_window, schedule_output_path)


def evaluate_paper_broker_proof_schedule(
    records: tuple[ScheduledPaperBrokerProofRecord, ...],
    windows: tuple[PaperBrokerProofScheduleWindow, ...] | None = None,
    active_window: PaperBrokerProofScheduleWindow | None = None,
    output_path: str | Path | None = None,
) -> PaperBrokerProofScheduleReport:
    windows = tuple(windows or default_paper_broker_proof_schedule_windows())
    checks: list[Mapping[str, Any]] = []
    if active_window is None:
        checks.append({"name": "active_window", "passed": False, "reason": "no_active_broker_proof_window"})
    else:
        active_records = tuple(record for record in records if record.window_name == active_window.name)
        submitted_when_blocked = any(record.submitted for record in active_records) and not active_window.submit_orders_allowed
        proof_ok = (
            all(record.passed for record in active_records)
            if active_window.submit_orders_allowed
            else all(not record.submitted for record in active_records)
        )
        checks.extend(
            [
                {
                    "name": "active_window",
                    "passed": bool(active_records),
                    "reason": "passed" if active_records else "missing_active_window_record",
                    "window": active_window.name,
                    "records": len(active_records),
                },
                {
                    "name": "broker_proof_result",
                    "passed": proof_ok,
                    "reason": "passed" if proof_ok else "broker_proof_failed",
                    "window": active_window.name,
                    "submit_orders_allowed": active_window.submit_orders_allowed,
                },
                {
                    "name": "blocked_window_no_submit",
                    "passed": not submitted_when_blocked,
                    "reason": "passed" if not submitted_when_blocked else "orders_submitted_in_blocked_window",
                    "window": active_window.name,
                },
            ]
        )
    report = PaperBrokerProofScheduleReport(windows, tuple(records), tuple(checks))
    if output_path is None:
        return report
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["artifact_path"] = str(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return PaperBrokerProofScheduleReport(report.windows, report.records, report.checks, artifact_path=str(path))


def _first_failed_reason(probes: list[PaperBrokerProofProbe]) -> str:
    for probe in probes:
        if not probe.passed:
            return probe.reason
    return "passed"


def _policy_payload(policy: MarketSessionPolicy) -> dict:
    return {
        "allow_pre_market": policy.allow_pre_market,
        "allow_regular": policy.allow_regular,
        "allow_after_hours": policy.allow_after_hours,
    }


def _approval_policy_probes(
    order_plan: PaperBrokerOrderPlan,
    options: PaperBrokerProofOptions,
    now: datetime,
) -> list[PaperBrokerProofProbe]:
    policy = options.approval_policy
    if policy is None:
        return [
            PaperBrokerProofProbe(
                "approval_policy",
                True,
                "not_configured",
                {"configured": False},
            )
        ]
    symbol = order_plan.symbol.upper()
    allowlist = {item.upper() for item in policy.symbol_allowlist}
    submitted_today = _submitted_reports_today(options.prior_reports, now)
    repeated_rejects = _rejected_reports(options.prior_reports, symbol)
    max_daily_ok = policy.max_daily_submissions is None or submitted_today < policy.max_daily_submissions
    reject_ok = policy.repeated_reject_lockout_threshold is None or repeated_rejects < policy.repeated_reject_lockout_threshold
    return [
        PaperBrokerProofProbe(
            "approval_policy",
            True,
            "passed",
            {"configured": True, "policy": policy.to_dict()},
        ),
        PaperBrokerProofProbe(
            "approval_kill_switch",
            not policy.kill_switch_enabled,
            "passed" if not policy.kill_switch_enabled else "paper_proof_kill_switch_enabled",
            {"kill_switch_enabled": policy.kill_switch_enabled},
        ),
        PaperBrokerProofProbe(
            "approval_symbol_allowlist",
            not allowlist or symbol in allowlist,
            "passed" if not allowlist or symbol in allowlist else "symbol_not_allowed_for_paper_proof",
            {"symbol": symbol, "symbol_allowlist": sorted(allowlist)},
        ),
        PaperBrokerProofProbe(
            "approval_daily_submission_limit",
            max_daily_ok,
            "passed" if max_daily_ok else "max_daily_paper_proof_submissions_reached",
            {"submitted_today": submitted_today, "max_daily_submissions": policy.max_daily_submissions},
        ),
        PaperBrokerProofProbe(
            "approval_repeated_reject_lockout",
            reject_ok,
            "passed" if reject_ok else "repeated_reject_lockout_active",
            {"symbol": symbol, "rejected_reports": repeated_rejects, "threshold": policy.repeated_reject_lockout_threshold},
        ),
    ]


def _submitted_reports_today(reports: tuple[Mapping[str, Any], ...], now: datetime) -> int:
    current_date = now.date()
    count = 0
    for report in reports:
        if not report.get("submitted"):
            continue
        generated_at = _parse_report_datetime(report.get("generated_at"))
        if generated_at and generated_at.date() == current_date:
            count += 1
    return count


def _rejected_reports(reports: tuple[Mapping[str, Any], ...], symbol: str) -> int:
    rejected = 0
    for report in reports:
        plan = dict(report.get("order_plan", {}))
        if plan.get("symbol", "").upper() != symbol.upper():
            continue
        if report.get("reason") == "paper_order_rejected":
            rejected += 1
            continue
        for order in report.get("orders", []):
            if order.get("status") == "REJECTED":
                rejected += 1
                break
    return rejected


def _parse_report_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _proof_payload(report: PaperBrokerProofReport | Mapping[str, Any]) -> dict:
    if hasattr(report, "to_dict"):
        return report.to_dict()
    return dict(report)


def _poll_execution_reports(
    broker: Broker,
    orders: list[Order],
    attempts: int,
    interval_seconds: float,
) -> tuple[list[Mapping[str, Any]], str, str | None]:
    poller = getattr(broker, "poll_execution_reports", None)
    if not callable(poller):
        return [_execution_report_payload(report) for report in broker.execution_reports()], "local_execution_reports", None
    last_error: str | None = None
    max_attempts = max(int(attempts or 1), 1)
    for attempt in range(max_attempts):
        try:
            reports = [_execution_report_payload(report) for report in poller(orders)]
            if reports:
                return reports, "broker_poll_execution_reports", None
        except Exception as exc:
            last_error = str(exc)
        if attempt < max_attempts - 1 and interval_seconds > 0:
            sleep(interval_seconds)
    return [], "broker_poll_execution_reports", last_error or "no_polled_reports"


def _order_payload(order: Order) -> dict:
    return {
        "id": order.id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "order_type": order.order_type,
        "limit_price": order.limit_price,
        "status": order.status,
        "created_at": order.created_at.isoformat(),
    }


def _position_payload(position) -> dict:
    return {
        "symbol": position.symbol,
        "quantity": position.quantity,
        "average_entry_price": position.average_entry_price,
        "market_value": position.market_value,
        "raw": _redact_broker_payload(position.raw),
    }


def _execution_report_payload(report) -> dict:
    return {
        "order_id": report.order_id,
        "status": report.status,
        "broker_order_id": report.broker_order_id,
        "fill_id": report.fill_id,
        "filled_quantity": report.filled_quantity,
        "average_fill_price": report.average_fill_price,
        "submitted_at": report.submitted_at.isoformat(),
        "raw": _redact_broker_payload(report.raw),
    }


def _account_payload(account) -> dict:
    return {
        "cash": account.cash,
        "buying_power": account.buying_power,
        "equity": account.equity,
        "daytrade_count": account.daytrade_count,
        "pattern_day_trader": account.pattern_day_trader,
        "trading_blocked": account.trading_blocked,
        "account_blocked": account.account_blocked,
        "captured_at": account.captured_at.isoformat(),
        "raw": _redact_broker_payload(account.raw),
    }


_REDACTED_BROKER_KEYS = {
    "account_id",
    "account_number",
    "asset_id",
    "id",
    "user_id",
}


def _redact_broker_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in _REDACTED_BROKER_KEYS:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_broker_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_broker_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_broker_payload(item) for item in value)
    return value
