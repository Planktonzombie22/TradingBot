import json

from src.backtesting import (
    PaperSessionManifest,
    PromotionPipelinePolicy,
    PromotionPipelineReport,
    ResearchCandidateEvidence,
    TradeCommitteeContext,
    TradeCommitteeDecision,
)
from src.engine import (
    CommitteeExecutionPolicy,
    PaperAccountState,
    RuntimePosition,
    plan_committee_execution,
    prepare_paper_session_dry_run,
)
from src.storage import ImmutableArtifactStore


def test_committee_trade_strategy_decision_generates_target_buy_order():
    account = PaperAccountState(100_000)
    decision = _decision("trade_strategy", target_weight=0.25)

    plan = plan_committee_execution(decision, account, {"SPY": 100.0})

    assert plan.has_orders
    assert plan.targets[0].target_quantity == 250
    assert plan.orders[0].order.side == "BUY"
    assert plan.orders[0].order.quantity == 250
    assert plan.orders[0].source_target is plan.targets[0]


def test_committee_cash_decision_flattens_existing_positions():
    account = PaperAccountState(100_000)
    account.positions["SPY"] = _position("SPY", 40, 100)
    account.positions["QQQ"] = _position("QQQ", -10, 300)
    decision = _decision("cash", target_weight=0.0)

    plan = plan_committee_execution(decision, account, {"SPY": 100.0, "QQQ": 300.0})
    orders = {intent.order.symbol: intent.order for intent in plan.orders}

    assert plan.reason == "cash_flatten_plan"
    assert orders["SPY"].side == "SELL"
    assert orders["SPY"].quantity == 40
    assert orders["QQQ"].side == "BUY"
    assert orders["QQQ"].quantity == 10


def test_committee_reduce_exposure_sells_down_to_target_weight():
    account = PaperAccountState(100_000)
    account.positions["SPY"] = _position("SPY", 300, 100)
    account.cash = 70_000
    decision = _decision("reduce_exposure", target_weight=0.10)

    plan = plan_committee_execution(decision, account, {"SPY": 100.0})

    assert plan.targets[0].target_quantity == 100
    assert plan.orders[0].order.side == "SELL"
    assert plan.orders[0].order.quantity == 200


def test_committee_hedge_decision_targets_default_hedge_symbol():
    account = PaperAccountState(100_000)
    decision = _decision("hedge", target_weight=0.25, hedge_weight=0.05)

    plan = plan_committee_execution(
        decision,
        account,
        {"SPY": 100.0, "SH": 20.0},
        policy=CommitteeExecutionPolicy(default_hedge_symbol="SH"),
    )

    assert plan.targets[0].symbol == "SH"
    assert plan.targets[0].target_quantity == 250
    assert plan.orders[0].order.side == "BUY"
    assert plan.orders[0].order.quantity == 250


def test_committee_plan_warns_and_holds_when_price_is_missing():
    account = PaperAccountState(100_000)
    decision = _decision("trade_strategy", target_weight=0.25)

    plan = plan_committee_execution(decision, account, {})

    assert not plan.has_orders
    assert plan.warnings == ("Missing valid price for SPY.",)


def test_paper_session_supervisor_writes_dry_run_artifacts(tmp_path):
    account = PaperAccountState(100_000)
    decision = _decision("trade_strategy", target_weight=0.25)

    report = prepare_paper_session_dry_run(
        _committee_context(with_manifest=True),
        account,
        {"SPY": 100.0},
        artifact_store=ImmutableArtifactStore(tmp_path),
        decision=decision,
    )

    assert report.ready_for_submission
    assert report.paper_manifest is not None
    assert report.execution_plan.orders[0].order.quantity == 250
    assert set(report.artifact_paths) == {"manifest", "committee_decision", "execution_plan", "session_report"}
    session_payload = json.loads(open(report.artifact_paths["session_report"], encoding="utf-8").read())
    assert session_payload["ready_for_submission"]
    assert session_payload["manifest"]["run_type"] == "paper-session-dry-run"


def test_paper_session_supervisor_requires_promoted_manifest_before_submit_ready():
    report = prepare_paper_session_dry_run(
        _committee_context(with_manifest=False),
        PaperAccountState(100_000),
        {"SPY": 100.0},
        decision=_decision("trade_strategy", target_weight=0.25),
    )

    assert not report.ready_for_submission
    assert "Missing promoted paper-session manifest." in report.warnings
    assert report.execution_plan.has_orders


def _decision(action: str, target_weight: float, hedge_weight: float = 0.0) -> TradeCommitteeDecision:
    return TradeCommitteeDecision(
        symbol="SPY",
        action=action,
        target_weight=target_weight,
        strategy_name="buyHold",
        hedge_weight=hedge_weight,
        reason="test_decision",
        gates=(),
    )


def _committee_context(with_manifest: bool):
    evidence = ResearchCandidateEvidence(strategy_name="buyHold", symbol="SPY")
    promotion = PromotionPipelineReport(
        evidence=evidence,
        policy=PromotionPipelinePolicy(),
        gates=(),
        manifest=PaperSessionManifest("buyHold", "SPY", {"target_fraction": 1.0}) if with_manifest else None,
    )
    return TradeCommitteeContext(
        symbol="SPY",
        promotion_report=promotion,
    )


def _position(symbol: str, quantity: float, price: float):
    return RuntimePosition(symbol, quantity, price)
