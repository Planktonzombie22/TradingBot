from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.config import settings as defaults


@dataclass(frozen=True)
class MarketDataConfig:
    symbol: str = defaults.MARKET
    period: str = defaults.PERIOD
    interval: str = defaults.INTERVAL
    start: Optional[str] = None
    end: Optional[str] = None
    provider: str = defaults.DATA_PROVIDER


@dataclass(frozen=True)
class AlpacaConfig:
    api_key: str = defaults.ALPACA_API_KEY
    secret_key: str = defaults.ALPACA_SECRET_KEY
    base_url: str = defaults.ALPACA_BASE_URL
    data_stream_url: str = defaults.ALPACA_DATA_STREAM_URL
    feed: str = "iex"


@dataclass(frozen=True)
class AccountConfig:
    initial_cash: float = defaults.ACCOUNT_SIZE
    margin_ratio: float = defaults.MARGIN_RATIO
    risk_fraction: float = defaults.PERCENTAGE_RISKED
    base_currency: str = "USD"


@dataclass(frozen=True)
class StrategyConfig:
    name: str = defaults.DEFAULT_STRATEGY
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str = defaults.EXECUTION_MODE
    allow_live_trading: bool = defaults.ALLOW_LIVE_TRADING
    state_db_path: str = defaults.STATE_DB_PATH


def _optional_float(value: str) -> Optional[float]:
    return float(value) if value else None


def _optional_int(value: str) -> Optional[int]:
    return int(value) if value else None


@dataclass(frozen=True)
class RuntimeRiskConfig:
    max_daily_loss: Optional[float] = _optional_float(defaults.MAX_DAILY_LOSS)
    max_drawdown: Optional[float] = _optional_float(defaults.MAX_DRAWDOWN)
    max_position_notional: Optional[float] = _optional_float(defaults.MAX_POSITION_NOTIONAL)
    max_order_notional: Optional[float] = _optional_float(defaults.MAX_ORDER_NOTIONAL)
    max_open_orders: Optional[int] = _optional_int(defaults.MAX_OPEN_ORDERS)
    max_orders_per_minute: Optional[int] = _optional_int(defaults.MAX_ORDERS_PER_MINUTE)


@dataclass(frozen=True)
class RuntimeConfig:
    paper_trading: bool = defaults.PAPER_TRADING
    data: MarketDataConfig = field(default_factory=MarketDataConfig)
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig)
    account: AccountConfig = field(default_factory=AccountConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    runtime_risk: RuntimeRiskConfig = field(default_factory=RuntimeRiskConfig)
