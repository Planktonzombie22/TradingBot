from dataclasses import dataclass

from src.execution import PaperBroker
from src.models import Order

from .profiles import BacktestExecutionProfile
from .types import AccountSnapshot, MarketSnapshot, OrderRejection


@dataclass(frozen=True)
class ExecutionParityResult:
    backtest_status: str
    paper_status: str
    backtest_quantity: float
    paper_quantity: float
    backtest_price: float
    paper_reference_price: float

    @property
    def status_matches(self) -> bool:
        return self.backtest_status == self.paper_status

    @property
    def quantity_matches(self) -> bool:
        return self.backtest_quantity == self.paper_quantity


@dataclass(frozen=True)
class ExecutionParityScenario:
    order: Order
    snapshot: MarketSnapshot
    account: AccountSnapshot
    profile: BacktestExecutionProfile = BacktestExecutionProfile()

    def replay(self) -> ExecutionParityResult:
        execution_model = self.profile.build_execution_model()
        outcome = execution_model.execute(self.order, self.snapshot, self.account)
        broker = PaperBroker(auto_fill_market_orders=True)
        paper_order = broker.submit_order(self.order)
        reference_price = self.snapshot.price(self.profile.price_column)

        if isinstance(outcome, OrderRejection):
            backtest_status = "REJECTED"
            backtest_quantity = 0.0
            backtest_price = 0.0
        else:
            backtest_status = "FILLED"
            backtest_quantity = outcome.quantity
            backtest_price = outcome.price

        return ExecutionParityResult(
            backtest_status=backtest_status,
            paper_status=paper_order.status,
            backtest_quantity=backtest_quantity,
            paper_quantity=paper_order.quantity if paper_order.status == "FILLED" else 0.0,
            backtest_price=backtest_price,
            paper_reference_price=reference_price,
        )
