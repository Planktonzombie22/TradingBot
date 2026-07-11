from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

import pandas as pd

from src.config import AccountConfig, RuntimeRiskConfig
from src.data import MarketDataEvent, MarketDataStream
from src.execution import Broker, PaperBroker
from src.models import Order, Signal
from src.risk import RiskManager
from src.strategies.core.base import Strategy

from .account import PaperAccountState
from .events import EngineEvent, EngineEventType
from .safety import RuntimeRiskMonitor

EngineEventHandler = Callable[[EngineEvent], None]


class EngineState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    HALTED = "HALTED"
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
    runtime_risk: RuntimeRiskConfig = field(default_factory=RuntimeRiskConfig)
    account_state: Optional[PaperAccountState] = None
    handlers: List[EngineEventHandler] = field(default_factory=list)
    state: EngineState = EngineState.CREATED
    bar_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    last_prices: dict = field(default_factory=dict)
    disable_new_orders: bool = False
    risk_monitor: Optional[RuntimeRiskMonitor] = None

    def __post_init__(self) -> None:
        if self.account_state is None:
            self.account_state = PaperAccountState(self.account.initial_cash)
        if self.risk_monitor is None:
            self.risk_monitor = RuntimeRiskMonitor(self.runtime_risk)

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

    def pause(self) -> None:
        if self.state == EngineState.RUNNING:
            self.state = EngineState.PAUSED
            self._emit(EngineEventType.CONTROL, "Trading engine paused.")

    def resume(self) -> None:
        if self.state == EngineState.PAUSED:
            self.state = EngineState.RUNNING
            self._emit(EngineEventType.CONTROL, "Trading engine resumed.")

    def disable_orders(self) -> None:
        self.disable_new_orders = True
        self._emit(EngineEventType.CONTROL, "New orders disabled.")

    def enable_orders(self) -> None:
        self.disable_new_orders = False
        self._emit(EngineEventType.CONTROL, "New orders enabled.")

    def cancel_all_orders(self) -> int:
        cancelled = 0
        for order in list(self.broker.open_orders()):
            if self.broker.cancel_order(order.id) is not None:
                cancelled += 1
        self._emit(EngineEventType.CONTROL, "Open orders cancelled.", {"cancelled": cancelled})
        return cancelled

    def flatten_positions(self) -> int:
        flattened = 0
        for symbol, position in list(self.account_state.positions.items()):
            if position.quantity == 0:
                continue
            order = Order(
                symbol=symbol,
                side="SELL" if position.quantity > 0 else "BUY",
                quantity=abs(position.quantity),
            )
            submitted = self.broker.submit_order(order)
            flattened += 1
            self._emit(
                EngineEventType.ORDER,
                "Flatten order submitted.",
                {"symbol": submitted.symbol, "side": submitted.side, "quantity": submitted.quantity, "status": submitted.status},
            )
            price = self.last_prices.get(symbol, position.average_price)
            if submitted.status == "FILLED":
                self.account_state.apply_fill(submitted, price)
                self._emit(
                    EngineEventType.FILL,
                    "Flatten order filled.",
                    {
                        "symbol": submitted.symbol,
                        "side": submitted.side,
                        "quantity": submitted.quantity,
                        "price": price,
                        "account": self.account_state.snapshot(self.last_prices),
                    },
                )
        self._emit(EngineEventType.CONTROL, "Positions flattened.", {"flatten_orders": flattened})
        return flattened

    def kill_switch(self, reason: str = "Manual kill switch activated.") -> None:
        self.disable_orders()
        cancelled = self.cancel_all_orders()
        flattened = self.flatten_positions()
        self.state = EngineState.HALTED
        self.market_data_stream.stop()
        self._emit(
            EngineEventType.HALT,
            reason,
            {"cancelled": cancelled, "flatten_orders": flattened},
        )

    def on_market_data(self, event: MarketDataEvent) -> None:
        self._emit(
            EngineEventType.MARKET_DATA,
            "Market data event received.",
            {"symbol": event.symbol, "type": event.event_type.value, "payload": event.payload},
        )
        if event.bar is None or self.strategy is None:
            return
        if self.state in {EngineState.PAUSED, EngineState.HALTED, EngineState.STOPPED, EngineState.FAILED}:
            return

        self._append_bar(event)
        self.last_prices[event.symbol] = event.bar.close
        equity_decision = self.risk_monitor.evaluate_equity(self.account_state.equity(self.last_prices))
        if not equity_decision.accepted:
            self._halt_for_risk(equity_decision.reason)
            return

        signal = self._latest_signal()
        self._emit(
            EngineEventType.SIGNAL,
            "Strategy signal produced.",
            {"symbol": signal.symbol, "action": signal.action, "stop_loss": signal.stop_loss},
        )

        if self.disable_new_orders:
            self._emit(EngineEventType.CONTROL, "Signal ignored because new orders are disabled.", {"symbol": signal.symbol})
            return

        order = self._order_from_signal(signal, event.bar.close)
        if order is None:
            return
        risk_decision = self.risk_monitor.evaluate_order(
            order=order,
            price=event.bar.close,
            current_position_quantity=self.account_state.quantity(order.symbol),
            open_orders=self.broker.open_orders(),
        )
        if not risk_decision.accepted:
            self._halt_for_risk(risk_decision.reason)
            return

        submitted = self.broker.submit_order(order)
        self.risk_monitor.record_order()
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

    def _halt_for_risk(self, reason: Optional[str]) -> None:
        message = reason or "Runtime risk halt triggered."
        self.disable_new_orders = True
        self.state = EngineState.HALTED
        self.market_data_stream.stop()
        self._emit(EngineEventType.HALT, message)
