from src.risk import PositionSizer, PositionSizingRequest, RiskManager
from src.models import Signal


def test_position_sizer_uses_stop_distance_and_buying_power():
    sizer = PositionSizer()

    quantity = sizer.size_from_stop(
        PositionSizingRequest(
            equity=10_000,
            entry_price=100,
            stop_price=95,
            risk_fraction=0.02,
            buying_power=5_000,
        )
    )

    assert quantity == 40


def test_risk_manager_rejects_zero_size_signal():
    manager = RiskManager()
    signal = Signal(action="BUY", symbol="SPY", timestamp="2024-01-01", stop_loss=100)

    decision = manager.order_from_signal(
        signal=signal,
        equity=10_000,
        price=100,
        risk_fraction=0.01,
    )

    assert not decision.accepted
    assert decision.order is None


def test_risk_manager_sizes_target_notional_fraction_signal():
    manager = RiskManager()
    signal = Signal(
        action="BUY",
        symbol="SPY",
        timestamp="2024-01-01",
        meta={"target_notional_fraction": 0.5},
    )

    decision = manager.order_from_signal(
        signal=signal,
        equity=10_000,
        price=100,
        risk_fraction=0.01,
        buying_power=7_500,
    )

    assert decision.accepted
    assert decision.order is not None
    assert decision.order.quantity == 50
    assert decision.order.stop_price is None
