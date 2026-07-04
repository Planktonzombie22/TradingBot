from datetime import datetime, timedelta, timezone

import pytest

from src.execution import (
    BrokerCapabilityProfile,
    BracketOrderPlan,
    EndOfDayAction,
    EndOfDayPolicy,
    GeneratedOrderIntent,
    OCOOrderPlan,
    OrderReplacementPolicy,
    SignalIntent,
    TargetPositionIntent,
    validate_order_capabilities,
)
from src.models import Order, Signal


def test_order_intents_preserve_lifecycle_lineage():
    signal = Signal("BUY", "SPY", datetime.now(timezone.utc), stop_loss=99)
    signal_intent = SignalIntent(signal=signal, strategy_name="test")
    target = TargetPositionIntent(symbol="SPY", target_quantity=10, source_signal=signal_intent)
    generated = GeneratedOrderIntent(order=Order("SPY", "BUY", 10), source_target=target)

    assert generated.source_target is target
    assert target.source_signal is signal_intent
    assert signal_intent.signal.symbol == "SPY"


def test_order_replacement_policy_chases_stale_limit_order():
    old_order = Order(
        "SPY",
        "BUY",
        1,
        order_type="LIMIT",
        limit_price=99,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    decision = OrderReplacementPolicy(stale_after_seconds=60, limit_chase_bps=10).evaluate(old_order, reference_price=100)

    assert decision.should_replace
    assert decision.replacement.limit_price == pytest.approx(100.1)


def test_order_replacement_policy_cancels_stale_market_order():
    old_order = Order(
        "SPY",
        "BUY",
        1,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    decision = OrderReplacementPolicy(stale_after_seconds=60).evaluate(old_order, reference_price=100)

    assert decision.should_cancel


def test_bracket_and_oco_plans_validate_broker_capabilities():
    bracket = BracketOrderPlan.market_entry("SPY", "BUY", 1, stop_price=95, take_profit_price=110)
    oco = OCOOrderPlan(bracket.orders()[1:])

    assert len(bracket.orders()) == 3
    assert bracket.stop_loss.parent_order_id == bracket.entry.id
    bracket.validate(BrokerCapabilityProfile(supports_bracket=True))
    oco.validate(BrokerCapabilityProfile(supports_oco=True))

    with pytest.raises(ValueError):
        bracket.validate(BrokerCapabilityProfile(supports_bracket=False))


def test_order_capability_validation_rejects_unsupported_trailing_stop():
    order = Order("SPY", "SELL", 1, order_type="TRAILING_STOP", trail_percent=0.05)

    with pytest.raises(ValueError, match="trailing-stop"):
        validate_order_capabilities([order], BrokerCapabilityProfile(supports_trailing_stop=False))


def test_end_of_day_policy_triggers_after_cutoff():
    policy = EndOfDayPolicy(action=EndOfDayAction.FLATTEN)

    assert not policy.should_apply(datetime.fromisoformat("2024-01-02T15:30:00-05:00"))
    assert policy.should_apply(datetime.fromisoformat("2024-01-02T15:56:00-05:00"))
    assert policy.action_payload()["action"] == "FLATTEN"
