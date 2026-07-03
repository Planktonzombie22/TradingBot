from src.app import TradingApplication
import pytest

from src.config import AlpacaConfig, ExecutionConfig, MarketDataConfig, RuntimeConfig, StrategyConfig
from src.engine import EngineEventType
from src.execution import AlpacaPaperBroker, PaperBroker


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


def test_application_uses_dry_run_broker_by_default_for_alpaca():
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="alpaca", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
            alpaca=AlpacaConfig(api_key="key", secret_key="secret"),
        )
    )

    assert isinstance(app.create_broker(), PaperBroker)


def test_application_requires_explicit_safe_paper_execution_for_alpaca_broker():
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="alpaca", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
            alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://paper-api.alpaca.markets"),
            execution=ExecutionConfig(mode="paper"),
        )
    )

    assert isinstance(app.create_broker(), AlpacaPaperBroker)


def test_application_blocks_non_paper_alpaca_url_without_live_unlock():
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="alpaca", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
            alpaca=AlpacaConfig(api_key="key", secret_key="secret", base_url="https://api.alpaca.markets"),
            execution=ExecutionConfig(mode="paper", allow_live_trading=False),
        )
    )

    with pytest.raises(ValueError, match="non-paper URL"):
        app.create_broker()
