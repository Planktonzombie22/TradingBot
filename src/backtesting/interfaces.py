from abc import ABC, abstractmethod
from typing import Iterable, Optional, Protocol, Sequence, Union

from src.models import Order, Signal

from .types import (
    AccountSnapshot,
    BacktestEvent,
    Fill,
    MarketSnapshot,
    OrderRejection,
    SignalContext,
)

ExecutionOutcome = Union[Fill, OrderRejection]


class EventSink(Protocol):
    """Receives simulation events without coupling the engine to storage."""

    def emit(self, event: BacktestEvent) -> None:
        ...


class SignalProvider(ABC):
    """Strategy-facing seam for historical, paper, and future live modes."""

    @abstractmethod
    def signal_for(self, snapshot: MarketSnapshot, account: AccountSnapshot) -> Signal:
        raise NotImplementedError


class OrderFactory(ABC):
    """Translates strategy intent into broker-like orders."""

    @abstractmethod
    def create_orders(self, context: SignalContext) -> Sequence[Order]:
        raise NotImplementedError


class RiskModel(ABC):
    """Accepts, rejects, resizes, or annotates orders before execution."""

    @abstractmethod
    def evaluate(self, order: Order, account: AccountSnapshot, snapshot: MarketSnapshot) -> Optional[OrderRejection]:
        raise NotImplementedError


class CommissionModel(ABC):
    """Computes explicit transaction costs."""

    @abstractmethod
    def calculate(self, order: Order, fill_price: float, fill_quantity: float) -> float:
        raise NotImplementedError


class SlippageModel(ABC):
    """Moves the execution price away from the reference market price."""

    @abstractmethod
    def apply(self, order: Order, snapshot: MarketSnapshot, reference_price: float) -> float:
        raise NotImplementedError


class LiquidityModel(ABC):
    """Determines how much of an order can be filled on the current bar."""

    @abstractmethod
    def fillable_quantity(self, order: Order, snapshot: MarketSnapshot) -> float:
        raise NotImplementedError


class BorrowCostModel(ABC):
    """Models borrow fees, locate failures, and short inventory constraints."""

    @abstractmethod
    def accrue(self, account: AccountSnapshot, snapshot: MarketSnapshot) -> float:
        raise NotImplementedError


class MarginModel(ABC):
    """Owns buying power, initial margin, maintenance margin, and margin calls."""

    @abstractmethod
    def buying_power(self, account: AccountSnapshot) -> float:
        raise NotImplementedError

    @abstractmethod
    def required_initial_margin(self, order: Order, price: float) -> float:
        raise NotImplementedError

    @abstractmethod
    def required_maintenance_margin(self, account: AccountSnapshot) -> float:
        raise NotImplementedError

    @abstractmethod
    def margin_call(self, account: AccountSnapshot) -> bool:
        raise NotImplementedError


class ExecutionModel(ABC):
    """Simulates how broker/order-book mechanics transform orders into fills."""

    @abstractmethod
    def execute(self, order: Order, snapshot: MarketSnapshot, account: AccountSnapshot) -> ExecutionOutcome:
        raise NotImplementedError


class PortfolioLedger(ABC):
    """Applies fills, marks positions, and creates account snapshots."""

    @abstractmethod
    def snapshot(self, timestamp, prices: Optional[dict] = None) -> AccountSnapshot:
        raise NotImplementedError

    @abstractmethod
    def apply_fill(self, fill: Fill) -> None:
        raise NotImplementedError

    @abstractmethod
    def accrue_cost(self, amount: float, timestamp) -> None:
        raise NotImplementedError


class MetricsCalculator(ABC):
    """Turns account, fill, and event history into analytics."""

    @abstractmethod
    def calculate(
        self,
        account_history: Sequence[AccountSnapshot],
        fills: Sequence[Fill],
        events: Sequence[BacktestEvent],
    ) -> dict:
        raise NotImplementedError
