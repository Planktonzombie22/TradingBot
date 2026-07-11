from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from src.backtesting import (
    PaperSessionManifest,
    TradeCommitteeContext,
    TradeCommitteeDecision,
    TradeCommitteePolicy,
    decide_trade_action,
)
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
            warnings=warnings,
        )
        if self.artifact_store is None:
            return report
        return _write_artifacts(self.artifact_store, report)


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
    artifact_paths["committee_decision"] = _as_str(artifact_store.write_json(report.manifest, "committee-decision.json", report.decision.to_dict()))
    artifact_paths["execution_plan"] = _as_str(artifact_store.write_json(report.manifest, "execution-plan.json", report.execution_plan.to_dict()))
    payload = report.to_dict()
    payload["artifact_paths"] = artifact_paths
    artifact_paths["session_report"] = _as_str(artifact_store.write_json(report.manifest, "session-report.json", payload))
    return PaperSessionSupervisorReport(
        manifest=report.manifest,
        paper_manifest=report.paper_manifest,
        decision=report.decision,
        execution_plan=report.execution_plan,
        account_snapshot=report.account_snapshot,
        latest_prices=report.latest_prices,
        artifact_paths=artifact_paths,
        warnings=report.warnings,
    )


def _as_str(path: Path) -> str:
    return str(path)
