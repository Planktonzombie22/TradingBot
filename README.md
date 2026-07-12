# TradingBot

TradingBot is a modular trading research framework for building strategies, running historical simulations, generating reports, and moving toward autonomous Alpaca paper trading.

The project is intentionally split into small subsystems: data loading, strategy logic, indicators, backtesting, live/paper runtime, broker execution, risk controls, storage, and reporting. The goal is not to hide trading complexity behind one giant script. The goal is to make every piece explicit enough that it can be tested, replaced, and eventually trusted.

Current status: this is a working MVP and research scaffold. It can run sample/yfinance-style backtests, generate JSON/HTML reports, replay stream events, and connect scaffolding for Alpaca data and paper execution. It is not yet ready for unattended real-money live trading. The production readiness path is tracked in `ROADMAP.md`.

## What Works Today

- Offline backtests through `main.py backtest`.
- Strategy execution through the shared `TradingApplication` workflow.
- Sample market data for deterministic local runs.
- yfinance historical data adapter, subject to local network/data availability.
- Alpaca historical and websocket scaffolding using `.env` credentials.
- A runtime engine for replay-style stream processing.
- A paper account model for fills, cash, positions, and equity updates.
- Backtesting architecture with pluggable execution, slippage, commission, liquidity, margin, risk, ledger, and metrics components.
- Strategy registry with parameter validation.
- Indicator modules with tests for core calculations.
- JSONL storage for run artifacts.
- JSON, HTML, text summary, and matplotlib plot reporting.
- Walk-forward, grid-search, and multi-symbol research utilities at the architecture/MVP level.
- Benchmark-relative strategy selection, excess-return research reports, market-regime classification, reusable context filters, per-symbol scorecards, ensemble allocation, and regime-based strategy activation at the architecture/MVP level.
- Cross-asset research matrices for testing stocks, ETFs, bonds/rates, credit, crypto, FX, commodities, and real assets across multiple windows and intervals.
- Test coverage for the major boundaries.

## What Is Not Finished Yet

The bot should not be treated as a fully autonomous production trader yet. The remaining work includes broker reconciliation, durable order state, crash recovery, idempotent order submission, stronger data quality gates, hard kill switches, market-session edge cases, robust paper-trading soak tests, and deployment supervision.

See `ROADMAP.md` for the complete itemized path from the current MVP to autonomous Alpaca paper trading and, eventually, a deliberately guarded live-trading unlock.

## Quick Start

Create or use the existing virtual environment:

```powershell
python -m venv trading_env
trading_env\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` points at the full local development profile in this workspace. Install narrower profiles when you want a lighter environment:

```powershell
trading_env\Scripts\python.exe -m pip install -r requirements\base.txt
trading_env\Scripts\python.exe -m pip install -r requirements\broker.txt
trading_env\Scripts\python.exe -m pip install -r requirements\research.txt
trading_env\Scripts\python.exe -m pip install -r requirements\reporting.txt
trading_env\Scripts\python.exe -m pip install -r requirements\acceleration.txt
```

Run the default offline backtest:

```powershell
trading_env\Scripts\python.exe main.py
```

Run a deterministic sample backtest:

```powershell
trading_env\Scripts\python.exe main.py backtest --provider sample --strategy buyHold --symbol SPY
```

Write a JSON backtest report:

```powershell
trading_env\Scripts\python.exe main.py backtest --provider sample --strategy buyHold --output reports\sample-backtest.json
```

Write an HTML report:

```powershell
trading_env\Scripts\python.exe main.py report --provider sample --strategy buyHold --html-output reports\backtest.html
```

Run the replay-stream MVP:

```powershell
trading_env\Scripts\python.exe main.py stream --provider sample --strategy buyHold
```

Run the paper runtime path with sample data:

```powershell
trading_env\Scripts\python.exe main.py paper --provider sample --strategy buyHold
```

Run one guarded autonomous paper-session dry run with sample data:

```powershell
trading_env\Scripts\python.exe main.py paper-session --provider sample --strategy buyHold --store-dir runs\paper-session-sample
```

Use yfinance historical data when network access is available:

```powershell
trading_env\Scripts\python.exe main.py backtest --provider yfinance --strategy tuffSystem --symbol SPY --period 2y --interval 1d
```

Run a reproducible Alpaca historical window:

```powershell
trading_env\Scripts\python.exe main.py backtest --provider alpaca --strategy tuffSystem --symbol SPY --interval 1d --start 2024-01-01T00:00:00Z --end 2024-12-31T00:00:00Z
```

Optimize the original Tuff System strategy from a reusable parameter-grid file:

```powershell
trading_env\Scripts\python.exe main.py optimize --provider alpaca --strategy tuffSystem --symbol SPY --interval 1d --start 2023-01-01T00:00:00Z --end 2025-12-31T00:00:00Z --param-grid-file configs\optimization\tuff_system_daily.json
```

Replay a strategy with parameter settings from a JSON file:

```powershell
trading_env\Scripts\python.exe main.py backtest --provider alpaca --strategy tuffSystem --strategy-params-file configs\strategies\tuff_system_default.json --symbol SPY --interval 1d --start 2023-01-01T00:00:00Z --end 2025-12-31T00:00:00Z
```

## Alpaca Setup

Copy `.env.example` to `.env` and fill in credentials:

```dotenv
PAPER_TRADING=true
DATA_PROVIDER=alpaca
EXECUTION_MODE=dry-run
ALLOW_LIVE_TRADING=false
STATE_DB_PATH=runs/tradingbot.sqlite3

ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_STREAM_URL=wss://stream.data.alpaca.markets/v2/iex
```

Then run an Alpaca stream/paper entry point:

```powershell
trading_env\Scripts\python.exe main.py paper --provider alpaca --symbol SPY
```

Or run the autonomous paper-session dry-run path, which loads data, classifies regime, asks the trade committee for a decision, generates a dry-run execution plan, and writes one audit trail:

```powershell
trading_env\Scripts\python.exe main.py paper-session --provider alpaca --symbol SPY --store-dir runs\paper-session-alpaca
```

Add `--comparison-provider yfinance` or another supported provider when you want the session to include a cross-source data drift report before committee approval.

The Alpaca pieces are intentionally conservative. They provide the architecture for historical data, websocket bars, guarded paper-order submission, reconciliation artifacts, and session scorecards. This is still an MVP paper workflow; unattended operation should wait for clean soak sessions and operator monitoring.

Dry-run mode is the default so live data can be tested without accidentally routing broker orders. To enable real Alpaca paper order submission through the broker adapter, use paper credentials, keep `PAPER_TRADING=true`, keep `ALPACA_BASE_URL=https://paper-api.alpaca.markets`, and set:

```dotenv
EXECUTION_MODE=paper
```

or pass:

```powershell
trading_env\Scripts\python.exe main.py paper --provider alpaca --execution-mode paper --symbol SPY
```

For the autonomous session command, broker submission is additionally gated by `--submit-orders`:

```powershell
trading_env\Scripts\python.exe main.py paper-session --provider alpaca --execution-mode paper --symbol SPY --submit-orders
```

## CLI Modes

`main.py` is the current application entry point.

```powershell
trading_env\Scripts\python.exe main.py [mode] [options]
```

Available modes:

- `backtest`: load historical data, create a strategy, run the backtesting engine, print a summary, and optionally write JSON artifacts.
- `stream`: create a market data stream and feed events through the runtime engine without treating the run as broker paper trading.
- `paper`: use the same runtime path as streaming, labeled as the paper-trading workflow. This is the path that will keep gaining broker synchronization and safety controls.
- `paper-session`: run one guarded committee-to-execution paper session from config, write the full audit trail, and optionally submit paper orders with `--submit-orders`.
- `report`: run a backtest and write an HTML report.
- `optimize`: run a parameter grid search and write ranked JSONL optimization artifacts.
- `bulk`: run many symbols across one or more strategies and write JSONL plus a summary report.
- `matrix`: run a cross-asset research matrix, where each group can define its own provider, symbols, intervals, and historical windows.

Common options:

- `--provider`: `sample`, `yfinance`, or `alpaca`.
- `--symbol`: symbol to load and trade, default `SPY`.
- `--symbols`: comma-separated symbol list for `bulk` mode.
- `--symbols-file`: JSON or text watchlist file for `bulk` mode.
- `--max-symbols`: maximum symbols to run in `bulk` mode.
- `--strategy`: registered strategy name, default `buyHold`.
- `--strategies`: comma-separated strategy list for `bulk` mode.
- `--strategy-params`: JSON object of strategy constructor parameters.
- `--strategy-params-file`: JSON file containing strategy constructor parameters.
- `--strategy-param-dir`: directory for bulk-mode per-strategy parameter JSON files.
- `--period`: historical lookback period, default `2y`.
- `--interval`: historical bar interval, default `1d` from the CLI.
- `--start`: optional historical start date/timestamp for providers that support date ranges.
- `--end`: optional historical end date/timestamp for providers that support date ranges.
- `--plot`: show the matplotlib backtest plot.
- `--output`: write a JSON backtest report.
- `--html-output`: write an HTML backtest report in `report` mode.
- `--store-dir`: write JSONL run artifacts under this directory, default `runs`.
- `--execution-mode`: `dry-run` or `paper`. Dry-run is the default; Alpaca paper order submission requires `paper`.
- `--flatten-on-stop`: for `stream`/`paper` modes, submit flattening orders before stopping the run. This is useful for replay sessions and should be used deliberately with broker-backed paper execution.
- `--submit-orders`: for `paper-session` mode, submit generated orders only after the guarded dry-run plan is ready. Requires `--execution-mode paper`.
- `--comparison-provider`: optional secondary provider for `paper-session` data drift checks.
- `--param-grid`: JSON object of parameter lists for `optimize` mode.
- `--param-grid-file`: JSON file containing parameter lists for `optimize` mode. Useful on shells where inline JSON quoting is awkward.
- `--metric`: metric to optimize, default `total_return`.
- `--bulk-output`: JSON summary path for `bulk` mode.
- `--benchmark-strategy`: benchmark strategy for benchmark-relative bulk reports, default `buyHold`.
- `--benchmark-output`: optional JSON path for excess-return and strategy-selection research output from `bulk` mode.
- `--research-matrix-file`: JSON matrix file for `matrix` mode, default `configs\research\cross_asset_matrix.json`.
- `--matrix-output`: JSON summary path for `matrix` mode.

Run a 50-market Alpaca bulk sweep:

```powershell
trading_env\Scripts\python.exe main.py bulk --provider alpaca --symbols-file configs\universes\liquid_etf_80.json --max-symbols 50 --strategies meanReversion,volatilityBreakout,momentumRegime,trendPullback,volumeMomentum,squeezeExpansion --interval 1d --start 2023-01-01T00:00:00Z --end 2025-12-31T00:00:00Z --store-dir runs\bulk-alpaca-research-50 --bulk-output reports\bulk-alpaca-research-50.json
```

Run a benchmark-relative research sweep:

```powershell
trading_env\Scripts\python.exe main.py bulk --provider alpaca --symbols-file configs\universes\liquid_etf_80.json --max-symbols 50 --strategies buyHold,meanReversion,tuffContrarian,gapFade,choppinessRange,vwapValueReversion --benchmark-strategy buyHold --benchmark-output reports\benchmark-relative-research-50.json
```

Run the cross-asset research matrix:

```powershell
trading_env\Scripts\python.exe main.py matrix --research-matrix-file configs\research\cross_asset_matrix.json --strategies buyHold,meanReversion,tuffContrarian,gapFade,choppinessRange --max-symbols 10 --store-dir runs\cross-asset-matrix --matrix-output reports\cross-asset-matrix.json
```

Cross-asset universe config lives in `configs\universes\cross_asset_core.json`. The matrix config currently covers large-cap stocks, rates/bonds/credit, crypto via yfinance symbols, commodities/real assets, and FX pairs.

## Dependency Profiles

The project uses layered requirements so the minimal runtime stays light while research and paper-trading work can opt into heavier libraries deliberately.

- `requirements.txt`: workspace default install; currently delegates to `requirements\dev.txt`.
- `requirements\base.txt`: pandas/numpy/yfinance/dotenv/requests/websocket-client.
- `requirements\broker.txt`: Alpaca SDK, crypto exchange connectivity, async/websocket helpers.
- `requirements\research.txt`: scipy, statsmodels, pyarrow, DuckDB, Optuna, and progress tooling for larger research runs.
- `requirements\reporting.txt`: matplotlib, Plotly, seaborn, Rich, and Jinja2.
- `requirements\acceleration.txt`: optional `numba` and `polars` candidates for tasks that profiling identifies as slow.
- `requirements\dev.txt`: full local development profile, including tests and notebooks.

Use `src.utils.dependencies.dependency_summary()` to inspect which optional capability packages are installed. Use `src.utils.profiling` to measure hotspots and `src.utils.acceleration` to turn benchmark results into conservative `numba`/`polars` recommendations with equivalence checks before replacing pandas/Python code.

## Programmatic Usage

Use `TradingApplication` when you want the standard app wiring:

```python
from src.app import TradingApplication
from src.config import RuntimeConfig

app = TradingApplication(RuntimeConfig())
data = app.load_data()
strategy = app.create_strategy()
result = app.run_backtest(data, strategy)
```

Use lower-level packages directly when building research scripts:

```python
from src.backtesting import BacktestEngine, run_backtest
from src.reporting import format_backtest_summary, write_backtest_report
```

## Configuration

Configuration starts in `src/config/settings.py`, which loads `.env` through `python-dotenv`. Structured runtime settings are defined in `src/config/profiles.py`:

- `MarketDataConfig`: symbol, period, interval, date range, and provider.
- `AlpacaConfig`: API key, secret key, REST base URL, stream URL, and feed.
- `AccountConfig`: initial cash, margin ratio, risk fraction, and base currency.
- `StrategyConfig`: strategy name and strategy parameters.
- `RuntimeConfig`: the top-level config object passed through the application.

`load_runtime_config()` merges defaults, environment-derived settings, and CLI/programmatic overrides. This keeps command-line execution and script execution on the same configuration path.

Important defaults:

- `PAPER_TRADING=true`
- `DATA_PROVIDER=yfinance`
- `EXECUTION_MODE=dry-run`
- `ALLOW_LIVE_TRADING=false`
- `STATE_DB_PATH=runs/tradingbot.sqlite3`
- `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- `ALPACA_DATA_STREAM_URL=wss://stream.data.alpaca.markets/v2/iex`
- `MARKET=SPY`
- `PERIOD=2y`
- `INTERVAL=4h`
- `DEFAULT_STRATEGY=tuffSystem`

## Project Structure

```text
src/
  app.py                 High-level workflow boundary.
  backtesting/           Historical simulation engine and research tools.
  config/                Runtime config, defaults, and .env loading.
  data/                  Historical feeds, streams, sample data, quality checks.
  engine/                Runtime stream/paper engine and account state.
  execution/             Broker interfaces, paper broker, Alpaca adapter scaffolding.
  indicators/            Pure technical indicator calculations.
  models/                Shared domain records.
  portfolio/             Portfolio and performance helpers.
  reporting/             JSON, HTML, summary, and plot output.
  risk/                  Position sizing, stop losses, portfolio limits.
  storage/               JSONL artifact storage.
  strategies/            Strategy base class, implementations, registry, parameters.
  tests/                 Unit and integration-style tests.
  utils/                 Logging, retry, timing, and helper utilities.
```

The old `src/backtest` compatibility package was removed. Historical simulation now lives in `src/backtesting`; reports live in `src/reporting`. This avoids having two almost-identical package names with different responsibilities.

## Architecture Overview

The primary workflow is:

1. `main.py` parses CLI arguments.
2. `load_runtime_config()` builds a `RuntimeConfig`.
3. `TradingApplication` wires together data, strategy, backtesting, or runtime components.
4. The selected mode runs one of the major flows:
   - Backtest flow: data feed -> strategy -> backtesting engine -> report/storage.
   - Stream/paper flow: market data stream -> runtime engine -> signal/order/fill events -> storage/logging.
5. Reporting and storage capture outputs for inspection.

The design is deliberately boundary-heavy. Strategies do not submit orders directly. Indicators do not know about portfolio state. Broker adapters do not calculate indicators. Backtesting uses interfaces for execution, costs, liquidity, margin, ledger, risk, and metrics so each assumption can be swapped without rewriting the whole engine.

## Domain Models

`src/models` contains portable objects used across the system:

- `Bar`: normalized market OHLCV data.
- `Signal`: strategy intent such as buy, sell, hold, or close.
- `Order`: generated order request and broker-facing order metadata.
- `Trade`: completed trade lifecycle information.
- `Position`: current symbol exposure.
- `Portfolio`: aggregate account/position state.
- `BacktestResult`: equity, money available, trades, fills, rejections, events, and metrics.

These models keep the rest of the code from passing loose dictionaries everywhere. Some provider adapters still translate raw payloads at the boundary, but internal code should prefer these records.

## Data Layer

`src/data` is responsible for getting market data into a normalized shape.

Key components:

- `DataFeed`: historical data interface.
- `YFinanceDataFeed`: yfinance historical adapter.
- `AlpacaHistoricalDataFeed`: Alpaca historical adapter scaffold.
- `MarketDataManager`: chooses the correct data provider based on config.
- `normalize_ohlcv_frame()` and `normalize_bar()`: canonical historical/live data normalization helpers.
- `MarketDataStream`: stream interface.
- `ReplayMarketDataStream`: deterministic stream from local/sample bars.
- `YFinancePollingStream`: polling-style yfinance stream scaffold.
- `AlpacaMarketDataStream`: websocket stream scaffold for Alpaca bars with health tracking, bounded reconnects, stale-stream detection, and subscription replay.
- `DataQualityValidator`: checks for missing, stale, malformed, or suspicious bars.
- `MarketSessionCalendar`: session classification for regular hours, pre-market, after-hours, holidays, and early closes.
- `HistoricalDataCache`: optional CSV cache for hydrated historical data.
- `CorporateActionPolicy`: split, dividend, symbol-change, raw, split-adjusted, and total-return adjustment scaffolding.
- `sample_ohlcv()`: deterministic local OHLCV data for tests and offline demos.

Alpaca REST calls flow through `AlpacaRestClient`, which centralizes authentication headers, retries, HTTP/network error classification, and timeout handling for both market data and paper-broker requests.
Alpaca historical requests follow `next_page_token` pagination and can optionally hydrate/read from `HistoricalDataCache`.
Historical and live bars are normalized through the same schema boundary before strategies see them. Data quality gates cover duplicate timestamps, missing/null bars, invalid OHLC relationships, non-positive prices, negative volume, out-of-order events, stale events, extreme high/low ranges, and possible split-like price jumps.

Design choice: provider-specific code stays at the edges. Strategies and engines should receive normalized frames/events instead of knowing whether the data came from yfinance, Alpaca, or a replay stream.

## Indicators

`src/indicators` contains pure indicator calculations:

- Moving averages and momentum: SMA, EMA, DEMA, MACD, ROC, RSI, Stochastic Oscillator.
- Volatility and channels: ATR, SuperTrend, Bollinger Bands, Donchian Channel, Keltner Channel.
- Price action and structure: Fair Value Gap, Swing Points, Liquidity Sweep, Market Structure Break, Pivot Points.
- Volume and money flow: OBV, VWAP, Anchored VWAP, Money Flow Index, Chaikin Money Flow, Relative Volume.
- Regime and risk shape: ADX, Aroon, Vortex Indicator, Choppiness Index, Efficiency Ratio, Ulcer Index, Elder-Ray Index, Ichimoku Cloud, Rolling Z-score.

The indicators are designed as calculation modules, not trading systems. They should not manage positions, emit broker orders, or depend on account state. This makes them reusable across strategies, backtests, optimizers, and reports.

## Strategies

`src/strategies` defines the strategy boundary.

Important files:

- `base.py`: the base `Strategy` contract.
- `buy_hold.py`: simple buy-and-hold strategy for deterministic MVP tests.
- `tuff_system.py`: indicator-based strategy.
- `research_systems.py`: additional research systems for momentum/regime, mean-reversion, volatility breakout, trend pullback, volume momentum, squeeze expansion, gap/structure, VWAP value, liquidity sweep, choppiness/range, and cloud/trend experiments.
- `parameters.py`: parameter specs and validation.
- `registry.py`: maps strategy names to classes and schemas, and exposes `register_strategy()` for plugin-style extensions.
- `scheduling.py`: symbol/timeframe/session/warmup scheduling policy.

Registered strategies:

- `buyHold`
- `aroonVortexTrend`
- `choppinessRange`
- `fvgRebalance`
- `meanReversion`
- `momentumRegime`
- `squeezeExpansion`
- `gapFade`
- `ichimokuCloudTrend`
- `liquiditySweepReversal`
- `skewReversion`
- `structureBreakoutRetest`
- `tuffConsensus`
- `tuffContrarian`
- `tuffRegimeSwitch`
- `tuffSystem`
- `trendPullback`
- `volatilityBreakout`
- `volumeMomentum`
- `vwapValueReversion`

Design choice: strategies emit `Signal` objects. They do not execute trades themselves. This keeps strategy intent separate from execution details such as slippage, margin, commissions, liquidity, broker limitations, or account state.

Strategy parameter specs are serializable through `strategy_schema()`, including type, default, min/max bounds, descriptions, and optional optimization candidate values. External modules can register new strategies with `register_strategy()` without editing the built-in registry.

`UniverseLoader` can build multi-symbol universes from direct config symbols, JSON/text watchlists, broker asset payloads, or simple generated research screens such as `top_volume`. `StrategySchedule` gates runtime execution by symbol, timeframe, session policy, and required warmup bars.

Tuff descendants are experimental systems built from the original Tuff ingredients:

- `tuffConsensus`: turns SuperTrend, DEMA, RSI, ADX, MACD, and ROC into a voting model.
- `tuffRegimeSwitch`: uses ADX to switch between Tuff-style trend following and band mean reversion.
- `tuffContrarian`: fades statistically stretched Tuff trend thrusts.

Additional experimental systems:

- `gapFade`: fades large prior-bar gaps when the bar rejects the gap direction.
- `skewReversion`: fades stretched return z-scores when rolling skew suggests one-sided exhaustion.
- `fvgRebalance`: trades continuation after fair value gaps appear and rebalance.
- `liquiditySweepReversal`: fades wick sweeps of recent highs/lows with money-flow confirmation.
- `structureBreakoutRetest`: trades market-structure breaks when relative volume and pivots agree.
- `vwapValueReversion`: fades large distance from anchored VWAP when money flow starts to normalize.
- `ichimokuCloudTrend`: follows cloud direction using Tenkan/Kijun alignment and cloud bias.
- `choppinessRange`: trades Bollinger extremes only when choppiness suggests a range.
- `aroonVortexTrend`: requires Aroon, Vortex, Elder-Ray, and efficiency agreement for trend entries.

## Backtesting

`src/backtesting` is the historical simulation package. It is the center of the research workflow.

Important components:

- `BacktestEngine`: runs a strategy over historical bars.
- `BacktestConfig`: simulation settings such as initial cash, margin ratio, risk fraction, and base currency.
- `PandasStrategySignalProvider`: adapts strategy output into the simulation flow.
- `RiskPercentOrderFactory`: turns signal intent into orders sized by configured risk.
- `BarExecutionModel`: fills orders against bar data.
- `CashMarginLedger`: tracks cash, positions, equity, and money available.
- `SimpleMarginModel`: validates buying power/margin assumptions.
- `CompositeRiskModel`: applies risk controls before execution.
- Slippage models: `NoSlippageModel`, `FixedBpsSlippageModel`, `SpreadVolumeSlippageModel`.
- Commission models: `ZeroCommissionModel`, `BpsCommissionModel`, broker presets.
- Liquidity models: `UnlimitedLiquidityModel`, `VolumeShareLiquidityModel`.
- Borrow cost models: `NoBorrowCostModel`, `AnnualizedBorrowCostModel`.
- `BasicMetricsCalculator`: calculates performance metrics.
- `StrategySelectionPolicy`: gates strategies against a benchmark before allowing them to deserve capital.
- `BenchmarkRelativeReport`: summarizes excess return, drawdown improvement, capture behavior, trade efficiency, and tail risk versus `buyHold`.
- `MarketRegimeProfile`: classifies trend/range, volatility, liquidity, and macro-sensitivity context.
- `StrategyActivationReport`: activates only the strategies whose design modes match the current market regime.
- `ResearchFilterSnapshot`: evaluates reusable contexts such as choppiness/range, VWAP stretch, structure confirmation, fair value gaps, and liquidity sweeps.
- `SymbolResearchScorecard`: combines benchmark return, selected strategy, best edge, regime, active strategies, filters, and parameter sensitivity for one market.
- `EnsembleAllocationPlan`: chooses strategy, benchmark, or cash per symbol and assigns conservative weights.
- `ResearchMatrixConfig`: expands asset groups, providers, intervals, and windows into repeatable cross-asset bulk research jobs.
- `InMemoryEventSink`: captures simulation events.

Research helpers:

- `run_backtest()`: simple compatibility function for scripts.
- `run_multi_symbol_backtest()`: multi-symbol backtest helper.
- `grid_search()`: parameter optimization helper.
- `run_optuna_optimization()`: optional Optuna optimizer backend with seeded sampling, study persistence, categorical/ranged parameter spaces, and holdout scoring.
- `run_walk_forward()`: walk-forward research helper.
- `rank_optimization_results()` and `overfitting_report()`: optimizer ranking and overfit diagnostics.
- Statistical research helpers: confidence intervals, cointegration tests, factor exposure regressions, and Benjamini-Hochberg p-value adjustment when the research dependency profile is installed.
- `BatchBacktestRunner`: resumable batch runner for symbols, strategies, and parameter sets.
- `run_bulk_backtests()`: mass backtesting helper for many symbols and strategies.

Design choice: backtesting assumptions are modular. This matters because unrealistic fills are one of the easiest ways to fool yourself in trading research. The architecture separates signal generation from order sizing, risk, execution, slippage, commissions, liquidity, margin, ledger updates, and metrics.

Sizing is stop-risk based. For entry signals with a stop, the default order factory sizes roughly as `equity * risk_fraction / abs(entry_price - stop_price)`, then caps size by available buying power. This is correct for the current research abstraction, but live/paper broker execution still needs symbol-specific margin rules, borrow availability, min order size, gap-through-stop handling, partial fills, and broker-side rejects before sizing can be considered production-complete.

Execution assumptions can be grouped with `BacktestExecutionProfile`, which builds a bar execution model from paper-like settings such as price column, spread, market impact, commission, and max volume share. `TransactionCostCalibration` can estimate spread/impact settings from observed paper fills and quoted bid/ask data. `ExecutionParityScenario` replays a single order through backtest execution and the paper broker boundary to catch obvious status or quantity drift.

## Runtime Engine

`src/engine` is separate from `src/backtesting`.

Backtesting answers: "What would have happened historically under these simulation assumptions?"

Runtime answers: "What should happen as market events arrive now?"

Runtime components:

- `TradingEngine`: consumes stream events, asks the strategy for signals, produces runtime events, and updates account state.
- `EngineEvent`: structured runtime event object.
- `EngineEventType`: event categories such as started, stopped, signal, order, fill, or error.
- `EngineState`: lifecycle state for the runtime loop.
- `PaperAccountState`: in-memory account state for paper fills.
- `RuntimePosition`: live/paper position representation.

Design choice: runtime execution and backtesting are intentionally different packages. They share concepts, but they should not collapse into the same loop because real-time trading has failures that historical simulation does not: reconnects, duplicate events, stale data, broker rejects, partial fills, restarts, and account reconciliation.

## Execution And Brokers

`src/execution` contains broker-facing abstractions:

- `Broker`: interface for broker adapters.
- `PaperBroker`: local paper broker scaffold.
- `AlpacaPaperBroker`: Alpaca paper REST adapter scaffold.
- `ExecutionReport`: normalized order/fill/reconciliation result.
- `mark_order()`: helper for order state transitions.
- Intent models for signal, target position, generated order, broker order, and fill.
- Replacement policies for stale market/limit order handling.
- Bracket/OCO/order-capability plans.
- End-of-day policies for hold, cancel-open-orders, flatten, and reduce behavior.

The current implementation is a base for paper trading, not a final unattended broker control system. Before autonomous paper trading is considered complete, the broker layer needs durable state, reconciliation loops, idempotent client order IDs, restart recovery, and stronger operational controls.

The runtime now includes MVP operator controls for `pause`, `resume`, `disable_orders`, `enable_orders`, `cancel_all_orders`, `flatten_positions`, and `kill_switch`. Configurable runtime risk limits can halt the engine on max daily loss, max drawdown, max position notional, max order notional, max open orders, or max order frequency.

## Risk

`src/risk` contains strategy-independent risk logic:

- Position sizing.
- Stop-loss policy.
- Portfolio exposure limits.
- Risk manager boundaries.

Risk exists in both research and runtime contexts. In backtesting, risk affects simulated order acceptance and sizing. In runtime/paper trading, risk must eventually become a hard safety layer before any broker order is submitted.

## Portfolio

`src/portfolio` contains portfolio state and performance helpers. This layer is intended for portfolio-level analytics and allocation work that should not live inside individual strategies.

Examples of future responsibility:

- Symbol-level exposure.
- Portfolio equity.
- Portfolio performance.
- Allocation models.
- Concentration and correlation-aware decisions.

Current allocation policies include equal weight, fixed notional, volatility target, and risk parity. Portfolio risk controls cover symbol concentration, gross exposure, sector exposure, pairwise correlation, cash reserve, and net beta exposure.

## Storage

`src/storage` currently provides `JsonlStore` and `SQLiteStateStore`.

The CLI uses this to write run artifacts such as:

- Equity points.
- Fill records.
- Engine events.

`SQLiteStateStore` persists broker-facing state:

- Orders.
- Execution reports.
- Account snapshots.
- Position snapshots.

It can also rebuild a local `PaperBroker` from persisted orders and reports, which is the first startup-recovery step for paper trading. JSONL is still useful for MVP inspection because it is simple, append-friendly, and easy to diff; SQLite is the durable path for broker state that must survive restarts.

`RunManifest` and `ImmutableArtifactStore` provide the research artifact boundary. A manifest records run type, strategy, symbols, config, data source, dependency versions, and code version when available. Immutable artifact writes create a run-specific directory and refuse accidental overwrite by default.

`ParquetArtifactStore` and `HistoricalDataCache(storage_format="parquet")` provide optional columnar storage for high-volume research outputs and historical bars. Parquet support requires the research dependency profile:

```powershell
trading_env\Scripts\python.exe -m pip install -r requirements\research.txt
```

CSV, JSON, and JSONL remain the default inspection-friendly formats.

`DuckDBResearchStore` provides an optional local query layer over JSONL and Parquet artifacts. This is intended for large bulk backtest runs, optimization sweeps, and paper-session artifact inspection without loading everything into Python first. DuckDB support also lives in `requirements\research.txt`.

## Reporting

`src/reporting` owns output and presentation:

- `summary.py`: text summary and JSON payload generation.
- `html.py`: HTML backtest report generation.
- `plots.py`: matplotlib backtest plots.

This package is deliberately separate from `src/backtesting`. The backtesting engine should produce results; reporting should decide how to display or serialize them.

## Logging And Utilities

`src/utils` contains small cross-cutting helpers:

- `logger.py`: logging setup.
- `retry.py`: retry/backoff utilities.
- `timers.py`: timing helpers.
- `profiling.py`: benchmark suite helpers for timing indicators, strategy generation, backtest loops, bulk research, storage writes, and paper-session planning before choosing acceleration packages.
- `acceleration.py`: profiling-driven acceleration recommendations and equivalence checks for optional `numba` or `polars` implementations.
- `helpers.py`: legacy/general helpers.

Logging is currently enough for the MVP and supports structured JSON logs plus rotating file output.

`src/monitoring` provides MVP operational visibility:

- `DashboardSnapshot`: account, open orders, recent fills, risk halt state, and health payloads.
- `NotificationRouter`: startup, shutdown, order, fill, error, and halt notifications routed to a sink.
- `MetricsRegistry`: counters, gauges, and latency/timing samples.
- `HealthCheck`: explicit health check wrappers.

`validate_runtime_environment()` checks `.env`/runtime safety before Alpaca data or paper execution, including required credentials, paper endpoint safety, execution mode, and live-trading unlock warnings.

`src/deployment` contains local Windows task, Docker, and small-server profile scaffolds. `docs/PAPER_TRADING_SOAK_CHECKLIST.md` defines the final paper-trading soak gates.

## Testing

Run all checks:

```powershell
trading_env\Scripts\python.exe -m compileall src
trading_env\Scripts\python.exe -m pytest src\tests
```

The tests currently cover:

- App-level MVP workflows.
- Alpaca integration scaffolding.
- Config loading.
- Data streams and quality checks.
- Execution, exits, calendar, logging, and retry utilities.
- Indicators.
- Portfolio risk and cost models.
- CLI/reporting behavior.
- Backtesting research tools.
- Storage.
- Strategy behavior.
- Roadmap expectations.

## Design Principles

1. Separate intent from execution.

Strategies emit signals. Order factories, risk models, execution models, brokers, and ledgers decide what happens next.

2. Keep provider code at the boundary.

Alpaca, yfinance, and sample data should normalize into shared internal shapes before strategies or engines see them.

3. Make backtesting assumptions explicit.

Slippage, commissions, liquidity, borrow costs, margin, risk, and metrics are separate components so research results can be understood and improved.

4. Keep runtime separate from historical simulation.

Live/paper trading has reconnects, stale streams, broker state, rejects, and crash recovery. Those concerns deserve their own engine.

5. Prefer small replaceable modules.

The project should be easy to extend by swapping a feed, strategy, risk model, broker adapter, report writer, or optimizer without rewriting everything.

6. Treat safety as architecture, not decoration.

Before autonomous paper trading is complete, risk halts, kill switches, reconciliation, durable state, and deployment supervision need to be first-class components.

## Current Roadmap

`ROADMAP.md` is the authoritative completion checklist.

Items 1-30 are implemented at the MVP/scaffold level. Production paper-trading readiness starts at item 31 and includes the final pieces needed for real autonomous Alpaca paper trading:

- Account sync and broker reconciliation.
- Idempotent order submission.
- Durable persisted state.
- Crash recovery.
- Dry-run and paper-trading safety modes.
- Max-loss and exposure halts.
- Kill switch and operator controls.
- Market calendar completeness.
- Websocket reconnect and stale-data handling.
- Historical data pagination and caching.
- Corporate action handling.
- Multi-symbol universe support.
- Portfolio allocation.
- Order lifecycle accuracy.
- Optimization workflows.
- Overfitting controls.
- Immutable run artifacts.
- Dashboard and notifications.
- Mocked Alpaca integration tests.
- Deployment profiles.
- Secrets validation.
- Paper-trading soak checklist.

Items 1-75 are now implemented at the MVP/scaffold level. This means the architecture is present and test-covered, not that unattended trading has passed a real multi-session paper soak.

## Development Notes

- Prefer `RuntimeConfig` and `load_runtime_config()` for new workflows.
- Prefer `src.backtesting` for historical simulation.
- Prefer `src.reporting` for summaries, plots, JSON, and HTML output.
- Keep generated artifacts under `runs/` or `reports/`.
- Keep `PAPER_TRADING=true` unless live execution is deliberately implemented later.
- Do not connect this to live capital until the broker reconciliation, risk halt, persistence, and kill-switch roadmap items are complete and tested.

Additional deployment notes are in `docs/DEPLOYMENT.md`.
