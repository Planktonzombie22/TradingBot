from dataclasses import dataclass

from src.models import Order

from .interfaces import MarginModel
from .types import AccountSnapshot


@dataclass(frozen=True)
class SimpleMarginModel(MarginModel):
    """Conservative margin model suitable as a default simulation baseline."""

    leverage: float = 1.0
    maintenance_rate: float = 0.25

    def buying_power(self, account: AccountSnapshot) -> float:
        available_margin = max(account.equity - account.used_margin, 0.0)
        return available_margin * self.leverage

    def required_initial_margin(self, order: Order, price: float) -> float:
        if self.leverage <= 0:
            return abs(order.quantity * price)
        return abs(order.quantity * price) / self.leverage

    def required_maintenance_margin(self, account: AccountSnapshot) -> float:
        return account.used_margin * self.maintenance_rate

    def margin_call(self, account: AccountSnapshot) -> bool:
        return account.equity < account.maintenance_margin
