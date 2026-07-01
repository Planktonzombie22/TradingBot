#cspell:words Backtest pydatetime
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Sequence

import pandas as pd

from src.config import settings as cfg
from src.models import Order, Signal


class BacktestEventType(str, Enum):
    """Important state transitions emitted during a simulation."""

    BAR = "BAR"
    SIGNAL = "SIGNAL"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_FILLED = "ORDER_FILLED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    MARGIN_CALL = "MARGIN_CALL"
    CASH_ADJUSTMENT = "CASH_ADJUSTMENT"
    SESSION_CLOSED = "SESSION_CLOSED"


class RejectionReason(str, Enum):
    """Why an order did not reach execution."""

    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    RISK_LIMIT = "RISK_LIMIT"
    MARKET_CLOSED = "MARKET_CLOSED"
    INVALID_ORDER = "INVALID_ORDER"
    NOT_TRIGGERED = "NOT_TRIGGERED"


@dataclass(frozen=True)
class BacktestConfig:
    """Top-level knobs that should be explicit for every simulation run."""

    initial_cash: float = cfg.ACCOUNT_SIZE
    base_currency: str = "USD"
    margin_ratio: float = cfg.MARGIN_RATIO
    risk_fraction: float = cfg.PERCENTAGE_RISKED
    allow_shorting: bool = True
    allow_fractional_shares: bool = True
    mark_price_column: str = "Close"
    execution_price_column: str = "Close"
    warmup_bars: int = 0
    force_flat_at_end: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketSnapshot:
    """Normalized view of one historical step."""

    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, symbol: str, timestamp: Any, row: pd.Series) -> "MarketSnapshot":
        ts = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
        return cls(
            timestamp=ts,
            symbol=symbol,
            open=float(row.get("Open", row.get("Close"))),
            high=float(row.get("High", row.get("Close"))),
            low=float(row.get("Low", row.get("Close"))),
            close=float(row.get("Close")),
            volume=float(row["Volume"]) if "Volume" in row and pd.notna(row["Volume"]) else None,
            raw=row.to_dict(),
        )

    def price(self, column: str) -> float:
        key = column.lower()
        if key == "open":
            return self.open
        if key == "high":
            return self.high
        if key == "low":
            return self.low
        return self.close


@dataclass(frozen=True)
class BacktestEvent:
    """Append-only audit record for replaying or debugging a run."""

    timestamp: datetime
    event_type: BacktestEventType
    message: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Fill:
    """Execution result after slippage, fees, and liquidity constraints."""

    order: Order
    timestamp: datetime
    quantity: float
    price: float
    commission: float = 0.0
    slippage: float = 0.0
    liquidity_fraction: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass(frozen=True)
class OrderRejection:
    """Structured rejection so invalid assumptions are visible in reports."""

    order: Order
    timestamp: datetime
    reason: RejectionReason
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountSnapshot:
    """Portfolio/account state captured at a point in simulated time."""

    timestamp: datetime
    cash: float
    equity: float
    buying_power: float
    used_margin: float = 0.0
    maintenance_margin: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    positions: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalContext:
    """Everything strategy/order translation should know about a bar."""

    signal: Signal
    snapshot: MarketSnapshot
    account: AccountSnapshot


@dataclass(frozen=True)
class SimulationBatch:
    """Input bundle for future multi-symbol and multi-asset runs."""

    symbols: Sequence[str]
    bars: Dict[str, pd.DataFrame]

    @classmethod
    def single_symbol(cls, symbol: str, bars: pd.DataFrame) -> "SimulationBatch":
        return cls(symbols=(symbol,), bars={symbol: bars})
