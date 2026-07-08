from src.config import load_runtime_config


def test_load_runtime_config_applies_cli_overrides():
    config = load_runtime_config(
        {
            "symbol": "QQQ",
            "provider": "alpaca",
            "interval": "5m",
            "strategy": "buyHold",
            "initial_cash": 25_000,
            "execution_mode": "paper",
            "state_db_path": "runs/test.sqlite3",
        }
    )

    assert config.data.symbol == "QQQ"
    assert config.data.provider == "alpaca"
    assert config.data.interval == "5m"
    assert config.strategy.name == "buyHold"
    assert config.account.initial_cash == 25_000
    assert config.execution.mode == "paper"
    assert config.execution.state_db_path == "runs/test.sqlite3"


def test_load_runtime_config_allows_explicit_period_none_for_date_windows():
    config = load_runtime_config(
        {
            "symbol": "AAPL",
            "provider": "yfinance",
            "period": None,
            "start": "2020-01-01",
            "end": "2024-01-01",
        }
    )

    assert config.data.period is None
    assert config.data.start == "2020-01-01"
    assert config.data.end == "2024-01-01"
