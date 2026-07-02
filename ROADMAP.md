# TradingBot Completion Roadmap

Current status: MVP/research scaffold complete, not autonomous-production-ready.

The first 30 items moved the bot from prototype toward a coherent research and paper-trading MVP:

1. Add runtime paper account state so stream fills update cash, positions, and equity.
2. Add machine-readable run reports for backtests and stream sessions.
3. Add an explicit roadmap and completion checklist to keep work ordered.
4. Add historical Alpaca data support alongside yfinance.
5. Add real paper-trading order submission through Alpaca REST.
6. Add order IDs, fill IDs, and broker reconciliation models.
7. Add persistent storage for trades, fills, equity curves, and events.
8. Add a configuration loader that merges defaults, `.env`, and CLI overrides.
9. Add strategy parameter schemas and validation.
10. Add walk-forward backtesting.
11. Add parameter optimization with train/test splits.
12. Add multi-symbol backtesting.
13. Add portfolio-level allocation and exposure limits.
14. Add sector, symbol, and correlation risk limits.
15. Add richer slippage models based on spread and volume.
16. Add commission/fee presets for common brokers.
17. Add borrow fee and short-locate modeling.
18. Add stop-loss and take-profit order generation.
19. Add trailing stops.
20. Add order replacement/cancel flows.
21. Add live market session/calendar checks.
22. Add structured JSON logging.
23. Add rotating file logs.
24. Add exception boundaries and retry policies for data providers.
25. Add data quality checks for missing bars, split spikes, and stale quotes.
26. Add indicator golden-value tests against known references.
27. Add strategy behavior tests for entry/exit edge cases.
28. Add CLI commands for `backtest`, `stream`, `paper`, and `report`.
29. Add a dashboard or notebook report generator.
30. Add deployment docs for running the bot continuously.

Implemented so far: items 1-30.
Production paper-trading readiness starts at item 31.

The remaining roadmap is the practical path to a bot that can run autonomous Alpaca paper trading, trustworthy backtesting, and repeatable optimization:

31. Add a broker account sync service for cash, buying power, positions, open orders, and day-trading status. Implemented MVP.
32. Add Alpaca order lifecycle reconciliation so local orders, broker orders, fills, cancels, and rejects converge after every restart. Implemented MVP.
33. Add idempotent broker submissions with stable client order IDs and duplicate-order protection. Implemented MVP.
34. Persist broker-facing state in a durable database instead of only JSONL artifacts. Implemented MVP.
35. Add startup recovery that rebuilds engine state from persisted orders, fills, account snapshots, and broker account state. Implemented MVP.
36. Add an explicit dry-run mode that exercises the full live pipeline without submitting orders.
37. Add an explicit paper-trading mode that submits real Alpaca paper orders behind environment and config safeguards.
38. Add a hard live-trading guard so production code cannot accidentally send live orders without a deliberate future unlock.
39. Add max daily loss, max drawdown, max position size, max notional, max open orders, and max order frequency halts.
40. Add a global kill switch that can flatten positions, cancel open orders, and stop the engine.
41. Add manual operator controls for pause, resume, cancel-all, flatten, and disable-new-orders.
42. Add market calendar handling for holidays, half days, early closes, pre-market, regular session, and after-hours policy.
43. Add websocket heartbeat monitoring, reconnect backoff, subscription replay, and stale-stream alarms.
44. Add rate-limit-aware REST clients with retries, jitter, request logging, and broker error classification.
45. Add historical Alpaca pagination and cache hydration for multi-symbol backtests.
46. Add corporate action handling for splits, dividends, symbol changes, and adjusted/unadjusted price policies.
47. Add data quality gates for duplicate bars, missing bars, out-of-order events, bad OHLC relationships, and extreme gaps.
48. Add live-vs-historical data normalization checks so strategies receive the same schema in both modes.
49. Add multi-symbol universe loading from config files, watchlists, broker assets, and generated research screens.
50. Add strategy scheduling by symbol, timeframe, session window, and warmup requirements.
51. Add strategy parameter schemas that are serializable, optimizable, and validated before runs.
52. Add a strategy plugin boundary for cleanly registering new strategies without editing core engine code.
53. Add portfolio allocation policies for equal weight, volatility targeting, risk parity, and fixed notional sizing.
54. Add portfolio-level exposure controls for sector, correlation, beta, symbol concentration, and cash reserve.
55. Add order intent models that distinguish signal, target position, generated order, broker order, and fill.
56. Add order replacement logic for stops, take-profits, trails, partial fills, and stale limit orders.
57. Add bracket, OCO, stop, stop-limit, trailing-stop, market, and limit order abstractions with broker capability checks.
58. Add end-of-day policies for holding overnight, flattening, reducing risk, and canceling stale orders.
59. Add transaction cost calibration from observed paper fills and quoted spreads.
60. Align backtest fills with paper execution assumptions, including bar timing, next-bar fills, spread, slippage, liquidity, and partial fills.
61. Add paper/live parity tests that replay the same scenario through backtesting, paper broker, and broker adapter boundaries.
62. Add an optimization CLI with grid search, random search, walk-forward runs, train/test splits, and artifact output.
63. Add overfitting controls: holdout windows, rolling validation, parameter stability, turnover penalties, and minimum trade counts.
64. Add optimization result ranking by CAGR, Sharpe, Sortino, drawdown, win rate, exposure, turnover, and tail risk.
65. Add batch backtesting over symbols, strategies, parameter sets, and timeframes with resumable progress.
66. Add run manifests that record code version, config, data source, data range, strategy parameters, and dependency versions.
67. Add immutable research artifacts for equity curves, orders, fills, trades, metrics, logs, config, and HTML reports.
68. Add a dashboard for current paper account state, open orders, recent fills, PnL, risk halts, and engine health.
69. Add notifications for startup, shutdown, order submission, fills, rejects, halts, exceptions, and stale data.
70. Add structured observability with JSON logs, metrics counters, latency timing, and health checks.
71. Add integration tests with mocked Alpaca REST and websocket flows for auth, bars, orders, fills, rejects, and reconnects.
72. Add scenario tests for market closed, insufficient buying power, rate limits, partial fills, cancel rejects, and stale data.
73. Add deployment profiles for local Windows task scheduling, Docker, and a small always-on server.
74. Add secrets handling and `.env` validation that fail fast when required credentials or unsafe combinations are present.
75. Add a final paper-trading soak checklist: at least several market sessions, no unreconciled orders, clean restarts, no unhandled exceptions, and metrics matching broker statements.
