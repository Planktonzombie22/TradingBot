from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from src.config import RuntimeRiskConfig
from src.models import Order


@dataclass(frozen=True)
class RuntimeRiskDecision:
    accepted: bool
    reason: Optional[str] = None


@dataclass
class RuntimeRiskMonitor:
    """Stateful paper-runtime safety checks for halts and order throttles."""

    config: RuntimeRiskConfig = field(default_factory=RuntimeRiskConfig)
    starting_equity: Optional[float] = None
    peak_equity: Optional[float] = None
    halted: bool = False
    halt_reason: Optional[str] = None
    order_timestamps: list[datetime] = field(default_factory=list)

    def evaluate_equity(self, equity: float) -> RuntimeRiskDecision:
        if self.starting_equity is None:
            self.starting_equity = equity
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

        if self.config.max_daily_loss is not None and self.starting_equity - equity >= self.config.max_daily_loss:
            return self._halt(f"Max daily loss exceeded: {self.starting_equity - equity:.2f}.")

        if self.config.max_drawdown is not None and self.peak_equity and self.peak_equity > 0:
            drawdown = (self.peak_equity - equity) / self.peak_equity
            if drawdown >= self.config.max_drawdown:
                return self._halt(f"Max drawdown exceeded: {drawdown:.2%}.")

        return RuntimeRiskDecision(True)

    def evaluate_order(
        self,
        order: Order,
        price: float,
        current_position_quantity: float,
        open_orders: Iterable[Order],
        now: Optional[datetime] = None,
    ) -> RuntimeRiskDecision:
        if self.halted:
            return RuntimeRiskDecision(False, self.halt_reason or "Runtime risk monitor is halted.")

        order_notional = abs(order.quantity * price)
        if self.config.max_order_notional is not None and order_notional > self.config.max_order_notional:
            return self._halt(f"Max order notional exceeded: {order_notional:.2f}.")

        projected_quantity = current_position_quantity + (order.quantity if order.side == "BUY" else -order.quantity)
        projected_notional = abs(projected_quantity * price)
        if self.config.max_position_notional is not None and projected_notional > self.config.max_position_notional:
            return self._halt(f"Max position notional exceeded: {projected_notional:.2f}.")

        if self.config.max_open_orders is not None and len(list(open_orders)) >= self.config.max_open_orders:
            return self._halt(f"Max open orders exceeded: {self.config.max_open_orders}.")

        now = now or datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=1)
        self.order_timestamps = [timestamp for timestamp in self.order_timestamps if timestamp >= window_start]
        if self.config.max_orders_per_minute is not None and len(self.order_timestamps) >= self.config.max_orders_per_minute:
            return self._halt(f"Max order frequency exceeded: {self.config.max_orders_per_minute} per minute.")

        return RuntimeRiskDecision(True)

    def record_order(self, timestamp: Optional[datetime] = None) -> None:
        self.order_timestamps.append(timestamp or datetime.now(timezone.utc))

    def reset_halt(self) -> None:
        self.halted = False
        self.halt_reason = None

    def _halt(self, reason: str) -> RuntimeRiskDecision:
        self.halted = True
        self.halt_reason = reason
        return RuntimeRiskDecision(False, reason)
