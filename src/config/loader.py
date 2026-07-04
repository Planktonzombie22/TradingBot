from dataclasses import replace
from typing import Any, Mapping, Optional

from .profiles import (
    AccountConfig,
    AlpacaConfig,
    ExecutionConfig,
    MarketDataConfig,
    RuntimeConfig,
    RuntimeRiskConfig,
    StrategyScheduleConfig,
    StrategyConfig,
    UniverseRuntimeConfig,
)


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
    schedule = config.schedule
    alpaca = config.alpaca
    universe = config.universe
    execution = config.execution
    runtime_risk = config.runtime_risk

    data_keys = {"symbol", "period", "interval", "start", "end", "provider"}
    account_keys = {"initial_cash", "margin_ratio", "risk_fraction", "base_currency"}
    strategy_keys = {"strategy", "strategy_name", "strategy_params"}
    schedule_keys = {"schedule_timeframe", "warmup_bars", "allow_pre_market", "allow_after_hours"}
    universe_keys = {"watchlist_path", "universe_screen"}
    alpaca_keys = {"api_key", "secret_key", "base_url", "data_stream_url", "feed"}
    execution_keys = {"allow_live_trading", "state_db_path"}
    runtime_risk_keys = {
        "max_daily_loss",
        "max_drawdown",
        "max_position_notional",
        "max_order_notional",
        "max_open_orders",
        "max_orders_per_minute",
    }

    data_updates = {key: overrides[key] for key in data_keys if key in overrides and overrides[key] is not None}
    account_updates = {key: overrides[key] for key in account_keys if key in overrides and overrides[key] is not None}
    alpaca_updates = {key: overrides[key] for key in alpaca_keys if key in overrides and overrides[key] is not None}
    universe_updates = {}
    schedule_updates = {}
    if "symbols" in overrides and overrides["symbols"] is not None:
        value = overrides["symbols"]
        universe_updates["symbols"] = tuple(value if isinstance(value, (list, tuple)) else str(value).split(","))
    if "watchlist_path" in overrides and overrides["watchlist_path"] is not None:
        universe_updates["watchlist_path"] = overrides["watchlist_path"]
    if "universe_screen" in overrides and overrides["universe_screen"] is not None:
        universe_updates["screen"] = overrides["universe_screen"]
    if "schedule_timeframe" in overrides and overrides["schedule_timeframe"] is not None:
        schedule_updates["timeframe"] = overrides["schedule_timeframe"]
    for key in {"warmup_bars", "allow_pre_market", "allow_after_hours"}:
        if key in overrides and overrides[key] is not None:
            schedule_updates[key] = overrides[key]
    execution_updates = {key: overrides[key] for key in execution_keys if key in overrides and overrides[key] is not None}
    runtime_risk_updates = {key: overrides[key] for key in runtime_risk_keys if key in overrides and overrides[key] is not None}
    if "execution_mode" in overrides and overrides["execution_mode"] is not None:
        execution_updates["mode"] = overrides["execution_mode"]

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
    if universe_updates:
        universe = replace(universe, **universe_updates)
    if schedule_updates:
        schedule = replace(schedule, **schedule_updates)
    if execution_updates:
        execution = replace(execution, **execution_updates)
    if runtime_risk_updates:
        runtime_risk = replace(runtime_risk, **runtime_risk_updates)

    return RuntimeConfig(
        paper_trading=overrides.get("paper_trading", config.paper_trading),
        data=data,
        alpaca=alpaca,
        universe=universe,
        account=account,
        strategy=strategy,
        schedule=schedule,
        execution=execution,
        runtime_risk=runtime_risk,
    )
