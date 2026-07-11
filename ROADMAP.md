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
36. Add an explicit dry-run mode that exercises the full live pipeline without submitting orders. Implemented MVP.
37. Add an explicit paper-trading mode that submits real Alpaca paper orders behind environment and config safeguards. Implemented MVP.
38. Add a hard live-trading guard so production code cannot accidentally send live orders without a deliberate future unlock. Implemented MVP.
39. Add max daily loss, max drawdown, max position size, max notional, max open orders, and max order frequency halts. Implemented MVP.
40. Add a global kill switch that can flatten positions, cancel open orders, and stop the engine. Implemented MVP.
41. Add manual operator controls for pause, resume, cancel-all, flatten, and disable-new-orders. Implemented MVP.
42. Add market calendar handling for holidays, half days, early closes, pre-market, regular session, and after-hours policy. Implemented MVP.
43. Add websocket heartbeat monitoring, reconnect backoff, subscription replay, and stale-stream alarms. Implemented MVP.
44. Add rate-limit-aware REST clients with retries, jitter, request logging, and broker error classification. Implemented MVP.
45. Add historical Alpaca pagination and cache hydration for multi-symbol backtests. Implemented MVP.
46. Add corporate action handling for splits, dividends, symbol changes, and adjusted/unadjusted price policies. Implemented MVP.
47. Add data quality gates for duplicate bars, missing bars, out-of-order events, bad OHLC relationships, and extreme gaps. Implemented MVP.
48. Add live-vs-historical data normalization checks so strategies receive the same schema in both modes. Implemented MVP.
49. Add multi-symbol universe loading from config files, watchlists, broker assets, and generated research screens. Implemented MVP.
50. Add strategy scheduling by symbol, timeframe, session window, and warmup requirements. Implemented MVP.
51. Add strategy parameter schemas that are serializable, optimizable, and validated before runs. Implemented MVP.
52. Add a strategy plugin boundary for cleanly registering new strategies without editing core engine code. Implemented MVP.
53. Add portfolio allocation policies for equal weight, volatility targeting, risk parity, and fixed notional sizing. Implemented MVP.
54. Add portfolio-level exposure controls for sector, correlation, beta, symbol concentration, and cash reserve. Implemented MVP.
55. Add order intent models that distinguish signal, target position, generated order, broker order, and fill. Implemented MVP.
56. Add order replacement logic for stops, take-profits, trails, partial fills, and stale limit orders. Implemented MVP.
57. Add bracket, OCO, stop, stop-limit, trailing-stop, market, and limit order abstractions with broker capability checks. Implemented MVP.
58. Add end-of-day policies for holding overnight, flattening, reducing risk, and canceling stale orders. Implemented MVP.
59. Add transaction cost calibration from observed paper fills and quoted spreads. Implemented MVP.
60. Align backtest fills with paper execution assumptions, including bar timing, next-bar fills, spread, slippage, liquidity, and partial fills. Implemented MVP.
61. Add paper/live parity tests that replay the same scenario through backtesting, paper broker, and broker adapter boundaries. Implemented MVP.
62. Add an optimization CLI with grid search, random search, walk-forward runs, train/test splits, and artifact output. Implemented MVP.
63. Add overfitting controls: holdout windows, rolling validation, parameter stability, turnover penalties, and minimum trade counts. Implemented MVP.
64. Add optimization result ranking by CAGR, Sharpe, Sortino, drawdown, win rate, exposure, turnover, and tail risk. Implemented MVP.
65. Add batch backtesting over symbols, strategies, parameter sets, and timeframes with resumable progress. Implemented MVP.
66. Add run manifests that record code version, config, data source, data range, strategy parameters, and dependency versions. Implemented MVP.
67. Add immutable research artifacts for equity curves, orders, fills, trades, metrics, logs, config, and HTML reports. Implemented MVP.
68. Add a dashboard for current paper account state, open orders, recent fills, PnL, risk halts, and engine health. Implemented MVP.
69. Add notifications for startup, shutdown, order submission, fills, rejects, halts, exceptions, and stale data. Implemented MVP.
70. Add structured observability with JSON logs, metrics counters, latency timing, and health checks. Implemented MVP.
71. Add integration tests with mocked Alpaca REST and websocket flows for auth, bars, orders, fills, rejects, and reconnects. Implemented MVP.
72. Add scenario tests for market closed, insufficient buying power, rate limits, partial fills, cancel rejects, and stale data. Implemented MVP.
73. Add deployment profiles for local Windows task scheduling, Docker, and a small always-on server. Implemented MVP.
74. Add secrets handling and `.env` validation that fail fast when required credentials or unsafe combinations are present. Implemented MVP.
75. Add a final paper-trading soak checklist: at least several market sessions, no unreconciled orders, clean restarts, no unhandled exceptions, and metrics matching broker statements. Implemented MVP.

Implemented so far: items 1-75.

The next phase shifts the project from "can run strategies" to "can decide when a strategy deserves capital." The recent bulk research showed that many raw indicator systems fail to beat simple buy-and-hold, so the bot needs benchmark-relative validation, selection, and ensemble logic before it should be trusted for autonomous paper trading decisions:

76. Add benchmark-relative strategy selection so raw strategies are only considered active when they beat buy-and-hold after drawdown, trade-count, and rejection gates. Implemented MVP.
77. Add excess-return research reports that compare every strategy to buy-and-hold per symbol, including excess return, drawdown improvement, upside/downside capture, trade efficiency, and tail risk. Implemented MVP.
78. Add market regime classification for trend, range, volatility expansion/contraction, liquidity quality, and macro-sensitive markets. Implemented MVP.
79. Add a strategy activation layer that maps strategies to eligible regimes instead of letting every strategy trade every market. Implemented MVP.
80. Convert useful but weak standalone systems into reusable filters, including choppiness/range filters, VWAP stretch filters, structure confirmation, FVG context, and liquidity sweep context. Implemented MVP.
81. Add per-symbol strategy scorecards that separate broad-market beta, symbol-specific edge, parameter sensitivity, and benchmark-relative robustness. Implemented MVP.
82. Add ensemble allocation that can choose strategy, benchmark, or cash per symbol based on validated edge and risk constraints. Implemented MVP.
83. Add "do not trade" gates for weak evidence, poor benchmark-relative performance, unstable parameters, high tail risk, low sample size, or excessive turnover.
84. Add cross-market validation that requires a strategy to prove itself across market clusters rather than only on isolated best-fit symbols.
85. Add final autonomous paper-trading candidate selection that promotes only benchmark-relative, regime-aware, risk-gated systems into paper sessions.

Research expansion intermission:

86. Add cross-asset research matrices so testing can span stocks, ETFs, bonds/rates, credit, crypto, FX, commodities, real assets, multiple providers, multiple intervals, and multiple historical windows. Implemented MVP.

Validation hardening phase:

87. Add explicit adjusted-data handling for yfinance and Alpaca so backtests do not accidentally mix raw split/dividend prices with adjusted benchmark data. Implemented MVP.
88. Add requested-window coverage validation so providers cannot silently truncate historical windows without the run failing loudly. Implemented MVP.
89. Add adjusted-OHLC drift handling so tiny provider adjustment artifacts become warnings while material high/low violations remain hard errors. Implemented MVP.
90. Add deterministic backtester invariant tests for long stops, short stops, shorting-disabled rejection, profitable shorts, partial closes, reversals, slippage, commissions, liquidity caps, and metric consistency. Implemented MVP.
91. Add a reusable backtest result validator that checks equity, fills, final flatness, and headline metric agreement. Implemented MVP.
92. Add independent benchmark validation against direct close-to-close math and external adjusted-close data where available. Implemented MVP.
93. Add published-strategy replication infrastructure so known public strategy examples can be rerun through this engine and compared against published stats. Implemented MVP.
94. Add a `replicate` CLI mode and default published SMA crossover suite based on the official backtesting.py GOOG example. Implemented MVP.

Current strategic research read:

The bot should now move from isolated indicator systems toward validated, portfolio-aware strategy families. Recent online research and practitioner evidence point to these candidate lanes:

- Diversified time-series momentum / managed futures across equities, bonds, FX, commodities, crypto, and rates. This is still one of the best-documented systematic anomalies, but recent quant/trend-following drawdowns show it must be regime-aware and reversal-aware.
- Cross-sectional momentum plus value, quality/defensive, carry, and low-volatility style premia. The goal is not one factor, but diversified style exposure with benchmark-relative validation.
- Statistical arbitrage and pairs/cluster relative value, preferably sector/beta-neutral with cointegration/correlation stability, borrow/cost filters, and crash controls.
- Volatility risk premium and option-income systems, but only after adding options data, Greeks, implied-vs-realized volatility, assignment/exercise logic, and tail-risk sizing. This should not be bolted onto the current equity-bar backtester casually.
- Crypto adaptive trend systems using shorter bars, volatility-regime trailing stops, monthly/weekly asset selection, and asymmetric long/short exposure.
- Dynamic allocation overlays that rotate between growth, defensive, cash, bonds, gold/commodities, or volatility hedges using smooth macro/market stress scores rather than brittle if/else regimes.
- Factor-trend systems that trade trends in factors, sectors, yield-curve shape, and relative baskets rather than only single-symbol price trends.
- Market-making/HFT-style systems are top-tier in industry but out of scope until the project has order book data, latency modeling, quote management, queue position, and intraday transaction-cost calibration.

Next phase: research-grade strategy families and capital selection.

95. Add a strategy research catalog that records each candidate system's source, rules, required data, expected edge, published benchmark stats, replication status, and implementation readiness. Implemented MVP.
96. Add a managed-futures/time-series-momentum engine that supports multi-lookback trend signals, volatility targeting, asset-class risk budgets, correlation scaling, and crisis-alpha reporting. Implemented strategy MVP; portfolio-level budgets/correlation/crisis-alpha reporting remain the next allocator/reporting layer.
97. Add a cross-sectional momentum and style-premia engine for ranking symbols by momentum, value proxy, quality proxy, low-volatility/defensive score, and carry proxy where data is available. Implemented research ranking MVP with OHLCV proxies and optional carry/yield columns.
98. Add a pairs/stat-arb research module with pair discovery, rolling correlation, cointegration tests, spread z-scores, half-life estimation, beta neutrality, borrow/cost checks, and portfolio-level spread allocation. Implemented dependency-light research MVP with correlation, hedge ratio, spread z-score, half-life, trade legs, and a cointegration proxy; formal cointegration, beta/sector neutrality, borrow checks, and portfolio spread allocation remain next.
99. Add a volatility-risk-premium roadmap gate: options chains, implied volatility surfaces, Greeks, option fills, assignment/exercise modeling, margin, and tail stress tests must exist before any option-income strategy is promoted. Implemented promotion-gate MVP with required capability checks, option contract/quote/Greeks/position models, and intrinsic-value tail-stress scaffolding.
100. Add a crypto adaptive-trend suite using 4h/6h/1d bars, rolling Sharpe asset selection, volatility-based trailing stops, drawdown gates, and asymmetric long/short allocation. Implemented strategy and selection MVP with rolling Sharpe, volatility targeting, trailing ATR stops, drawdown gates, asymmetric long/short exposure, and crypto universe ranking.
101. Add dynamic allocation systems that rotate between growth, defensive, cash, bonds, gold/commodities, and volatility hedges using smooth scores for rates, trend, drawdown, VIX/volatility, liquidity, and crowding. Implemented portfolio overlay MVP with smooth market stress scoring and sleeve-level allocation across growth, defensive, bonds, commodities, hedges, and cash.
102. Add factor-trend research for sectors, industries, value-vs-growth, high-beta-vs-low-volatility, quality, and yield-curve-shape baskets. Implemented factor-spread trend MVP for style, sector, size, defensive/cyclical, and rates ETF proxy baskets with long/short legs and trend scores.
103. Add a strategy ensemble allocator that combines independent strategy families by marginal contribution to risk, correlation, drawdown overlap, and benchmark-relative edge rather than raw return alone. Implemented strategy-family ensemble MVP with benchmark-relative edge, drawdown, volatility, return-correlation, drawdown-overlap, family caps, strategy caps, and cash reserve handling.
104. Add market-cluster validation so each system must prove where it works: equity bull trends, equity bear markets, bond selloffs, rate-cut cycles, inflationary commodities, FX carry regimes, crypto bull/bear cycles, and choppy mean-reverting tapes. Implemented market-cluster validation MVP with named symbol clusters, benchmark-relative pass/fail gates, per-strategy summaries, and promotion pass-rate checks.
105. Add cost capacity analysis: turnover, spread sensitivity, volume participation, borrow availability, short fees, slippage stress, and degradation curves by capital size. Implemented MVP with strategy capacity profiles, capital degradation reports, borrow availability gates, slippage stress assumptions, ranking helpers, and default research config.
106. Add walk-forward model governance: anchored/rolling train-test splits, parameter stability reports, false-discovery controls, and no-retune holdouts. Implemented MVP with rolling/anchored train-test optimization, parameter-mode champion selection, train-to-test false-discovery proxy, frozen-parameter holdout testing, promotion pass/fail reasons, and default governance config.
107. Add a promotion pipeline from research candidate to paper candidate: source rules captured, data validated, replication or benchmark comparison complete, out-of-sample pass, cost stress pass, risk gates pass, and paper-session manifest created. Implemented MVP with candidate evidence contracts, promotion policies, explicit gate reports, governance/capacity/validation integration, paper-session manifests, and default promotion config.
108. Add paper-trading scorecards that compare expected backtest behavior to live paper fills, slippage, missed trades, rejected orders, and broker account statements. Implemented MVP with expected-vs-observed paper scorecards, slippage/missed-fill/reject/equity-drift/reconciliation gates, broker statement payloads, backtest-to-paper helpers, and default scorecard thresholds.
109. Add live data drift monitors comparing Alpaca/yfinance/secondary sources on recent bars, gaps, adjusted prices, and corporate-action behavior. Implemented MVP with provider snapshots, cross-source OHLC/close drift reports, stale-source checks, adjustment-mode warnings, split-like corporate-action mismatch detection, multi-source comparison helpers, and default drift thresholds.
110. Add a final "trade/no-trade committee" layer that can choose strategy, benchmark, hedge, reduce exposure, or sit in cash based on validated edge and current regime quality. Implemented MVP with final decision context, explicit committee gates, strategy/benchmark/cash/hedge/reduce actions, paper-scorecard/data-drift/promotion/regime inputs, and default policy config.

Final runtime handoff phase:

111. Add a committee-to-execution planning bridge that turns final trade/no-trade decisions into target-position and generated-order intents without submitting broker orders directly. Implemented MVP with target sizing, cash flattening, exposure reduction, hedge targeting, missing-price warnings, and execution-plan serialization.
112. Add a paper-session supervisor that loads promoted manifests, current committee context, runtime account state, and latest prices, then records dry-run plans before broker submission is allowed. Implemented MVP with dry-run session preparation, promoted-manifest checks, committee decision capture, execution-plan generation, account/price snapshots, immutable artifact writes, and submission-readiness flags.
113. Add a capital ledger for candidate strategies so multiple promoted systems compete for cash, hedge budget, symbol limits, and family-level exposure caps before orders are generated. Implemented MVP with capital requests, allocation reports, edge/priority ranking, cash reserve enforcement, symbol/strategy/family caps, hedge-budget accounting, and committee-decision conversion helpers.
114. Add end-to-end paper session artifacts that persist committee inputs, committee decisions, generated execution plans, submitted broker orders, fills, reconciliation, and post-session scorecards as one audit trail.
115. Add a final autonomous paper-trading command that can run one guarded session from config: data sync, drift check, regime classification, committee decision, dry-run plan, optional paper submit, reconciliation, and report output.

Dependency and performance hardening phase:

116. Split dependencies into explicit install profiles for base runtime, broker integrations, research acceleration, reporting, and development, and add a capability audit so optional packages are visible at runtime. Implemented MVP with layered requirement files, pinned current core packages, broker/research/reporting/dev profiles, dependency capability reporting, README install guidance, and regression tests.
117. Add Parquet/Arrow historical data and artifact storage for high-volume bars, backtest matrices, and optimization outputs while preserving JSON/JSONL compatibility for inspection.
118. Add DuckDB-backed research querying over bulk backtest artifacts, paper-session artifacts, market data caches, and optimization results.
119. Add Optuna optimization as an optional optimizer backend with study persistence, pruning, seeded samplers, walk-forward objective functions, and artifact output.
120. Add statistical research upgrades using scipy/statsmodels for cointegration, regression/factor exposure, confidence intervals, p-value controls, and regime robustness tests.
121. Add a benchmark/profiling harness that times indicator calculation, strategy generation, backtest loops, bulk research, storage writes, and paper-session planning before choosing acceleration packages.
122. Add targeted acceleration only after profiling: numba for tight numeric loops or polars for lazy wide-data research, with pandas-compatible boundaries and equivalence tests.
