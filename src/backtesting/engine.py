from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from src.models import BacktestResult, Order
from src.strategies.base import Strategy

from .adapters import PandasStrategySignalProvider, RiskPercentOrderFactory
from .costs import NoBorrowCostModel, NoSlippageModel, UnlimitedLiquidityModel, ZeroCommissionModel
from .execution import BarExecutionModel
from .interfaces import (
    BorrowCostModel,
    EventSink,
    ExecutionModel,
    MetricsCalculator,
    OrderFactory,
    RiskModel,
    SignalProvider,
)
from .ledger import CashMarginLedger
from .margin import SimpleMarginModel
from .metrics import BasicMetricsCalculator
from .risk import CompositeRiskModel
from .types import (
    AccountSnapshot,
    BacktestConfig,
    BacktestEvent,
    BacktestEventType,
    Fill,
    MarketSnapshot,
    OrderRejection,
    SignalContext,
)


@dataclass
class InMemoryEventSink(EventSink):
    events: List[BacktestEvent] = field(default_factory=list)

    def emit(self, event: BacktestEvent) -> None:
        self.events.append(event)


@dataclass
class BacktestEngine:
    """Composable event-driven shell for historical simulation.

    The defaults intentionally remain modest. Realism is added by swapping
    models, not by editing orchestration code.
    """

    config: BacktestConfig = field(default_factory=BacktestConfig)
    signal_provider: Optional[SignalProvider] = None
    order_factory: Optional[OrderFactory] = None
    risk_model: Optional[RiskModel] = None
    execution_model: Optional[ExecutionModel] = None
    borrow_cost_model: BorrowCostModel = field(default_factory=NoBorrowCostModel)
    metrics_calculator: MetricsCalculator = field(default_factory=BasicMetricsCalculator)
    event_sink: InMemoryEventSink = field(default_factory=InMemoryEventSink)

    def run(self, strategy: Strategy, bars: pd.DataFrame) -> BacktestResult:
        if bars.empty:
            raise ValueError("Cannot backtest an empty data frame.")
        self.event_sink.events.clear()

        working_bars = bars.dropna(subset=[self.config.mark_price_column])
        symbol = strategy.symbol
        margin_model = SimpleMarginModel(leverage=self.config.margin_ratio)
        ledger = CashMarginLedger(initial_cash=self.config.initial_cash, margin_model=margin_model)

        signal_provider = self.signal_provider or PandasStrategySignalProvider(strategy, working_bars)
        order_factory = self.order_factory or RiskPercentOrderFactory(
            risk_fraction=self.config.risk_fraction,
            margin_ratio=self.config.margin_ratio,
            allow_fractional_shares=self.config.allow_fractional_shares,
        )
        risk_model = self.risk_model or CompositeRiskModel(
            margin_model=margin_model,
            allow_shorting=self.config.allow_shorting,
        )
        execution_model = self.execution_model or BarExecutionModel(
            slippage_model=NoSlippageModel(),
            commission_model=ZeroCommissionModel(),
            liquidity_model=UnlimitedLiquidityModel(),
            price_column=self.config.execution_price_column,
        )

        account_history: List[AccountSnapshot] = []
        fills: List[Fill] = []
        rejections: List[OrderRejection] = []

        for row_number, (timestamp, row) in enumerate(working_bars.iterrows()):
            snapshot = MarketSnapshot.from_row(symbol, timestamp, row)
            prices = {symbol: snapshot.price(self.config.mark_price_column)}
            account = ledger.snapshot(snapshot.timestamp, prices=prices)

            self._emit(snapshot, BacktestEventType.BAR, "Processing historical bar.", {"row": row_number})
            if row_number < self.config.warmup_bars:
                account_history.append(account)
                continue

            borrow_cost = self.borrow_cost_model.accrue(account, snapshot)
            if borrow_cost:
                ledger.accrue_cost(borrow_cost, snapshot.timestamp)
                self._emit(snapshot, BacktestEventType.CASH_ADJUSTMENT, "Borrow cost accrued.", {"amount": borrow_cost})

            signal = signal_provider.signal_for(snapshot, account)
            self._emit(snapshot, BacktestEventType.SIGNAL, "Strategy signal received.", {"action": signal.action})

            context = SignalContext(signal=signal, snapshot=snapshot, account=account)
            for order in order_factory.create_orders(context):
                self._emit_order(snapshot, BacktestEventType.ORDER_CREATED, "Order created from signal.", order)
                rejection = risk_model.evaluate(order, account, snapshot)
                if rejection is not None:
                    rejections.append(rejection)
                    self._emit_rejection(rejection)
                    continue

                outcome = execution_model.execute(order, snapshot, account)
                if isinstance(outcome, OrderRejection):
                    rejections.append(outcome)
                    self._emit_rejection(outcome)
                    continue

                ledger.apply_fill(outcome)
                fills.append(outcome)
                account = ledger.snapshot(snapshot.timestamp, prices=prices)
                self._emit(
                    snapshot,
                    BacktestEventType.ORDER_FILLED,
                    "Order filled.",
                    {"symbol": order.symbol, "quantity": outcome.quantity, "price": outcome.price},
                )

            account_history.append(ledger.snapshot(snapshot.timestamp, prices=prices))

        if self.config.force_flat_at_end and account_history:
            self._force_flat(symbol, working_bars, ledger, execution_model, fills, rejections)
            last_timestamp = account_history[-1].timestamp
            last_price = float(working_bars[self.config.mark_price_column].iloc[-1])
            account_history[-1] = ledger.snapshot(last_timestamp, prices={symbol: last_price})

        equity = pd.Series(
            [snapshot.equity for snapshot in account_history],
            index=[snapshot.timestamp for snapshot in account_history],
            dtype=float,
        )
        money_available = pd.Series(
            [snapshot.buying_power for snapshot in account_history],
            index=[snapshot.timestamp for snapshot in account_history],
            dtype=float,
        )
        metrics = self.metrics_calculator.calculate(account_history, fills, self.event_sink.events)
        total_pnl = equity.iloc[-1] - self.config.initial_cash

        return BacktestResult(
            trades=list(ledger.closed_trades),
            equity=equity,
            money_available=money_available,
            total_pnl=float(total_pnl),
            total_pnl_pct=float(total_pnl / self.config.initial_cash) if self.config.initial_cash else 0.0,
            fills=fills,
            rejections=rejections,
            account_history=account_history,
            events=list(self.event_sink.events),
            metrics=metrics,
            config=self.config,
        )

    def _force_flat(
        self,
        symbol: str,
        bars: pd.DataFrame,
        ledger: CashMarginLedger,
        execution_model: ExecutionModel,
        fills: List[Fill],
        rejections: List[OrderRejection],
    ) -> None:
        last_timestamp = bars.index[-1]
        last_row = bars.iloc[-1]
        snapshot = MarketSnapshot.from_row(symbol, last_timestamp, last_row)
        account = ledger.snapshot(snapshot.timestamp, prices={symbol: snapshot.close})
        for held_symbol, quantity in list(account.positions.items()):
            order = Order(
                symbol=held_symbol,
                side="SELL" if quantity > 0 else "BUY",
                quantity=abs(quantity),
            )
            outcome = execution_model.execute(order, snapshot, account)
            if isinstance(outcome, OrderRejection):
                rejections.append(outcome)
                self._emit_rejection(outcome)
            else:
                ledger.apply_fill(outcome)
                fills.append(outcome)
                self._emit(snapshot, BacktestEventType.POSITION_CLOSED, "Position force-closed at simulation end.")

    def _emit(self, snapshot: MarketSnapshot, event_type: BacktestEventType, message: str, payload: Optional[dict] = None) -> None:
        self.event_sink.emit(
            BacktestEvent(
                timestamp=snapshot.timestamp,
                event_type=event_type,
                message=message,
                payload=payload or {},
            )
        )

    def _emit_order(self, snapshot: MarketSnapshot, event_type: BacktestEventType, message: str, order: Order) -> None:
        self._emit(
            snapshot,
            event_type,
            message,
            {"symbol": order.symbol, "side": order.side, "quantity": order.quantity, "type": order.order_type},
        )

    def _emit_rejection(self, rejection: OrderRejection) -> None:
        self.event_sink.emit(
            BacktestEvent(
                timestamp=rejection.timestamp,
                event_type=BacktestEventType.ORDER_REJECTED,
                message=rejection.message,
                payload={"reason": rejection.reason.value, **rejection.metadata},
            )
        )


def run_backtest(strategy: Strategy, df: pd.DataFrame, config: Optional[BacktestConfig] = None) -> BacktestResult:
    """Compatibility entrypoint for scripts that still import run_backtest."""

    return BacktestEngine(config=config or BacktestConfig()).run(strategy, df)
