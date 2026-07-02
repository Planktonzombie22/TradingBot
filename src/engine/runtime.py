from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

import pandas as pd

from src.config import AccountConfig
from src.data import MarketDataEvent, MarketDataStream
from src.execution import Broker, PaperBroker
from src.models import Order, Signal
from src.risk import RiskManager
from src.strategies.base import Strategy

from .account import PaperAccountState
from .events import EngineEvent, EngineEventType

EngineEventHandler = Callable[[EngineEvent], None]


class EngineState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass
class TradingEngine:
    """Bare-bones live/paper runtime coordinator.

    Backtesting owns historical simulation. This runtime owns event flow for
    future paper/live loops: market data in, strategy/risk/execution out.
    """

    market_data_stream: MarketDataStream
    strategy: Optional[Strategy] = None
    broker: Broker = field(default_factory=PaperBroker)
    risk_manager: RiskManager = field(default_factory=RiskManager)
    account: AccountConfig = field(default_factory=AccountConfig)
    account_state: Optional[PaperAccountState] = None
    handlers: List[EngineEventHandler] = field(default_factory=list)
    state: EngineState = EngineState.CREATED
    bar_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    last_prices: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.account_state is None:
            self.account_state = PaperAccountState(self.account.initial_cash)

    def add_handler(self, handler: EngineEventHandler) -> None:
        self.handlers.append(handler)

    def start(self) -> None:
        self.state = EngineState.RUNNING
        self.market_data_stream.add_handler(self.on_market_data)
        self._emit(EngineEventType.STARTED, "Trading engine started.")
        try:
            self.market_data_stream.run_forever()
        except Exception as exc:
            self.state = EngineState.FAILED
            self._emit(EngineEventType.ERROR, "Trading engine failed.", {"error": str(exc)})
            raise

    def stop(self) -> None:
        self.market_data_stream.stop()
        self.state = EngineState.STOPPED
        self._emit(EngineEventType.STOPPED, "Trading engine stopped.")

    def on_market_data(self, event: MarketDataEvent) -> None:
        self._emit(
            EngineEventType.MARKET_DATA,
            "Market data event received.",
            {"symbol": event.symbol, "type": event.event_type.value, "payload": event.payload},
        )
        if event.bar is None or self.strategy is None:
            return

        self._append_bar(event)
        self.last_prices[event.symbol] = event.bar.close
        signal = self._latest_signal()
        self._emit(
            EngineEventType.SIGNAL,
            "Strategy signal produced.",
            {"symbol": signal.symbol, "action": signal.action, "stop_loss": signal.stop_loss},
        )

        order = self._order_from_signal(signal, event.bar.close)
        if order is None:
            return

        submitted = self.broker.submit_order(order)
        self._emit(
            EngineEventType.ORDER,
            "Paper order submitted.",
            {"symbol": submitted.symbol, "side": submitted.side, "quantity": submitted.quantity, "status": submitted.status},
        )
        if submitted.status == "FILLED":
            self.account_state.apply_fill(submitted, event.bar.close)
            self._emit(
                EngineEventType.FILL,
                "Paper order filled.",
                {
                    "symbol": submitted.symbol,
                    "side": submitted.side,
                    "quantity": submitted.quantity,
                    "price": event.bar.close,
                    "account": self.account_state.snapshot(self.last_prices),
                },
            )

    def _emit(self, event_type: EngineEventType, message: str, payload: Optional[dict] = None) -> None:
        event = EngineEvent(event_type=event_type, message=message, payload=payload or {})
        for handler in self.handlers:
            handler(event)

    def _append_bar(self, event: MarketDataEvent) -> None:
        bar = event.bar
        self.bar_history.loc[pd.Timestamp(bar.timestamp), ["Open", "High", "Low", "Close", "Volume"]] = [
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
        ]
        self.bar_history = self.bar_history.sort_index()

    def _latest_signal(self) -> Signal:
        signals = self.strategy.generate_signals(self.bar_history)
        return signals.iloc[-1]

    def _order_from_signal(self, signal: Signal, price: float) -> Optional[Order]:
        current_quantity = self.account_state.quantity(signal.symbol)
        if signal.action == "BUY" and current_quantity > 0:
            return None
        if signal.action == "SELL" and current_quantity < 0:
            return None
        if signal.action == "CLOSE":
            if current_quantity == 0:
                return None
            return Order(
                symbol=signal.symbol,
                side="SELL" if current_quantity > 0 else "BUY",
                quantity=abs(current_quantity),
            )

        equity = self.account_state.equity({signal.symbol: price})
        decision = self.risk_manager.order_from_signal(
            signal=signal,
            equity=equity,
            price=price,
            risk_fraction=self.account.risk_fraction,
            buying_power=equity * self.account.margin_ratio,
        )
        return decision.order if decision.accepted else None
