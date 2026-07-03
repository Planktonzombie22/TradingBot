from src.config import MarketDataConfig, RuntimeConfig, RuntimeRiskConfig, StrategyConfig, load_runtime_config
from src.app import TradingApplication
from src.engine import EngineEventType, EngineState
from src.models import Order


def test_runtime_risk_config_accepts_overrides():
    config = load_runtime_config(
        {
            "max_daily_loss": 100,
            "max_drawdown": 0.1,
            "max_position_notional": 500,
            "max_order_notional": 250,
            "max_open_orders": 2,
            "max_orders_per_minute": 5,
        }
    )

    assert config.runtime_risk.max_daily_loss == 100
    assert config.runtime_risk.max_drawdown == 0.1
    assert config.runtime_risk.max_position_notional == 500
    assert config.runtime_risk.max_order_notional == 250
    assert config.runtime_risk.max_open_orders == 2
    assert config.runtime_risk.max_orders_per_minute == 5


def test_runtime_halts_before_oversized_order():
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
            runtime_risk=RuntimeRiskConfig(max_order_notional=1),
        )
    )
    engine = app.create_engine()
    events = []
    engine.add_handler(events.append)

    engine.start()

    assert engine.state == EngineState.HALTED
    assert engine.account_state.quantity("SPY") == 0
    assert any(event.event_type == EngineEventType.HALT for event in events)


def test_disable_new_orders_blocks_signal_execution():
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )
    engine = app.create_engine()
    engine.disable_orders()

    engine.start()

    assert engine.account_state.quantity("SPY") == 0
    assert engine.state == EngineState.RUNNING


def test_kill_switch_cancels_orders_flattens_positions_and_halts():
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )
    engine = app.create_engine()
    entry = Order(symbol="SPY", side="BUY", quantity=2)
    filled = engine.broker.submit_order(entry)
    engine.account_state.apply_fill(filled, 100)
    engine.last_prices["SPY"] = 101

    engine.kill_switch("Operator requested stop.")

    assert engine.state == EngineState.HALTED
    assert engine.disable_new_orders
    assert engine.account_state.quantity("SPY") == 0
