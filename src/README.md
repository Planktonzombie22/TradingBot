# Source Layout

The source tree is organized around runtime responsibility:

- `app.py`: application orchestration entry point that connects config, data, strategies, backtesting, and execution.
- `backtesting/`: historical simulation, execution realism, research workflows, validation, and strategy promotion tooling.
- `config/`: runtime profiles, settings, environment validation, and config loading.
- `data/`: market-data providers, live/replay streams, normalization, quality checks, calendars, and universes.
- `engine/`: live/paper engine state, event handling, account state, and runtime safety decisions.
- `execution/`: broker abstraction, paper/Alpaca brokers, order intents/plans, order lifecycle, reconciliation, and safety guards.
- `indicators/`: technical indicators grouped by market concept.
- `models/`: shared domain models such as orders, bars, positions, signals, trades, and backtest results.
- `monitoring/`: dashboards, health checks, metrics, and notifications.
- `operations/`: operational run checklists and soak-test helpers.
- `portfolio/`: portfolio books, allocation logic, and performance analytics.
- `reporting/`: summaries, plots, and HTML/report artifacts.
- `risk/`: live-trading risk limits, position sizing, stops, and risk manager decisions.
- `storage/`: JSONL artifacts, immutable run manifests, and SQLite broker state.
- `strategies/`: strategy interfaces, registry, parameters, scheduling, and concrete systems.
- `utils/`: shared infrastructure helpers such as retry, logging, timers, and Alpaca REST plumbing.

Most packages expose a stable public facade from their top-level `__init__.py`; application code should prefer those facades unless it is working inside that package.
