from dataclasses import replace
from typing import Any, Mapping, Optional

from .profiles import AccountConfig, AlpacaConfig, MarketDataConfig, RuntimeConfig, StrategyConfig


def load_runtime_config(overrides: Optional[Mapping[str, Any]] = None) -> RuntimeConfig:
    """Build RuntimeConfig from defaults and explicit override keys.

    Environment variables are loaded by `settings.py` before profile defaults are
    created. This function is the merge point for CLI or programmatic overrides.
    """

    overrides = dict(overrides or {})
    config = RuntimeConfig()
    data = config.data
    account = config.account
    strategy = config.strategy
    alpaca = config.alpaca

    data_keys = {"symbol", "period", "interval", "start", "end", "provider"}
    account_keys = {"initial_cash", "margin_ratio", "risk_fraction", "base_currency"}
    strategy_keys = {"strategy", "strategy_name", "strategy_params"}
    alpaca_keys = {"api_key", "secret_key", "base_url", "data_stream_url", "feed"}

    data_updates = {key: overrides[key] for key in data_keys if key in overrides and overrides[key] is not None}
    account_updates = {key: overrides[key] for key in account_keys if key in overrides and overrides[key] is not None}
    alpaca_updates = {key: overrides[key] for key in alpaca_keys if key in overrides and overrides[key] is not None}

    if "strategy" in overrides and overrides["strategy"] is not None:
        strategy = replace(strategy, name=overrides["strategy"])
    if "strategy_name" in overrides and overrides["strategy_name"] is not None:
        strategy = replace(strategy, name=overrides["strategy_name"])
    if "strategy_params" in overrides and overrides["strategy_params"] is not None:
        strategy = replace(strategy, params=dict(overrides["strategy_params"]))

    if data_updates:
        data = replace(data, **data_updates)
    if account_updates:
        account = replace(account, **account_updates)
    if alpaca_updates:
        alpaca = replace(alpaca, **alpaca_updates)

    return RuntimeConfig(
        paper_trading=overrides.get("paper_trading", config.paper_trading),
        data=data,
        alpaca=alpaca,
        account=account,
        strategy=strategy,
    )
