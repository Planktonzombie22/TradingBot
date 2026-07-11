from dataclasses import dataclass
from typing import Callable, Dict, Mapping

import pandas as pd

from src.models import BacktestResult
from src.strategies.core.base import Strategy

from ..core.engine import BacktestEngine
from ..core.types import BacktestConfig


StrategyFactory = Callable[[str], Strategy]


@dataclass(frozen=True)
class MultiSymbolBacktestResult:
    symbol_results: Dict[str, BacktestResult]
    equity: pd.Series
    total_pnl: float
    total_pnl_pct: float

    @property
    def fills(self):
        return [fill for result in self.symbol_results.values() for fill in result.fills]

    @property
    def trades(self):
        return [trade for result in self.symbol_results.values() for trade in result.trades]


def run_multi_symbol_backtest(
    data: Mapping[str, pd.DataFrame],
    strategy_factory: StrategyFactory,
    config: BacktestConfig | None = None,
) -> MultiSymbolBacktestResult:
    if not data:
        raise ValueError("Multi-symbol backtest requires at least one symbol.")

    config = config or BacktestConfig()
    per_symbol_cash = config.initial_cash / len(data)
    symbol_results: Dict[str, BacktestResult] = {}

    for symbol, bars in data.items():
        symbol_config = BacktestConfig(
            initial_cash=per_symbol_cash,
            base_currency=config.base_currency,
            margin_ratio=config.margin_ratio,
            risk_fraction=config.risk_fraction,
            allow_shorting=config.allow_shorting,
            allow_fractional_shares=config.allow_fractional_shares,
            mark_price_column=config.mark_price_column,
            execution_price_column=config.execution_price_column,
            warmup_bars=config.warmup_bars,
            force_flat_at_end=config.force_flat_at_end,
            metadata={**config.metadata, "symbol": symbol},
        )
        symbol_results[symbol] = BacktestEngine(config=symbol_config).run(strategy_factory(symbol), bars)

    equity = pd.concat([result.equity for result in symbol_results.values()], axis=1).ffill().sum(axis=1)
    total_pnl = float(equity.iloc[-1] - config.initial_cash)
    total_pnl_pct = float(total_pnl / config.initial_cash) if config.initial_cash else 0.0
    return MultiSymbolBacktestResult(
        symbol_results=symbol_results,
        equity=equity,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
    )
