# TradingBot

Modular trading research framework for strategy development, historical simulation, and future paper/live execution.

## Architecture

- `src/models`: portable domain records such as orders, signals, bars, positions, trades, portfolios, and backtest results.
- `src/config`: runtime profiles and legacy constants. Prefer `RuntimeConfig` for new workflows.
- `src/data`: market data feed contracts, provider adapters, and normalization through `MarketDataManager`.
- `src/indicators`: pure indicator calculations. These should not know about execution, risk, or portfolio state.
- `src/strategies`: strategy contracts and registry. Strategies emit `Signal` objects only.
- `src/risk`: position sizing, stop-loss policy, and order risk decisions.
- `src/execution`: broker-facing contracts and paper broker scaffolding.
- `src/portfolio`: portfolio books and performance analytics.
- `src/backtesting`: event-driven historical simulation with pluggable slippage, commission, liquidity, margin, risk, ledger, and metrics models.
- `src/backtest`: compatibility command/reporting layer for older imports.
- `src/app.py`: application workflow boundary that wires config, data, strategy, and simulation.

## Backtest Entry Points

```python
from src.app import TradingApplication
from src.config import RuntimeConfig

app = TradingApplication(RuntimeConfig())
data = app.load_data()
strategy = app.create_strategy()
result = app.run_backtest(data, strategy)
```

Legacy imports still work:

```python
from src.backtest import run_backtest
```

## Development

Run checks with the project interpreter:

```powershell
trading_env\Scripts\python.exe -m compileall src
trading_env\Scripts\python.exe -m pytest src\tests
```
