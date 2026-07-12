from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.backtesting import (
    PaperSessionManifest,
    PaperTradingScorecard,
    TradeCommitteeContext,
    TradeCommitteeDecision,
    TradeCommitteePolicy,
    decide_trade_action,
)
from src.execution import ExecutionReport, ReconciliationResult
from src.models import Order
from src.storage import ImmutableArtifactStore, RunManifest

from .account import PaperAccountState
from .committee import CommitteeExecutionPlan, CommitteeExecutionPolicy, plan_committee_execution


@dataclass(frozen=True)
class PaperSessionSupervisorConfig:
    mode: str = "dry-run"
    require_promotion_manifest: bool = True
    artifact_run_type: str = "paper-session-dry-run"
    data_source: Mapping[str, Any] = field(default_factory=lambda: {"provider": "runtime"})


@dataclass(frozen=True)
class PaperSessionSupervisorReport:
    manifest: RunManifest
    paper_manifest: PaperSessionManifest | None
    decision: TradeCommitteeDecision
    execution_plan: CommitteeExecutionPlan
    account_snapshot: Mapping[str, Any]
    latest_prices: Mapping[str, float]
    committee_context: Mapping[str, Any] = field(default_factory=dict)
    submitted_orders: tuple[Order, ...] = ()
    execution_reports: tuple[ExecutionReport, ...] = ()
    reconciliation: ReconciliationResult | None = None
    paper_scorecard: PaperTradingScorecard | None = None
    post_session_account_snapshot: Mapping[str, Any] | None = None
    artifact_paths: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def ready_for_submission(self) -> bool:
        return self.decision.approved and self.execution_plan.has_orders and not self.warnings

    def to_dict(self) -> dict:
        return {
            "manifest": self.manifest.to_dict(),
            "paper_manifest": self.paper_manifest.to_dict() if self.paper_manifest else None,
            "decision": self.decision.to_dict(),
            "execution_plan": self.execution_plan.to_dict(),
            "account_snapshot": dict(self.account_snapshot),
            "latest_prices": dict(self.latest_prices),
            "committee_context": dict(self.committee_context),
            "submitted_orders": [_order_payload(order) for order in self.submitted_orders],
            "execution_reports": [_execution_report_payload(report) for report in self.execution_reports],
            "reconciliation": _reconciliation_payload(self.reconciliation),
            "paper_scorecard": self.paper_scorecard.to_dict() if self.paper_scorecard else None,
            "post_session_account_snapshot": dict(self.post_session_account_snapshot) if self.post_session_account_snapshot else None,
            "artifact_paths": dict(self.artifact_paths),
            "warnings": list(self.warnings),
            "ready_for_submission": self.ready_for_submission,
        }


class PaperSessionSupervisor:
    def __init__(
        self,
        artifact_store: ImmutableArtifactStore | None = None,
        config: PaperSessionSupervisorConfig | None = None,
        committee_policy: TradeCommitteePolicy | None = None,
        execution_policy: CommitteeExecutionPolicy | None = None,
    ):
        self.artifact_store = artifact_store
        self.config = config or PaperSessionSupervisorConfig()
        self.committee_policy = committee_policy
        self.execution_policy = execution_policy

    def prepare_dry_run(
        self,
        context: TradeCommitteeContext,
        account_state: PaperAccountState,
        latest_prices: Mapping[str, float],
        decision: TradeCommitteeDecision | None = None,
    ) -> PaperSessionSupervisorReport:
        committee_decision = decision or decide_trade_action(context, self.committee_policy)
        execution_plan = plan_committee_execution(
            committee_decision,
            account_state,
            latest_prices,
            policy=self.execution_policy,
        )
        paper_manifest = _paper_manifest(context)
        warnings = tuple(_warnings(self.config, paper_manifest, execution_plan))
        run_manifest = _run_manifest(self.config, context, committee_decision, paper_manifest)
        account_snapshot = account_state.snapshot(dict(latest_prices))
        report = PaperSessionSupervisorReport(
            manifest=run_manifest,
            paper_manifest=paper_manifest,
            decision=committee_decision,
            execution_plan=execution_plan,
            account_snapshot=account_snapshot,
            latest_prices=dict(latest_prices),
            committee_context=_context_payload(context),
            warnings=warnings,
        )
        if self.artifact_store is None:
            return report
        return _write_artifacts(self.artifact_store, report)

    def write_audit_trail(
        self,
        report: PaperSessionSupervisorReport,
        submitted_orders: Sequence[Order] = (),
        execution_reports: Sequence[ExecutionReport] = (),
        reconciliation: ReconciliationResult | None = None,
        paper_scorecard: PaperTradingScorecard | None = None,
        post_session_account_snapshot: Mapping[str, Any] | None = None,
    ) -> PaperSessionSupervisorReport:
        audited_report = _copy_report(
            report,
            submitted_orders=tuple(submitted_orders),
            execution_reports=tuple(execution_reports),
            reconciliation=reconciliation,
            paper_scorecard=paper_scorecard,
            post_session_account_snapshot=dict(post_session_account_snapshot) if post_session_account_snapshot else None,
        )
        if self.artifact_store is None:
            return audited_report
        return _write_lifecycle_artifacts(self.artifact_store, audited_report)


def prepare_paper_session_dry_run(
    context: TradeCommitteeContext,
    account_state: PaperAccountState,
    latest_prices: Mapping[str, float],
    artifact_store: ImmutableArtifactStore | None = None,
    config: PaperSessionSupervisorConfig | None = None,
    committee_policy: TradeCommitteePolicy | None = None,
    execution_policy: CommitteeExecutionPolicy | None = None,
    decision: TradeCommitteeDecision | None = None,
) -> PaperSessionSupervisorReport:
    return PaperSessionSupervisor(
        artifact_store=artifact_store,
        config=config,
        committee_policy=committee_policy,
        execution_policy=execution_policy,
    ).prepare_dry_run(context, account_state, latest_prices, decision)


def write_paper_session_audit_trail(
    report: PaperSessionSupervisorReport,
    artifact_store: ImmutableArtifactStore | None = None,
    submitted_orders: Sequence[Order] = (),
    execution_reports: Sequence[ExecutionReport] = (),
    reconciliation: ReconciliationResult | None = None,
    paper_scorecard: PaperTradingScorecard | None = None,
    post_session_account_snapshot: Mapping[str, Any] | None = None,
) -> PaperSessionSupervisorReport:
    return PaperSessionSupervisor(artifact_store=artifact_store).write_audit_trail(
        report,
        submitted_orders=submitted_orders,
        execution_reports=execution_reports,
        reconciliation=reconciliation,
        paper_scorecard=paper_scorecard,
        post_session_account_snapshot=post_session_account_snapshot,
    )


def _run_manifest(
    config: PaperSessionSupervisorConfig,
    context: TradeCommitteeContext,
    decision: TradeCommitteeDecision,
    paper_manifest: PaperSessionManifest | None,
) -> RunManifest:
    strategy = decision.strategy_name or (paper_manifest.strategy_name if paper_manifest else "committee")
    return RunManifest.create(
        run_type=config.artifact_run_type,
        strategy=strategy,
        symbols=[context.symbol.upper()],
        config={
            "mode": config.mode,
            "committee_reason": decision.reason,
            "committee_action": decision.action,
            "paper_manifest_status": paper_manifest.manifest_status if paper_manifest else None,
        },
        data_source=config.data_source,
    )


def _paper_manifest(context: TradeCommitteeContext) -> PaperSessionManifest | None:
    if context.promotion_report is None:
        return None
    return context.promotion_report.manifest


def _warnings(
    config: PaperSessionSupervisorConfig,
    paper_manifest: PaperSessionManifest | None,
    execution_plan: CommitteeExecutionPlan,
) -> list[str]:
    warnings = list(execution_plan.warnings)
    if config.mode != "dry-run":
        warnings.append("Paper session supervisor only supports dry-run preparation in this MVP.")
    if config.require_promotion_manifest and paper_manifest is None:
        warnings.append("Missing promoted paper-session manifest.")
    return warnings


def _write_artifacts(
    artifact_store: ImmutableArtifactStore,
    report: PaperSessionSupervisorReport,
) -> PaperSessionSupervisorReport:
    artifact_paths: dict[str, str] = {}
    artifact_paths["manifest"] = _as_str(artifact_store.write_manifest(report.manifest))
    artifact_paths["committee_context"] = _as_str(artifact_store.write_json(report.manifest, "committee-context.json", report.committee_context))
    artifact_paths["committee_decision"] = _as_str(artifact_store.write_json(report.manifest, "committee-decision.json", report.decision.to_dict()))
    artifact_paths["execution_plan"] = _as_str(artifact_store.write_json(report.manifest, "execution-plan.json", report.execution_plan.to_dict()))
    artifact_paths["session_report"] = _as_str(artifact_store.run_dir(report.manifest) / "session-report.json")
    written_report = _copy_report(report, artifact_paths=artifact_paths)
    artifact_store.write_json(report.manifest, "session-report.json", written_report.to_dict(), overwrite=True)
    return written_report


def _write_lifecycle_artifacts(
    artifact_store: ImmutableArtifactStore,
    report: PaperSessionSupervisorReport,
) -> PaperSessionSupervisorReport:
    artifact_paths = dict(report.artifact_paths)
    artifact_paths["submitted_orders"] = _as_str(
        artifact_store.write_json(
            report.manifest,
            "submitted-orders.json",
            {"orders": [_order_payload(order) for order in report.submitted_orders]},
            overwrite=True,
        )
    )
    artifact_paths["execution_reports"] = _as_str(
        artifact_store.write_json(
            report.manifest,
            "execution-reports.json",
            {"reports": [_execution_report_payload(item) for item in report.execution_reports]},
            overwrite=True,
        )
    )
    artifact_paths["reconciliation"] = _as_str(
        artifact_store.write_json(
            report.manifest,
            "reconciliation.json",
            _reconciliation_payload(report.reconciliation) or {"orders": [], "is_clean": None, "unresolved": []},
            overwrite=True,
        )
    )
    artifact_paths["paper_scorecard"] = _as_str(
        artifact_store.write_json(
            report.manifest,
            "paper-scorecard.json",
            report.paper_scorecard.to_dict() if report.paper_scorecard else {"available": False},
            overwrite=True,
        )
    )
    artifact_paths["post_session_account"] = _as_str(
        artifact_store.write_json(
            report.manifest,
            "post-session-account.json",
            dict(report.post_session_account_snapshot or {}),
            overwrite=True,
        )
    )
    artifact_paths["session_report"] = _as_str(artifact_store.run_dir(report.manifest) / "session-report.json")
    written_report = _copy_report(report, artifact_paths=artifact_paths)
    artifact_store.write_json(report.manifest, "session-report.json", written_report.to_dict(), overwrite=True)
    return written_report


def _copy_report(
    report: PaperSessionSupervisorReport,
    committee_context: Mapping[str, Any] | None = None,
    submitted_orders: tuple[Order, ...] | None = None,
    execution_reports: tuple[ExecutionReport, ...] | None = None,
    reconciliation: ReconciliationResult | None = None,
    paper_scorecard: PaperTradingScorecard | None = None,
    post_session_account_snapshot: Mapping[str, Any] | None = None,
    artifact_paths: Mapping[str, str] | None = None,
) -> PaperSessionSupervisorReport:
    return PaperSessionSupervisorReport(
        manifest=report.manifest,
        paper_manifest=report.paper_manifest,
        decision=report.decision,
        execution_plan=report.execution_plan,
        account_snapshot=report.account_snapshot,
        latest_prices=report.latest_prices,
        committee_context=report.committee_context if committee_context is None else committee_context,
        submitted_orders=report.submitted_orders if submitted_orders is None else submitted_orders,
        execution_reports=report.execution_reports if execution_reports is None else execution_reports,
        reconciliation=report.reconciliation if reconciliation is None else reconciliation,
        paper_scorecard=report.paper_scorecard if paper_scorecard is None else paper_scorecard,
        post_session_account_snapshot=(
            report.post_session_account_snapshot if post_session_account_snapshot is None else post_session_account_snapshot
        ),
        artifact_paths=report.artifact_paths if artifact_paths is None else artifact_paths,
        warnings=report.warnings,
    )


def _context_payload(context: TradeCommitteeContext) -> dict:
    return {
        "symbol": context.symbol,
        "promotion_report": context.promotion_report.to_dict() if context.promotion_report else None,
        "paper_scorecard": context.paper_scorecard.to_dict() if context.paper_scorecard else None,
        "data_drift_reports": [_payload_or_dict(report) for report in context.data_drift_reports],
        "regime": _payload_or_dict(context.regime) if context.regime else None,
        "strategy_edge": context.strategy_edge,
        "benchmark_edge": context.benchmark_edge,
        "current_exposure": context.current_exposure,
        "risk_halt": context.risk_halt,
        "risk_reason": context.risk_reason,
        "notes": list(context.notes),
    }


def _order_payload(order: Order) -> dict:
    return {
        "id": order.id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "order_type": order.order_type,
        "limit_price": order.limit_price,
        "stop_price": order.stop_price,
        "take_profit_price": order.take_profit_price,
        "trail_percent": order.trail_percent,
        "time_in_force": order.time_in_force,
        "parent_order_id": order.parent_order_id,
        "order_group_id": order.order_group_id,
        "status": order.status,
        "created_at": order.created_at.isoformat(),
    }


def _execution_report_payload(report: ExecutionReport) -> dict:
    return {
        "order_id": report.order_id,
        "status": report.status,
        "broker_order_id": report.broker_order_id,
        "fill_id": report.fill_id,
        "filled_quantity": report.filled_quantity,
        "average_fill_price": report.average_fill_price,
        "submitted_at": report.submitted_at.isoformat(),
        "raw": dict(report.raw),
    }


def _reconciliation_payload(reconciliation: ReconciliationResult | None) -> dict | None:
    if reconciliation is None:
        return None
    return {
        "is_clean": reconciliation.is_clean,
        "captured_at": reconciliation.captured_at.isoformat(),
        "unresolved": [_order_reconciliation_payload(item) for item in reconciliation.unresolved],
        "orders": [_order_reconciliation_payload(item) for item in reconciliation.orders],
    }


def _order_reconciliation_payload(item) -> dict:
    status = item.status.value if hasattr(item.status, "value") else item.status
    return {
        "order_id": item.order_id,
        "status": status,
        "local_status": item.local_status,
        "broker_status": item.broker_status,
        "broker_order_id": item.broker_order_id,
        "message": item.message,
    }


def _payload_or_dict(item) -> dict:
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if isinstance(item, Mapping):
        return dict(item)
    return {"value": str(item)}


def _as_str(path: Path) -> str:
    return str(path)
