from src.app import TradingApplication
from src.config import MarketDataConfig, RuntimeConfig, StrategyConfig
from src.engine import EngineEventType


def sample_app() -> TradingApplication:
    return TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )


def test_application_runs_sample_backtest_end_to_end():
    app = sample_app()

    result = app.run_backtest()

    assert len(result.fills) == 2
    assert len(result.trades) == 1
    assert result.metrics["ending_equity"] > 0


def test_application_runs_sample_stream_through_engine():
    app = sample_app()
    engine = app.create_engine()
    events = []
    engine.add_handler(events.append)

    engine.start()
    engine.stop()

    event_types = [event.event_type for event in events]
    assert EngineEventType.STARTED in event_types
    assert EngineEventType.ORDER in event_types
    assert EngineEventType.FILL in event_types
    assert EngineEventType.STOPPED in event_types
    assert engine.account_state.cash < engine.account.initial_cash
    assert engine.account_state.quantity("SPY") > 0
