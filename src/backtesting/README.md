# Backtesting Package Layout

The package is intentionally split by responsibility:

- `core/`: simulator primitives and engine internals: snapshots, fills, interfaces, ledger, margin, risk, metrics, validation, and `BacktestEngine`.
- `execution/`: execution realism and cost modeling: bar fills, commissions, slippage, liquidity, borrow costs, execution profiles, parity checks, calibration, and capacity analysis.
- `runners/`: workflows that run backtests repeatedly or produce research artifacts: batch runs, bulk runs, multi-symbol runs, optimization, walk-forward, governance, replication, and research matrices.
- `research/`: strategy-selection and market-research layers: regime classification, filters, benchmark-relative selection, scorecards, ensembles, market clusters, style premia, stat arb, factor trend, crypto selection, dynamic allocation, and options promotion gates.

`src.backtesting` remains the public facade. Prefer importing from there in application code, for example:

```python
from src.backtesting import BacktestConfig, run_backtest, run_walk_forward_governance
```

Direct legacy module paths such as `src.backtesting.types` and `src.backtesting.costs` are aliased for compatibility, but new internal code should import from the clearer subpackages.
