from abc import ABC, abstractmethod
from typing import Callable, Iterable, Sequence

from .events import MarketDataEvent

MarketDataHandler = Callable[[MarketDataEvent], None]


class MarketDataStream(ABC):
    """Push-based market data stream contract."""

    @abstractmethod
    def subscribe_bars(self, symbols: Sequence[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_handler(self, handler: MarketDataHandler) -> None:
        raise NotImplementedError

    @abstractmethod
    def run_forever(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError


class ReplayMarketDataStream(MarketDataStream):
    """Deterministic stream for testing live-style flows from stored events."""

    def __init__(self, events: Iterable[MarketDataEvent]):
        self.events = list(events)
        self.handlers: list[MarketDataHandler] = []
        self.running = False

    def subscribe_bars(self, symbols: Sequence[str]) -> None:
        self.symbols = set(symbols)

    def add_handler(self, handler: MarketDataHandler) -> None:
        self.handlers.append(handler)

    def run_forever(self) -> None:
        self.running = True
        for event in self.events:
            if not self.running:
                break
            if hasattr(self, "symbols") and event.symbol not in self.symbols:
                continue
            for handler in self.handlers:
                handler(event)

    def stop(self) -> None:
        self.running = False


class YFinancePollingStream(MarketDataStream):
    """Placeholder for polling yfinance and emitting stream-shaped events."""

    def __init__(self):
        self.handlers: list[MarketDataHandler] = []
        self.symbols: Sequence[str] = []
        self.running = False

    def subscribe_bars(self, symbols: Sequence[str]) -> None:
        self.symbols = symbols

    def add_handler(self, handler: MarketDataHandler) -> None:
        self.handlers.append(handler)

    def run_forever(self) -> None:
        self.running = True
        raise NotImplementedError("YFinance polling stream architecture is present but not implemented yet.")

    def stop(self) -> None:
        self.running = False
