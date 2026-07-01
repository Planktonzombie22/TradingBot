from dataclasses import dataclass, field

import pandas as pd

from src.backtesting import BacktestConfig, BacktestEngine
from src.config import RuntimeConfig
from src.data import MarketDataManager, YFinanceDataFeed
from src.models import BacktestResult
from src.strategies import get_strategy
from src.strategies.base import Strategy


@dataclass
class TradingApplication:
    """High-level workflow boundary for the trading bot."""

    config: RuntimeConfig = field(default_factory=RuntimeConfig)
    data_manager: MarketDataManager = field(default_factory=lambda: MarketDataManager(YFinanceDataFeed()))

    def load_data(self) -> pd.DataFrame:
        return self.data_manager.historical(self.config.data)

    def create_strategy(self) -> Strategy:
        strategy_cls = get_strategy(self.config.strategy.name)
        return strategy_cls(self.config.data.symbol, **self.config.strategy.params)

    def run_backtest(self, data=None, strategy=None) -> BacktestResult:
        data = data if data is not None else self.load_data()
        strategy = strategy if strategy is not None else self.create_strategy()
        engine = BacktestEngine(
            config=BacktestConfig(
                initial_cash=self.config.account.initial_cash,
                margin_ratio=self.config.account.margin_ratio,
                risk_fraction=self.config.account.risk_fraction,
                base_currency=self.config.account.base_currency,
            )
        )
        return engine.run(strategy, data)
