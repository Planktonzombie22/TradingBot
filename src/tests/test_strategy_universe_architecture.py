from datetime import datetime

import pandas as pd

from src.app import TradingApplication
from src.config import RuntimeConfig, StrategyScheduleConfig, UniverseRuntimeConfig, load_runtime_config
from src.data import UniverseConfig, UniverseLoader
from src.models import Signal
from src.strategies import (
    ParameterSpec,
    Strategy,
    get_strategy,
    register_strategy,
    strategy_schema,
    validate_strategy_params,
)
from src.strategies.scheduling import StrategySchedule


class RegisteredTestStrategy(Strategy):
    def __init__(self, symbol: str, threshold: float = 1.0):
        super().__init__(symbol)
        self.threshold = threshold

    def generate_signals(self, df):
        return pd.Series([Signal.hold(self.symbol, index) for index in df.index], index=df.index, dtype=object)


def test_universe_loader_reads_json_watchlists_and_dedupes(tmp_path):
    watchlist = tmp_path / "watchlist.json"
    watchlist.write_text('{"symbols":["spy","QQQ","SPY"]}', encoding="utf-8")

    symbols = UniverseLoader().load(UniverseConfig(symbols=("iwm",), watchlist_path=str(watchlist)))

    assert symbols == ["IWM", "SPY", "QQQ"]


def test_universe_loader_reads_grouped_cross_asset_files(tmp_path):
    watchlist = tmp_path / "groups.json"
    watchlist.write_text(
        '{"stocks":["aapl","MSFT"],"crypto":{"symbols":["BTC-USD","ETH-USD"]},"bonds":["TLT"]}',
        encoding="utf-8",
    )

    all_symbols = UniverseLoader().load(UniverseConfig(watchlist_path=str(watchlist)))
    selected = UniverseLoader().load(UniverseConfig(watchlist_path=str(watchlist), groups=("crypto", "bonds")))

    assert all_symbols == ["AAPL", "MSFT", "BTC-USD", "ETH-USD", "TLT"]
    assert selected == ["BTC-USD", "ETH-USD", "TLT"]


def test_universe_loader_filters_broker_assets_and_research_screen():
    loader = UniverseLoader()
    assets = [{"symbol": "SPY", "tradable": True}, {"symbol": "HALT", "tradable": False}]
    screen_data = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "Volume": [100, 300, 200],
            "Close": [10, 20, 30],
        }
    )

    broker_symbols = loader.from_broker_assets(assets)
    screen_symbols = loader.from_screen("top_volume", screen_data, limit=2)

    assert broker_symbols == ["SPY"]
    assert screen_symbols == ["BBB", "CCC"]


def test_strategy_registration_and_serializable_schema():
    register_strategy(
        "registeredTest",
        RegisteredTestStrategy,
        parameters={
            "threshold": ParameterSpec(
                "threshold",
                default=1.0,
                type_=float,
                minimum=0.0,
                maximum=10.0,
                description="Test threshold",
                optimize_values=[0.5, 1.0, 2.0],
            )
        },
        replace=True,
    )

    assert get_strategy("registeredTest") is RegisteredTestStrategy
    assert validate_strategy_params("registeredTest", {"threshold": "2.5"})["threshold"] == 2.5
    schema = strategy_schema("registeredTest")
    assert schema["parameters"]["threshold"]["type"] == "float"
    assert schema["parameters"]["threshold"]["optimize_values"] == [0.5, 1.0, 2.0]


def test_strategy_schedule_respects_symbol_session_and_warmup():
    schedule = StrategySchedule(symbols=("SPY",), timeframe="1Min", warmup_bars=3)

    assert not schedule.should_run("QQQ", datetime.fromisoformat("2024-01-02T10:00:00-05:00"), 5)
    assert not schedule.should_run("SPY", datetime.fromisoformat("2024-01-02T10:00:00-05:00"), 2)
    assert not schedule.should_run("SPY", datetime.fromisoformat("2024-01-02T08:00:00-05:00"), 5)
    assert schedule.should_run("SPY", datetime.fromisoformat("2024-01-02T10:00:00-05:00"), 5)


def test_runtime_config_and_app_expose_universe_and_schedule():
    config = load_runtime_config(
        {
            "symbols": "SPY,QQQ",
            "schedule_timeframe": "5Min",
            "warmup_bars": 10,
            "allow_pre_market": True,
        }
    )
    app = TradingApplication(
        RuntimeConfig(
            universe=UniverseRuntimeConfig(symbols=config.universe.symbols),
            schedule=StrategyScheduleConfig(
                timeframe=config.schedule.timeframe,
                warmup_bars=config.schedule.warmup_bars,
                allow_pre_market=config.schedule.allow_pre_market,
            ),
        )
    )

    assert config.universe.symbols == ("SPY", "QQQ")
    assert config.schedule.timeframe == "5Min"
    assert app.load_universe() == ["SPY", "QQQ"]
    assert app.create_strategy_schedule().warmup_bars == 10
