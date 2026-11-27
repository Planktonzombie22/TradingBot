# TradingBot

TradingBot is a modular trading research framework for building strategies, running historical simulations, generating reports, and moving toward autonomous Alpaca paper trading.

The project is intentionally split into small subsystems: data loading, strategy logic, indicators, backtesting, live/paper runtime, broker execution, risk controls, storage, and reporting. The goal is not to hide trading complexity behind one giant script. The goal is to make every piece explicit enough that it can be tested, replaced, and eventually trusted.

Current status: this is a working MVP and research scaffold with real Alpaca paper-trading proof. It can run sample/yfinance-style backtests, generate JSON/HTML reports, replay stream events, run guarded Alpaca paper sessions, and score supervised daemon activation artifacts. It is not yet ready for unattended real-money live trading. The production readiness path is tracked in `ROADMAP.md`.

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

Open the barebones desktop GUI:

```powershell
trading_env\Scripts\python.exe gui_app.py
```

On Windows, you can also double-click `Run TradingBot GUI.bat`. The GUI wraps the same CLI/runtime paths, shows command output in a console panel, embeds a matplotlib price/equity chart for backtests, and exposes paper-daemon start/status/kill-switch controls. The daemon card reads the local state artifact and labels the heartbeat as missing, fresh, or stale. The autonomy readiness card reads the latest paper-daemon soak rollup and window-capture plan, showing ready/blocked status, clean activation counts, active-window coverage, monitor/parity/flatten/stewardship status, next missing capture window, capture-window timing, market-session state, remaining blockers, and next action. `Run Next Capture` executes the first pending guarded capture command from that plan only when the target clock window is active and the shared market-session calendar does not classify the market as closed, and it still asks through the same paper-submit confirmation dialog. `Print Snapshot` writes a structured operator snapshot into the GUI console so daemon, readiness, capture, dashboard, and research state can be reviewed together. `Print Readiness` writes the higher-level autonomous-readiness verdict, separating operator-managed paper readiness from unattended paper readiness and listing the current blockers/next steps. The dashboard card summarizes monitor status, paper positions, open orders, latest fills, PnL attribution, and drawdown from local artifacts when they exist. GUI presets can apply safe sample dry-run, Alpaca data-only, micro paper, and full paper rehearsal defaults, and the validation panel can run validation profiles or the release checklist.

For a direct paper-daemon launcher, double-click `Run Paper Daemon.bat`. It checks the local kill switch before starting and uses the guarded `micro-notional` Alpaca paper profile.

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

Run repeated guarded paper-session dry runs as a local soak:

```powershell
trading_env\Scripts\python.exe main.py paper-soak --provider sample --strategy buyHold --soak-sessions 3 --store-dir runs\paper-soak-sample
```

Run the scheduled autonomous paper-session wrapper, which only runs the active operator window and writes schedule evidence:

```powershell
trading_env\Scripts\python.exe main.py paper-session-schedule --provider sample --strategy buyHold --store-dir runs\paper-session-schedule --paper-session-schedule-output reports\paper-session-schedule.json
```
Default pre-market and end-of-day windows are audit-only. Market-open, intraday, and market-close windows may forward explicit `--submit-orders` intent into the normal paper-session submission guard.
`validate-profile --validation-profile paper-dry-run` consumes `--paper-session-schedule-output` when that artifact exists, so a closed-window or failed scheduled-session report is treated as failed evidence rather than being papered over by fixture data.

Run the always-on paper daemon. This repeatedly checks the active paper-session window, writes heartbeat/state files, and only forwards broker submission intent when both `--submit-orders` and the scheduled-session guard allow it:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon --provider alpaca --execution-mode paper --symbol SPY --paper-profile micro-notional --submit-orders
```

Add cleanup review when you want each daemon iteration to preview current paper positions and planned flattening orders. Add monitor evidence when you also want expected-vs-observed position drift and stale open-order checks in the daemon report. Add data-parity evidence when websocket-vs-REST bar checks should be attached to each loop. Cleanup is preview-only unless `--paper-daemon-cleanup-submit` is also supplied:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon --provider alpaca --execution-mode paper --symbol SPY --paper-profile micro-notional --paper-daemon-cleanup-each-iteration --paper-daemon-monitor-each-iteration --paper-daemon-data-parity-each-iteration
```

Use a daemon profile when you want the soak shape chosen for you. `sample-data` is an offline bounded loop, `alpaca-data-only` validates Alpaca data without submit intent, `micro-notional` enables tiny paper-submit intent plus cleanup/monitor/parity evidence, and `full-paper-rehearsal` is the larger guarded rehearsal profile:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon --provider sample --strategy buyHold --paper-daemon-profile sample-data
trading_env\Scripts\python.exe main.py paper-daemon --provider alpaca --execution-mode dry-run --symbol SPY --paper-daemon-profile alpaca-data-only
trading_env\Scripts\python.exe main.py paper-daemon --provider alpaca --execution-mode paper --symbol SPY --paper-daemon-profile micro-notional
```

Stop it cleanly from another terminal before shutting down the computer:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon-stop
```

Check daemon state or clear the stop file when you want to resume:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon-status
trading_env\Scripts\python.exe main.py paper-daemon-clear-stop
```

For local smoke tests, bound the loop so it exits quickly:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon --provider sample --strategy buyHold --paper-daemon-max-iterations 1 --paper-daemon-interval-seconds 0
```

Summarize or audit daemon evidence after a run:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type recovery
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type daily-summary --paper-daemon-report-input reports\paper-daemon-report.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type notifications
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type retention
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type notional --paper-daemon-current-notional 25
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type restart-drill --paper-daemon-restart-drills-input reports\paper-daemon-restart-drills.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type exposure-ack-template --paper-daemon-cleanup-input reports\paper-cleanup-report.json --paper-daemon-ops-output reports\paper-exposure-acknowledgement-template.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type activation-checklist --paper-daemon-report-input reports\paper-daemon-report.json --paper-daemon-daily-summary-input reports\paper-daemon-daily-summary.json --paper-command-center-input reports\paper-command-center.json --paper-daemon-kill-proof-input reports\paper-daemon-kill-proof-report.json --paper-daemon-cleanup-input reports\paper-cleanup-report.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type activation-checklist --paper-daemon-report-input reports\paper-daemon-report.json --paper-daemon-daily-summary-input reports\paper-daemon-daily-summary.json --paper-command-center-input reports\paper-command-center.json --paper-daemon-kill-proof-input reports\paper-daemon-kill-proof-report.json --paper-daemon-cleanup-input reports\paper-cleanup-report.json --paper-daemon-acknowledged-exposure-input reports\paper-exposure-acknowledgement.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type supervised-soak --paper-daemon-activation-inputs reports\paper-daemon-alpaca-active-proof-activation-checklist.json --paper-daemon-soak-required-clean-activations 3 --paper-daemon-soak-required-active-windows 2 --paper-daemon-ops-output reports\paper-daemon-supervised-soak.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type position-stewardship --paper-daemon-position-monitor-input reports\paper-monitor-report.json --paper-daemon-ops-output reports\paper-position-stewardship.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type flatten-drill --paper-daemon-flatten-pre-monitor-input reports\paper-monitor-pre-flatten.json --paper-daemon-flatten-plan-input reports\paper-controlled-flatten.json --paper-daemon-flatten-cleanup-input reports\paper-cleanup-submit.json --paper-daemon-flatten-post-monitor-input reports\paper-monitor-post-flatten.json --paper-daemon-flatten-stewardship-input reports\paper-position-stewardship.json --paper-daemon-ops-output reports\paper-daemon-flatten-drill.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type soak-rollup --paper-daemon-activation-checklist-input reports\paper-daemon-activation-checklist.json --paper-daemon-supervised-soak-input reports\paper-daemon-supervised-soak.json --paper-command-center-input reports\paper-command-center.json --paper-daemon-position-monitor-input reports\paper-monitor-report.json --paper-daemon-position-cleanup-input reports\paper-cleanup-submit.json --paper-daemon-data-parity-input reports\paper-daemon-data-parity.json --paper-daemon-notional-input reports\paper-daemon-notional.json --paper-daemon-stewardship-input reports\paper-position-stewardship.json --paper-daemon-flatten-drill-input reports\paper-daemon-flatten-drill.json --paper-daemon-ops-output reports\paper-daemon-soak-rollup.json
trading_env\Scripts\python.exe main.py paper-daemon-ops --paper-daemon-ops-type window-capture-plan --paper-daemon-supervised-soak-input reports\paper-daemon-supervised-soak.json --paper-daemon-window-capture-windows market_open,intraday,market_close --paper-daemon-ops-output reports\paper-daemon-window-capture-plan.json
```

`exposure-ack-template` writes `acknowledged: false` on purpose. It is a review template, not approval evidence.
`--paper-daemon-acknowledged-exposure-input` is intentionally explicit. Use it only for an operator-approved JSON artifact with `acknowledged: true`, bounded `max_positions` and `max_notional`, and preferably an `expires_at` timestamp. Without that file, unexpected paper positions remain blockers.

Show the paper command-center summary from local artifacts:

```powershell
trading_env\Scripts\python.exe main.py paper-command-center --provider alpaca --symbol SPY --strategy buyHold --paper-daemon-profile micro-notional
```

Run a portfolio-level paper-session dry run across several symbols:

```powershell
trading_env\Scripts\python.exe main.py paper-portfolio --provider sample --symbols SPY,QQQ,IWM --strategy buyHold --store-dir runs\paper-portfolio-sample
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
Add `--recover-state` when you want the session to load the SQLite broker state store, reconcile prior orders/reports, and block new paper submission if unresolved state remains.

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

When `--submit-orders` is set, `paper-session` evaluates a broker-routing submission guard before any order is sent. The guard checks market-session policy, generated order presence, the shared paper-proof approval policy, symbol allowlists, max daily proof submissions, kill-switch state, and repeated-reject lockouts. Every run writes `submission-guard.json` plus the final `paper-session-result.json` into the session audit trail; outside an allowed session it records `market_session_not_tradable`, leaves `submitted=false`, and keeps the planned orders as reviewable evidence.

For the smallest broker-facing proof, use `paper-broker-proof`. It validates Alpaca paper credentials, the paper endpoint, execution mode, market-session permission, and a tiny notional cap before submitting anything. If the market is closed, it writes a no-submit artifact and does not touch the broker:

```powershell
trading_env\Scripts\python.exe main.py paper-broker-proof --provider alpaca --execution-mode paper --symbol SPY --paper-proof-limit-price 1 --paper-proof-max-notional 25 --submit-orders --paper-proof-output reports\alpaca-paper-broker-proof.json
```
Broker proof artifacts redact sensitive raw broker identifiers while preserving normalized fields needed by lifecycle, parity, cleanup, and fill-polling evidence checks.

To score an existing broker proof without submitting another paper order, use consume-existing validation:

```powershell
trading_env\Scripts\python.exe main.py validate-profile --validation-profile paper-submit --consume-existing-evidence --paper-proof-output reports\alpaca-paper-broker-proof.json --validation-profile-output reports\evidence\paper-submit-existing-evidence.json
```

Use `paper-broker-schedule` when you want the bot to decide whether the current operator window is allowed for a broker proof. It writes a schedule artifact plus a child proof artifact. On closed-market days it records `outside_window` / no-submit evidence:

```powershell
trading_env\Scripts\python.exe main.py paper-broker-schedule --provider alpaca --execution-mode paper --symbol SPY --paper-proof-limit-price 1 --paper-proof-max-notional 25 --submit-orders --paper-proof-schedule-output reports\alpaca-paper-broker-proof-schedule.json
```

To score an existing broker proof into scheduled evidence without placing another paper order:

```powershell
trading_env\Scripts\python.exe main.py paper-broker-schedule --paper-proof-existing-artifact reports\alpaca-paper-broker-proof.json --paper-proof-schedule-output reports\alpaca-paper-broker-proof-schedule.json
```

Summarize the latest activation artifacts for review. If `--paper-cleanup-output` exists, the activation report includes cleanup status, blocked cleanup reasons, remaining positions, and the next recommended cleanup step:

```powershell
trading_env\Scripts\python.exe main.py paper-activation-report --paper-proof-output reports\alpaca-paper-broker-proof.json --paper-proof-schedule-output reports\alpaca-paper-broker-proof-schedule.json --paper-submit-evidence reports\evidence\paper-submit-activation-check.json --paper-activation-output reports\paper-activation-report.json
```

Preview paper-account cleanup before retrying promoted portfolio submits:

```powershell
trading_env\Scripts\python.exe main.py paper-cleanup --provider alpaca --execution-mode paper --paper-cleanup-output reports\paper-cleanup-preview.json
```

Submit cleanup orders only during an allowed session and only after the shared paper-session guard passes:

```powershell
trading_env\Scripts\python.exe main.py paper-cleanup --provider alpaca --execution-mode paper --submit-orders --paper-cleanup-symbols SPY --paper-proof-symbol-allowlist SPY --fill-poll-attempts 3 --fill-poll-interval-seconds 1 --paper-cleanup-output reports\paper-cleanup-submit.json
```

## CLI Modes

`main.py` is the current application entry point.

`gui_app.py` is the desktop operator entry point. It is intentionally a wrapper around the existing command and application layers, not a second trading engine. Use it for backtests, basic chart review, paper-session commands, and paper-daemon controls when you want a click-driven workflow.

```powershell
trading_env\Scripts\python.exe main.py [mode] [options]
```

Available modes:

- `backtest`: load historical data, create a strategy, run the backtesting engine, print a summary, and optionally write JSON artifacts.
- `stream`: create a market data stream and feed events through the runtime engine without treating the run as broker paper trading.
- `paper`: use the same runtime path as streaming, labeled as the paper-trading workflow. This is the path that will keep gaining broker synchronization and safety controls.
- `paper-session`: run one guarded committee-to-execution paper session from config, write the full audit trail, and optionally submit paper orders with `--submit-orders`.
- `paper-session-schedule`: run the active scheduled autonomous paper-session window, suppress broker routing in no-submit windows, and write schedule evidence.
- `paper-broker-proof`: run the smallest guarded Alpaca paper broker proof, writing config/session/notional checks and optional submit/cancel evidence to one JSON artifact.
- `paper-broker-schedule`: run the broker proof only through the active scheduled proof window, writing both the schedule result and a child proof artifact.
- `paper-cleanup`: inspect Alpaca paper positions, plan flattening orders, and optionally submit only after the normal paper-session guard passes.
- `paper-monitor`: compare expected submitted paper positions against current broker positions and notional budget without placing orders.
- `paper-pilot`: run cleanup, no-resubmit paper-submit validation, activation reporting, and an optional promoted portfolio preview into one operator decision artifact.
- `paper-daemon`: continuously check scheduled paper-session windows, write heartbeat/state artifacts, and run guarded paper sessions until stopped by the kill switch or timeout.
- `paper-daemon-stop`: write the local daemon kill-switch file.
- `paper-daemon-clear-stop`: remove the local daemon kill-switch file so the next daemon launch can run.
- `paper-daemon-status`: print the latest daemon state plus current kill-switch status.
- `paper-daemon-ops`: write daemon recovery, summary, notification, retention, notional, restart-drill, activation, supervised-soak, stewardship, and flatten-drill evidence from paper artifacts.
- `paper-command-center`: write and print a compact operator summary of daemon state, kill switch, active config, paper monitor, data parity, PnL, drawdown, fills, warnings, and latest artifacts.
- `paper-activation-report`: summarize direct proof, scheduled proof, paper-submit validation evidence, blocked reasons, next windows, and recommendations for operator review.
- `paper-soak`: run repeated guarded paper sessions and aggregate readiness, warning, artifact, reconciliation, and scorecard checks into one JSON soak report.
- `paper-portfolio`: run guarded paper-session candidates across a symbol universe, allocate capital, and write one consolidated portfolio order report.
- `report`: run a backtest and write an HTML report.
- `optimize`: run a parameter grid search and write ranked JSONL optimization artifacts.
- `bulk`: run many symbols across one or more strategies and write JSONL plus a summary report.
- `matrix`: run a cross-asset research matrix, where each group can define its own provider, symbols, intervals, and historical windows.
- `replicate`: run published-strategy replication suites and compare local results against reference stats.
- `validate`: write the validation manifest, readiness index, CLI smoke plan, performance budgets, operator readiness HTML page, and current not-live-ready status without running expensive broker or soak checks.
- `validate-profile`: execute a named validation profile and write normalized evidence that `validate` and `release-checklist` can consume later.
- `profile`: run lightweight critical-path benchmarks, evaluate them against performance budgets, and write a profiling report.
- `release-checklist`: write the current release validation bundle plus a release-candidate bundle with checklist steps, paper-profile evidence, readiness status, operator readiness HTML, rehearsal status, and remaining gates.
- `release-rehearsal`: run release and paper-dry-run validation profiles, then build the release validation bundle, readiness page, release-candidate bundle, and rehearsal summary in one pass.

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
- `--submit-orders`: for `paper-session` and `paper-broker-proof` modes, submit generated/tiny proof orders only after the relevant guards pass. Requires `--execution-mode paper` for Alpaca broker routing.
- `--paper-session-schedule-output`: JSON artifact path for `paper-session-schedule`.
- `--paper-proof-output`: JSON artifact path for `paper-broker-proof`.
- `--paper-proof-schedule-output`: JSON artifact path for `paper-broker-schedule`.
- `--paper-proof-existing-artifact`: existing broker-proof artifact to score with `paper-broker-schedule` without contacting a broker.
- `--paper-proof-artifact-root`: directory for child proof artifacts created by `paper-broker-schedule`.
- `--paper-submit-evidence`: validation evidence bundle consumed by `paper-activation-report`.
- `--paper-activation-output`: JSON operator report path for `paper-activation-report`.
- `--paper-cleanup-output`: JSON artifact path for `paper-cleanup`.
- `--paper-cleanup-symbols`: optional comma-separated cleanup/flatten symbol filter. Defaults to every broker position.
- `--paper-monitor-output`: JSON artifact path for `paper-monitor`.
- `--paper-monitor-portfolio-input`: portfolio paper-session artifact whose submitted orders define expected positions.
- `--paper-monitor-position-input`: optional existing position-preview artifact; when omitted, `paper-monitor` runs a fresh no-submit broker position preview.
- `--paper-monitor-cleanup-input`: optional filled cleanup artifact whose submitted close orders mark expected paper positions as closed.
- `--paper-monitor-max-notional`: optional max observed position notional for monitor validation.
- `--paper-daemon-interval-seconds`: seconds between daemon schedule checks, default `300`.
- `--paper-daemon-max-iterations`: optional bounded run count for smoke tests.
- `--paper-daemon-kill-switch`: stop-file path, default `runs\paper-daemon.kill`.
- `--paper-daemon-state-output`: daemon state artifact path, default `runs\paper-daemon-state.json`.
- `--paper-daemon-heartbeat-output`: daemon heartbeat artifact path, default `runs\paper-daemon-heartbeat.json`.
- `--paper-daemon-artifact-root`: daemon child artifact directory, default `runs\paper-daemon`.
- `--paper-daemon-report-output`: full daemon run report path, default `reports\paper-daemon-report.json`.
- `--paper-daemon-cleanup-each-iteration`: run a no-submit cleanup/flatten review after each daemon schedule check.
- `--paper-daemon-cleanup-submit`: allow daemon cleanup reviews to submit flatten orders after explicit guards pass.
- `--paper-daemon-monitor-each-iteration`: attach expected-position, observed-position, and stale-open-order monitor evidence to each daemon iteration.
- `--paper-daemon-monitor-open-order-timeout-minutes`: unresolved paper-order age limit for daemon monitor evidence, default `15`.
- `--paper-daemon-data-parity-each-iteration`: attach websocket-vs-REST bar parity evidence to every daemon iteration.
- `--paper-daemon-data-parity-max-close-drift-bps`: maximum streamed-vs-REST close drift before daemon data parity fails, default `5`.
- `--paper-daemon-profile`: apply bounded daemon soak defaults for `sample-data`, `alpaca-data-only`, `micro-notional`, or `full-paper-rehearsal`; explicit enabling flags can still add checks.
- `--paper-daemon-ops-type`: daemon ops artifact type: `recovery`, `daily-summary`, `notifications`, `retention`, `notional`, `restart-drill`, `activation-checklist`, `exposure-ack-template`, `supervised-soak`, `position-stewardship`, `flatten-drill`, `soak-rollup`, or `window-capture-plan`.
- `--paper-daemon-activation-inputs`: comma-separated activation-checklist artifacts consumed by `paper-daemon-ops --paper-daemon-ops-type supervised-soak`.
- `--paper-daemon-soak-required-clean-activations`: clean activation-checklist count required before supervised daemon soak passes, default `3`.
- `--paper-daemon-soak-required-active-windows`: distinct active windows required before supervised daemon soak passes, default `2`.
- `--paper-daemon-soak-max-observed-notional`: optional total observed-notional cap across supervised daemon soak activation artifacts.
- `--paper-daemon-position-monitor-input`: paper monitor artifact consumed by `position-stewardship`; defaults to `--paper-monitor-output` when that file exists.
- `--paper-daemon-position-cleanup-input`: optional cleanup artifact whose filled close orders prove stale positions were closed.
- `--paper-daemon-position-max-age-hours`: maximum active paper-position age before stewardship requires closure evidence, default `72`.
- `--paper-daemon-flatten-pre-monitor-input`: pre-flatten paper monitor artifact consumed by `flatten-drill`.
- `--paper-daemon-flatten-plan-input`: controlled flatten plan artifact consumed by `flatten-drill`.
- `--paper-daemon-flatten-cleanup-input`: submitted cleanup artifact consumed by `flatten-drill`; must show submitted, filled close orders and clean reconciliation.
- `--paper-daemon-flatten-post-monitor-input`: post-flatten paper monitor artifact consumed by `flatten-drill`; must show no observed exposure and record closed symbols.
- `--paper-daemon-flatten-stewardship-input`: optional position-stewardship artifact consumed by `flatten-drill`.
- `--paper-daemon-activation-checklist-input`: activation-checklist artifact consumed by `soak-rollup`.
- `--paper-daemon-supervised-soak-input`: supervised-soak artifact consumed by `soak-rollup`.
- `--paper-daemon-stewardship-input`: position-stewardship artifact consumed by `soak-rollup`.
- `--paper-daemon-flatten-drill-input`: flatten-drill artifact consumed by `soak-rollup`.
- `--paper-daemon-data-parity-input`: data-parity artifact consumed by `soak-rollup`.
- `--paper-daemon-notional-input`: notional decision artifact consumed by `soak-rollup`.
- `--paper-daemon-window-capture-windows`: comma-separated submit-capable windows targeted by `window-capture-plan`, default `market_open,intraday,market_close`.
- `--paper-daemon-window-capture-max-iterations`: bounded daemon iteration count suggested in `window-capture-plan` commands, default `1`.
- `--paper-command-center-output`: JSON artifact path for `paper-command-center`, default `reports\paper-command-center.json`.
- `--paper-command-center-stale-seconds`: heartbeat age after which command-center marks the daemon stale, default `900`.
- `--paper-daemon-restart-drills-input`: JSON restart-drill evidence for clean stop/resume, stale-lock replacement, kill-switch resume, and duplicate client-order-id checks.
- `--paper-daemon-current-notional`: current paper capital tier used by daemon notional recommendations, default `25`.
- `--paper-daemon-required-clean-iterations`: clean submitted daemon iterations required before escalation is recommended, default `10`.
- `--paper-position-journal`: optional JSONL path where `paper-monitor` appends paper-position lifecycle observations.
- `--paper-open-orders-input`: optional existing open-order artifact for stale-order scoring without contacting a broker.
- `--paper-open-orders-output`: optional JSON artifact path where `paper-monitor` records broker open-order status and stale-order gating.
- `--paper-open-order-timeout-minutes`: unresolved paper-order age limit before the monitor marks the order stale, default `15`.
- `--paper-stale-order-cancel-output`: optional JSON artifact path where `paper-monitor` records stale-order cancel planning or acknowledgement.
- `--paper-cancel-stale-orders`: explicitly cancel stale paper open orders found by `paper-monitor`; omitted by default, so monitor runs only plan cancellation.
- `--paper-exit-preview-output`: optional JSON artifact path where `paper-monitor` writes dry-run flatten orders for cleanup debt or requested active exits.
- `--paper-exit-preview-active`: include active expected pilot positions in the exit preview instead of previewing only stale/orphan cleanup debt.
- `--paper-controlled-flatten-output`: optional JSON artifact path for active-pilot flatten planning that stays separate from generic cleanup.
- `--paper-controlled-flatten-symbols`: optional comma-separated active pilot symbols for controlled flatten planning; defaults to all active pilot positions.
- `--paper-controlled-flatten-reason`: strategy-aware reason recorded on controlled flatten plans.
- `--paper-eod-closeout-output`: optional JSON artifact path for end-of-day flatten/reduce/hold closeout planning.
- `--paper-eod-overnight-policy`: default EOD overnight policy, `hold`, `flatten`, or `reduce`; default `hold`.
- `--paper-eod-reduce-fraction`: fraction of current quantity retained when EOD policy is `reduce`, default `0.5`.
- `--paper-pnl-attribution-output`: optional JSON artifact path for PnL attribution by strategy, symbol, signal family, regime, and execution session.
- `--paper-drawdown-output`: optional JSON artifact path for broker equity and mark-to-market drawdown tracking.
- `--paper-drawdown-peak-equity`: optional prior peak equity used by drawdown tracking.
- `--paper-market-snapshot-output`: optional JSON artifact path for latest trade/latest quote snapshots from `paper-monitor` or `paper-pilot`.
- `--paper-data-freshness-output`: optional JSON artifact path for quote/trade freshness scoring in `paper-monitor`.
- `--paper-quote-spread-output`: optional JSON artifact path for quote spread, effective spread, and fill-quality analysis in `paper-monitor`.
- `--paper-asset-metadata-output`: optional JSON artifact path for asset class, session calendar policy, and tradability metadata.
- `--paper-symbol-capability-output`: optional JSON artifact path for fractional, shortability, and marginability capability gates.
- `--paper-require-fractional` / `--paper-require-short` / `--paper-require-margin`: require those capabilities in symbol gate artifacts.
- `--paper-pilot-output`: JSON artifact path for the one-command pilot readiness report.
- `--paper-pilot-validation-output`: paper-submit validation evidence path generated inside `paper-pilot`.
- `--paper-pilot-skip-portfolio`: skip the promoted portfolio preview inside `paper-pilot`.
- `--paper-pilot-submit-portfolio`: allow `paper-pilot` to submit the promoted portfolio only after cleanup and broker evidence gates are already passing.
- `--paper-proof-quantity`: tiny quantity used by `paper-broker-proof`, default `1`.
- `--paper-proof-limit-price`: conservative limit price used by `paper-broker-proof`, default `1`.
- `--paper-proof-max-notional`: maximum planned notional allowed by `paper-broker-proof`, default `25`.
- `--paper-proof-side`: `BUY` or `SELL` side for `paper-broker-proof`, default `BUY`.
- `--paper-proof-client-order-id`: optional client order id for duplicate-protection proof runs.
- `--fill-poll-attempts`: broker execution-report polling attempts after proof submit/cancel or paper-session submission, default `1`.
- `--fill-poll-interval-seconds`: delay between broker execution-report polling attempts, default `0`.
- `--paper-proof-symbol-allowlist`: comma-separated symbols allowed for broker-proof submission.
- `--max-daily-proof-submissions`: maximum submitted broker-proof orders allowed per UTC date.
- `--paper-proof-kill-switch`: block broker-proof submission regardless of other guards.
- `--repeated-reject-lockout-threshold`: block broker-proof submission after repeated rejected proof orders for the symbol.
- `--paper-proof-prior-dir`: directory of prior broker-proof artifacts used by approval-policy limits.
- `--allow-pre-market` / `--allow-after-hours`: allow `paper-broker-proof` outside the regular session when the configured policy explicitly permits it.
- `--comparison-provider`: optional secondary provider for `paper-session` data drift checks.
- `--soak-sessions`: number of guarded sessions to run in `paper-soak` mode.
- `--paper-soak-output`: JSON artifact path for the `paper-soak` scoreboard, promotion gate, failure halt, checks, and sessions.
- `--paper-soak-min-clean-streak`: clean pass streak required before micro-notional paper can graduate to larger paper notional, default `10`.
- `--paper-soak-acknowledge-failure`: acknowledge a paper-soak failure halt for the selected operator action.
- `--paper-soak-operator-action`: operator response after a paper-soak failure halt: `retry`, `flatten`, or `disable`.
- `--paper-profile-preview`: apply a named paper profile's sizing and risk defaults while forcing no broker submission and skipping Alpaca provider/credential requirements. Use this for local profile previews with sample data.
- `--recover-state`: load and reconcile persisted broker-facing state before `paper-session` or `paper-soak` decisions.
- `--state-db-path`: override the SQLite broker state path used for recovery and paper-session persistence.
- `--timeout-seconds`: maximum runtime for a CLI command before a watchdog requests shutdown and then hard-exits with code `124` if cleanup stalls. Defaults are 180 seconds for backtest/report-style commands, 300 seconds for paper/runtime commands, and 900 seconds for optimization/research sweeps.
- `--param-grid`: JSON object of parameter lists for `optimize` mode.
- `--param-grid-file`: JSON file containing parameter lists for `optimize` mode. Useful on shells where inline JSON quoting is awkward.
- `--metric`: metric to optimize, default `total_return`.
- `--bulk-output`: JSON summary path for `bulk` mode.
- `--benchmark-strategy`: benchmark strategy for benchmark-relative bulk reports, default `buyHold`.
- `--benchmark-output`: optional JSON path for excess-return and strategy-selection research output from `bulk` mode.
- `--promotion-output`: optional JSON path for paper-session candidate manifests generated from benchmark-relative bulk winners.
- `--promotion-input`: optional benchmark promotion JSON whose enabled manifests seed `paper-portfolio` runs.
- `--research-matrix-file`: JSON matrix file for `matrix` mode, default `configs\research\cross_asset_matrix.json`.
- `--matrix-output`: JSON summary path for `matrix` mode.
- `--replication-file`: JSON published-strategy replication suite for `replicate` mode.
- `--replication-output`: output path for the published replication comparison report.
- `--validation-output`: output path for the validation/readiness bundle written by `validate` mode.
- `--evidence-dir`: directory or JSON file containing validation evidence for `validate` and `release-checklist`; missing default evidence is treated as no current evidence.
- `--readiness-html-output`: output path for the operator readiness HTML page written by `validate` and `release-checklist`.
- `--validation-profile`: profile name for `validate-profile`; available values are `smoke`, `fast`, `full`, `paper-dry-run`, `paper-submit`, `release`, and `live-gate`.
- `--validation-profile-output`: optional evidence bundle output path for `validate-profile`; defaults to the selected profile's configured output path.
- `--validation-run-id`: optional run id recorded in `validate-profile` evidence metadata.
- `--consume-existing-evidence`: for `validate-profile`, skip manifest commands and score only existing artifacts plus native evidence producers. Use this after a successful broker proof when you want validation evidence without submitting another order.
- `--profiling-output`: output path for the benchmark and performance-budget report written by `profile` mode.
- `--profiling-repeats`: measured repeats per benchmark task in `profile` mode.
- `--release-output`: output path for the release validation bundle written by `release-checklist` mode.
- `--release-candidate-output`: output path for the full release-candidate bundle written by `release-checklist` mode.
- `--rehearsal-evidence-dir`: evidence directory populated by `release-rehearsal`.
- `--rehearsal-output`: orchestration summary path written by `release-rehearsal`.

Run a 50-market Alpaca bulk sweep:

```powershell
trading_env\Scripts\python.exe main.py bulk --provider alpaca --symbols-file configs\universes\liquid_etf_80.json --max-symbols 50 --strategies meanReversion,volatilityBreakout,momentumRegime,trendPullback,volumeMomentum,squeezeExpansion --interval 1d --start 2023-01-01T00:00:00Z --end 2025-12-31T00:00:00Z --store-dir runs\bulk-alpaca-research-50 --bulk-output reports\bulk-alpaca-research-50.json
```

Run a benchmark-relative research sweep:

```powershell
trading_env\Scripts\python.exe main.py bulk --provider alpaca --symbols-file configs\universes\liquid_etf_80.json --max-symbols 50 --strategies buyHold,meanReversion,tuffContrarian,gapFade,choppinessRange,vwapValueReversion --benchmark-strategy buyHold --benchmark-output reports\benchmark-relative-research-50.json
```

Generate paper-session promotion candidates from the same benchmark-relative sweep:

```powershell
trading_env\Scripts\python.exe main.py bulk --provider alpaca --symbols-file configs\universes\liquid_etf_80.json --max-symbols 50 --strategies buyHold,meanReversion,tuffContrarian,gapFade,choppinessRange,vwapValueReversion --benchmark-strategy buyHold --benchmark-output reports\benchmark-relative-research-50.json --promotion-output reports\paper-rehearsal-candidates-50.json
```

The promotion output is deliberately conservative. It does not approve live trading; it converts strategies that beat the benchmark gates into `paper_manifest` entries for the next paper-session rehearsal step.

Run a guarded portfolio paper dry-run from those promotion candidates:

```powershell
trading_env\Scripts\python.exe main.py paper-portfolio --provider alpaca --promotion-input reports\paper-rehearsal-candidates-50.json --store-dir runs\paper-portfolio-promoted
```

Run the same candidates as a micro-notional preview before broker routing:

```powershell
trading_env\Scripts\python.exe main.py paper-portfolio --provider alpaca --promotion-input reports\paper-rehearsal-candidates-50.json --paper-profile micro-notional --paper-profile-preview --store-dir runs\paper-portfolio-promoted-micro-preview
```

Portfolio paper submission is intentionally post-allocation. Child symbol sessions only plan orders; the portfolio layer then allocates capital, scales consolidated orders to the aggregate notional cap, evaluates the paper-session submission guard, submits only accepted consolidated orders, polls broker execution reports when configured, reconciles the final lifecycle state, and redacts raw broker identifiers in the artifact.

Run the one-command paper pilot after broker proof and cleanup artifacts exist:

```powershell
trading_env\Scripts\python.exe main.py paper-pilot --provider alpaca --execution-mode paper --promotion-input reports\paper-rehearsal-candidates-50.json --paper-profile micro-notional --paper-cleanup-output reports\paper-cleanup-report.json --paper-pilot-output reports\paper-pilot-report.json
```

By default this is a readiness orchestration and portfolio preview. It consumes existing broker-proof evidence without resubmitting proof orders, includes cleanup evidence, writes an activation report, and explains blockers before broker routing. `--submit-orders` applies only to the cleanup step. Portfolio submission requires the separate `--paper-pilot-submit-portfolio` flag and still stays behind the normal paper-session submission guard plus passing cleanup and broker evidence.

After a promoted paper submit, monitor the resulting broker positions against the submitted portfolio artifact:

```powershell
trading_env\Scripts\python.exe main.py paper-monitor --provider alpaca --execution-mode paper --paper-monitor-portfolio-input runs\paper-pilot-promoted-submit\portfolio-session-report.json --paper-cleanup-output reports\paper-post-submit-position-preview.json --paper-monitor-output reports\paper-monitor-promoted-submit.json
```

This does not flatten anything. It treats broker-filled submitted portfolio orders as the expected paper exposure, then flags missing symbols, unexpected symbols, quantity mismatches, and notional-budget breaches. A small post-submit mark-to-market tolerance prevents penny-level market drift from failing an otherwise clean monitor. The monitor output embeds a paper-position lifecycle summary with owning strategy, source report, target notional, observed market value, average fill price, filled quantity, slippage, unrealized PnL, notional drift, default stop/exit policy, status (`fresh`, `active`, `stale`, `missing`, or `orphan`), forced-exit-needed flags, per-position scorecards, and an exposure registry that separates active expected exposure from cleanup debt. Add `--paper-position-journal reports\paper-position-journal.jsonl` to append each lifecycle observation to a durable JSONL journal.

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
- `BenchmarkPromotionReport`: converts selected benchmark-relative edges into Alpaca paper-session rehearsal manifests.
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
- `LockedAlpacaLiveBroker`: explicit live broker boundary that raises on every live operation until the live adapter milestone is intentionally implemented.
- `ExecutionReport`: normalized order/fill/reconciliation result.
- `mark_order()`: helper for order state transitions.
- Intent models for signal, target position, generated order, broker order, and fill.
- Replacement policies for stale market/limit order handling.
- Bracket/OCO/order-capability plans.
- End-of-day policies for hold, cancel-open-orders, flatten, and reduce behavior.
- `src.execution.safety.live`: live-safety evidence builders for separate live order boundaries, multi-factor live unlock checks, account allowlist fingerprints, hard live caps, kill-switch drill evidence, no-live-submit tests, secret scanning, redaction regression, audit-log integrity, read-only reporting mode, manual approvals, emergency procedures, compliance awareness, and CI-style "live still locked" proof.

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

Alpaca historical data requests translate `--period` into an explicit `start` query when `--start` is not provided, so paper-session regime and committee decisions receive a real lookback window rather than a single recent bar.

`src.validation` defines the productization evidence layer used by readiness and release reports. In addition to the broader broker, runtime, research, and performance checks, `PaperSoakTierReport`, `DailyOpsAcceptanceReport`, `ObservabilityAcceptanceReport`, and `SecurityConfigReport` capture the final paper-trading acceptance concerns: tiered soak evidence, operator-report completeness, metrics/health/notification visibility, halt reason visibility, `.env` safety, paper/live URL confusion, live-trading guards, and committed-secret markers. `DeploymentRehearsalReport`, `GoldenArtifactReport`, and `HardPreLiveUpgradeReport` cover the release tail: deployment profile rehearsal evidence, frozen expected-output comparisons, and artifact-backed proof for the remaining pre-live capabilities that are still simulated.

`ValidationEvidenceBundle`, `EvidenceFreshnessReport`, `ValidationActionPlan`, and `ReleaseDecisionReport` turn prior validation artifacts into an operator-facing decision flow. `validate` and `release-checklist` can read evidence from `--evidence-dir`, select the newest evidence per check, flag stale or missing proof, emit the next checks or commands needed before release/paper/live readiness can advance, and write the static readiness page with `--readiness-html-output`.

`ValidationRunMetadata` and `ValidationEvidenceHistory` add the evidence history layer: run IDs, code version, config hash, environment metadata, dependency versions, provider/broker mode, and artifact digests. `ValidationProfile` defines CI/operator profiles for fast, full, paper-dry-run, paper-submit, release, and live-gate evidence selection.

`execute_validation_check()`, `execute_validation_checks()`, `execute_validation_profile()`, and `write_validation_evidence_bundle()` are the first evidence-producing runner boundary. They execute manifest commands through an injectable runner, enforce timeouts, check expected artifacts, and convert the outcome into normalized `ValidationEvidence` bundles.

`validate-profile` exposes that runner boundary from the CLI. It selects one of the default profiles, executes the profile's manifest commands, writes a standard evidence bundle with run metadata, and leaves readiness scoring to the existing `validate` and `release-checklist` consumers. Checks that already have native evaluators, such as paper-profile validation, security configuration, paper-soak tier acceptance, paper-session schedule acceptance, daily-ops report acceptance, observability acceptance, and performance budgets, are produced in-process rather than being marked as skipped.

Use `--validation-profile smoke` when you want a lightweight parser/evidence smoke that avoids recursive full-suite execution. Use `fast` or `paper-dry-run` when you want real code-test and paper-workflow evidence.

The `paper-submit` and `live-gate` profiles also consume `--paper-cleanup-output` as `paper_account_cleanup` evidence. A cleanup artifact passes when the broker account is already flat, or when guarded flatten orders were submitted and reconciled cleanly. If the artifact still shows positions and submission was blocked, the profile carries that blocked reason forward instead of hiding leftover paper exposure behind a passing CLI exit code.

The `release` profile now also emits native fixture-backed evidence for release/productization gates that do not require broker credentials: failure injection, data-quality torture, backtester differential checks, optimizer validation, deployment rehearsal, golden artifacts, and release-checklist generation.

The final release-candidate rehearsal consumes schedule evidence separately from release readiness. A release-profile bundle can make the release decision ready; a paper-dry-run bundle supplies `paper_session_schedule` evidence. When both are present in `--evidence-dir`, `release-checklist` can mark the autonomous paper rehearsal passed while live readiness remains locked.

`release-rehearsal` automates that handoff. It writes `release-validation.json` and `paper-dry-run-validation.json` into `--rehearsal-evidence-dir`, runs `release-checklist` against that directory, and writes a compact summary to `--rehearsal-output`.

Release bundles also include `live_unlock_blockers`. This section is intentionally conservative: even when release readiness and the paper rehearsal pass, live unlock remains blocked until every hard pre-live gate has real artifact-backed evidence, including broker statement ingestion, real Alpaca fill polling, market-session enforcement, paper-account parity, borrow/margin realism, and live-execution separation.

Golden artifact maintenance is represented by `GoldenArtifactFixture` and `GoldenArtifactApprovalRequest`, so expected outputs can be regenerated with explicit review metadata and mismatch evidence instead of silent manual edits.

Paper-session scheduling is represented by `PaperSessionScheduleWindow`, `ScheduledPaperSessionRecord`, and `PaperSessionScheduleReport`. These define pre-market, market-open, intraday, close, and end-of-day evidence windows, including windows where broker submission must remain blocked.

Broker proof now includes `BrokerStatementIngestionReport` for statement/account/position parity and `AlpacaFillPollingReport` for real fill polling evidence through an injectable broker boundary. These reports are still evidence scaffolds until wired to live Alpaca statement/fill endpoints.

Market-session and deployment proof are represented by `MarketSessionEnforcementReport` and `DeploymentRunEvidenceReport`. The first proves order generation/submission obeyed session permissions; the second records process exit, graceful stop, watchdog, log rotation, artifact persistence, state-db persistence, and restart recovery evidence for Windows, Docker, and server profiles.

Operator-facing readiness can be rendered with `render_readiness_html()` or written with `write_readiness_html_page()`. The page summarizes readiness score, release/live status, stale evidence, next actions, and required-check status from a validation bundle. The `validate` and `release-checklist` CLI modes now write this page directly.

The final paper rehearsal bundle is represented by `AutonomousPaperTradingRehearsalReport`, which checks that evidence exists, scheduled paper sessions passed, release readiness is unblocked, and an operator readiness page was produced. `release-checklist` writes this conservative rehearsal status into both the release validation bundle and the `--release-candidate-output` artifact; missing scheduled paper-session proof keeps the candidate blocked rather than pretending the bot is ready.

`src/deployment` contains local Windows task, Docker, small-server profile scaffolds, GUI executable packaging plans, and automation evidence builders for daily operator cycles, scheduled jobs, service entrypoints, supervision, leases, and idempotency. `docs/PAPER_TRADING_SOAK_CHECKLIST.md` defines the final paper-trading soak gates.

`src/operations` contains the paper-session control layer:

- `run_autonomous_paper_session()`: one guarded symbol-level paper-session plan and audit trail, including a submission guard for broker routing when `--submit-orders` is requested.
- `run_scheduled_paper_session()`: active-window autonomous paper-session scheduler that writes schedule evidence, skips outside-window runs, and suppresses submit intent for no-submit windows.
- `run_paper_broker_proof()`: broker-facing micro-order proof that validates paper config, session calendar, notional caps, account snapshot, submit acknowledgement, cancel acknowledgement, local execution reports, broker-polled execution reports, and cleanup.
- `run_scheduled_paper_broker_proof()`: scheduled broker-proof wrapper that selects the active operator window, blocks closed-market runs, and writes schedule plus child proof artifacts.
- `run_paper_cleanup()`: broker-position cleanup/flatten preview or guarded paper submit with fill polling, reconciliation, and redacted artifacts.
- `build_paper_monitor_report()`: post-submit monitor that compares expected paper positions from submitted portfolio orders against observed broker positions and embeds lifecycle/ownership status.
- `build_paper_position_lifecycle_report()`: paper-position lifecycle layer for ownership metadata, age status, forced-exit-needed flags, exposure registry summaries, and journal-ready observations.
- `build_paper_open_order_report()`: stale open-order monitor that scores unresolved submitted paper orders against a timeout and blocks new-entry readiness once an order is stale.
- `run_paper_stale_order_cancel()`: stale open-order cancel policy layer with preview-only default artifacts, explicit cancel acknowledgement scoring, and redacted operator output.
- `build_execution_template_report()`: maps strategy families to broker-agnostic execution templates such as limit-with-timeout, bracket, trailing-stop, and close-only.
- `build_bracket_order_plan()`: builds entry, stop-loss, and take-profit leg previews for future bracket/OCO broker routing.
- `build_replace_order_report()`: evaluates stale limit orders and produces cancel-replace planning using quote-aware replacement prices.
- `build_partial_fill_reconciliation_report()`: records filled, partial, unfilled, and overfilled states with remaining quantity and average fill evidence.
- `build_client_order_id_replay_report()`: prevents duplicate submissions by replaying intended client order IDs against prior submissions.
- `build_pre_submit_order_preview()`: summarizes final side, quantity, order type, estimated notional, price source, and risk/approval gate status before broker submission.
- `build_order_count_gate_report()`: enforces max order count per session and max order count per symbol before portfolio routing.
- `build_turnover_gate_report()`: compares broker/account equity against daily and strategy-attributed turnover before new routing is allowed.
- `build_realized_slippage_halt_report()`: turns repeated fill slippage breaches into an explicit strategy halt signal.
- `build_rejected_order_cooldown_report()`: groups rejected orders by symbol and strategy and emits cooldown windows after repeated failures.
- `build_liquidity_participation_report()`: checks recent average volume, spread, estimated notional, and order participation before execution.
- `build_broker_rounding_report()`: applies asset-class quantity precision, fractional/whole-share rules, and minimum-notional checks before broker submission.
- `build_stop_exit_visibility_report()`: verifies active paper positions have visible stop and exit orders in the monitor layer.
- `build_quote_depth_report()`: scores bid/ask depth notional and spread for future quote-depth and market-impact checks.
- `build_paper_exit_preview()`: dry-run exit planner that produces flatten orders for stale/orphan cleanup debt, with an explicit option to preview active pilot exits too.
- `build_paper_controlled_flatten_plan()`: strategy-aware active-pilot flatten planner that selects owned promoted positions, blocks non-active/orphan symbols, and requires a follow-up monitor confirmation after submission is added.
- `build_paper_eod_closeout_report()`: end-of-day closeout planner that can hold, flatten, or reduce positions from strategy overnight policy and current lifecycle state.
- `build_paper_pnl_attribution_report()`: position-level attribution by strategy, symbol, signal family, regime, and execution session with mark-to-market PnL, drift, exposure, and slippage summaries.
- `build_paper_drawdown_report()`: broker-equity plus mark-to-market drawdown tracker for paper pilots and future soak scoreboards.
- `build_live_market_snapshot_report()`: latest trade/latest quote snapshot layer with midpoint, spread, and spread-bps calculations.
- `build_quote_spread_report()`: pre-submit/post-fill spread and effective-spread analysis for execution quality checks.
- `build_data_freshness_report()`: asset-class-aware freshness gates for bars, quotes, trades, and cached data.
- `arbitrate_data_source()`: provider selection scaffold that chooses Alpaca, yfinance, cache, or another source from freshness, schema, availability, and drift evidence.
- `build_asset_class_metadata_report()`: asset-class and calendar-policy metadata for stocks, ETFs, bonds, funds, crypto, and future universes.
- `build_symbol_capability_report()`: tradability, fractional, shortability/easy-to-borrow, marginability, and maintenance-margin capability gates before order generation.
- `build_multi_timeframe_data_report()`: verifies each symbol has the intraday and higher-timeframe context a strategy requires before it is allowed into a paper decision.
- `build_corporate_action_replay_report()`: checks split/dividend replay assumptions, adjusted price/quantity math, and paper-vs-backtest quantity consistency.
- `build_market_calendar_regression_report()`: validates holiday, early-close, and session/tradability expectations against the market calendar boundary used by paper scheduling.
- `simulate_data_outage()`: models historical-data-available/live-quote-unavailable failures and verifies submission blocks or explicitly downgraded cached-data behavior.
- `build_websocket_rest_parity_report()`: compares streamed bars against REST bars after close so websocket ingestion can be audited against a second retrieval path.
- `build_data_latency_histogram_report()`: groups websocket, REST, strategy, order, and fill-polling latencies into bucketed p50/p95/max evidence for lag detection.
- `build_paper_pilot_report()`: operator-facing pilot decision that combines cleanup, paper-submit evidence, activation status, and portfolio preview into blockers and next actions.
- `PaperBrokerProofApprovalPolicy`: order-intent approval policy for broker-proof submissions, covering symbol allowlists, max daily submissions, kill switch, repeated-reject lockouts, and cleanup requirements.
- `PaperSessionSubmissionGuardReport`: autonomous paper-session broker-routing evidence for submit intent, market-session permission, generated orders, and approval-policy limits.
- `run_paper_session_soak()`: repeated guarded sessions with readiness, warning, artifact, reconciliation, scorecard checks, scoreboard metrics, promotion-gate status, and failure-halt state.
- `build_paper_soak_scoreboard()`: paper-soak scoreboard that tracks pass/fail streaks, failure reasons, runtime, exposure, PnL placeholder values, fill quality, drift reports, and monitor status across sessions.
- `evaluate_paper_soak_promotion_gate()`: clean-streak gate that blocks graduation from micro-notional paper until the required pass streak is present.
- `evaluate_paper_soak_failure_halt()`: failure lockout model that requires operator acknowledgement plus a concrete retry/flatten/disable decision after a soak failure.
- `run_portfolio_paper_session()`: multi-symbol candidate sessions with capital-ledger allocation and one consolidated order report.
- `load_paper_session_manifests()`: loads promotion JSON or raw paper manifests into the portfolio paper-session runner.
- `PortfolioSubmissionReport`: records post-allocation portfolio broker routing, aggregate notional budget, submission guard, fill polling, reconciliation, and redacted execution reports.
- `build_portfolio_exposure_report()`: unifies broker positions, expected positions, open orders, strategy targets, cash, buying power, and equity into one paper exposure view.
- `build_beta_vol_adjusted_exposure_report()`: applies beta and volatility risk lenses to current portfolio notional before sizing decisions.
- `build_correlation_cluster_cap_report()`: groups highly correlated symbols and checks cluster exposure caps from current correlation evidence.
- `build_portfolio_exposure_cap_report()`: enforces symbol, sector, asset-class, strategy, total gross, and total net exposure caps.
- `build_strategy_capital_budget_report()`: allows per-strategy capital increases only when paper scorecards pass and the operator approves.
- `build_capital_decay_report()`: reduces per-strategy capital after underperformance, execution errors, failed paper scorecards, or stale research evidence.
- `build_loss_limit_report()`: aggregates daily and weekly realized, unrealized, and strategy-attributed PnL into loss-limit gates.
- `build_drawdown_lockout_report()`: persists max-drawdown lockouts across restarts until a manual reset is allowed.
- `build_volatility_shock_report()`: estimates directional long/short losses from symbol-level shock assumptions before promoted submits.
- `build_gap_through_stop_stress_report()`: models overnight gap-through-stop losses and blocks exposure when the gap budget is exceeded.
- `build_margin_pressure_report()`: estimates maintenance-margin pressure and concentration against broker equity/buying-power inputs.
- `build_cash_reserve_report()`: projects cash after pending entries and exits to enforce operator-defined reserves.
- `build_dynamic_position_scaling_report()`: scales target notionals by confidence, paper scorecard quality, regime fit, and volatility.
- `build_portfolio_rebalance_report()`: decides whether existing paper positions should hold, increase, or reduce toward strategy targets.
- `build_symbol_conflict_report()`: detects opposing same-symbol strategy intents and either nets or blocks them by policy.
- `build_strategy_stop_trading_report()`: stops individual strategies after drawdown, data drift, high slippage, repeated rejects, missing fills, or regime mismatch.
- `build_portfolio_kill_switch_report()`: records portfolio kill-switch state, open-order cancellation intent, generated flatten orders, and disabled-new-order status.
- `build_account_risk_percentage_report()`: checks session, daily, strategy, and portfolio risk values against operator-defined percentages of account equity.
- `build_risk_dashboard_summary_report()`: converts risk reports into dashboard-ready cards with pass/fail, severity, reason, and headline values.
- `build_var_cvar_exposure_report()`: estimates per-symbol and portfolio VaR/CVaR from historical return scenarios and current exposure.
- `build_strategy_registry_report()`: records whether each strategy is exploratory, paper-active, disabled, retired, or live-eligible.
- `build_strategy_retirement_report()`: retires candidates after repeated benchmark-relative or paper-scorecard failures.
- `build_strategy_quarantine_report()`: quarantines strategies when paper behavior diverges from backtest behavior beyond configured tolerances.
- `build_walk_forward_refresh_report()`: identifies stale paper-active strategies, failed OOS refreshes, and promotion-ready walk-forward results.
- `build_holdout_metadata_report()`: validates train/validation/test windows and blocks accidental holdout retuning.
- `build_benchmark_paper_monitor_report()`: disables paper strategies that underperform their benchmark after costs.
- `build_regime_conditioned_scorecard_report()`: records which regimes are tradable for a strategy and which should block new exposure.
- `build_market_cluster_paper_scorecard_report()`: validates paper evidence across market clusters, asset classes, symbol breadth, and session counts.
- `build_capacity_scorecard_report()`: checks observed paper slippage, volume participation, and target-notional capacity.
- `build_sample_size_gate_report()`: prevents thin paper evidence from influencing allocation before trade, session, and symbol minimums are met.
- `build_statistical_confidence_report()`: estimates confidence from excess-return samples and emits small-sample warnings.
- `build_parameter_drift_report()`: compares current optimized parameters against prior approved parameters.
- `build_boring_baseline_control_report()`: requires promoted strategies to justify themselves against buy-and-hold, cash, simple trend, and risk-parity-style baselines.
- `build_ensemble_promotion_report()`: promotes only strategy families with acceptable benchmark edge, low ensemble correlation, and distinct failure modes.
- `build_candidate_ab_paper_test_report()`: records tiny parallel A/B paper tests under separate manifests and scorecards.
- `build_strategy_order_explainability_report()`: stores the signal values, indicator state, regime state, risk gates, and thesis behind each paper order.
- `build_strategy_exit_review_report()`: reviews exits against the original strategy thesis instead of treating PnL as the only judge.
- `build_strategy_audit_report()`: groups active, disabled, retired, exploratory, and live-eligible strategies with review freshness and reasons.
- `build_paper_backtest_replay_report()`: compares actual paper fills against expected backtest fills by order id, price drift, quantity drift, and fill count.
- `build_backtest_paper_expectation_report()`: serializes expected paper behavior from a backtest before any paper orders are submitted.
- `build_fill_model_calibration_report()`: converts observed paper fills into spread/volume-impact calibration evidence.
- `build_slippage_model_version_report()`: records the named/versioned slippage model and parameters used by a backtest.
- `build_latency_aware_backtest_report()`: simulates strategy decision, broker submission, and fill delays for latency-aware backtest evidence.
- `build_intrabar_execution_assumption_report()`: validates stop, limit, and bracket trigger assumptions against paper observations.
- `build_short_borrow_fee_report()`: models locate availability, borrow rates, and short-fee drag before short systems are enabled.
- `build_margin_leverage_cost_report()`: estimates margin interest and blocks leverage assumptions that exceed configured caps.
- `build_corporate_action_cashflow_report()`: checks dividend cashflows and split-adjusted quantities for paper/backtest parity.
- `build_portfolio_rebalance_parity_report()`: compares backtest target notionals against paper-session rebalance targets.
- `build_reference_backtest_comparison_report()`: compares local multi-symbol, partial-fill, rebalance, and exit results against independent references.
- `build_paper_session_regression_fixture_report()`: records real paper-session replay, scorecard, monitor, and reconciliation fixtures for future regression protection.
- `build_optimization_reproducibility_report()`: compares optimization runs across code versions, dependency versions, seeds, best parameters, and scores.
- `build_optimization_budget_report()`: enforces maximum trials, runtime, memory, and failed-trial rates for optimization jobs.
- `build_promotion_overfitting_warning_report()`: embeds parameter-surface, false-discovery, train/holdout gap, and trial-count warnings directly into promotion manifests.
- `build_survivorship_bias_awareness_report()`: checks listing and delisting metadata before broad stock-universe backtests can influence live candidates.
- `build_walk_forward_deployment_simulation_report()`: proves a deployment manifest was selected using only data available before the deployment start.
- `build_daily_operator_cycle_report()`: defines the daily data-sync, research-refresh, scheduled-paper, monitor, report, readiness, and alert-summary cycle.
- `build_windows_task_scheduler_config_report()`: generates pre-market, market-open, intraday, close, and end-of-day Windows Task Scheduler job metadata.
- `build_service_entrypoint_report()`: separates continuous monitoring commands from scheduled paper-session commands for Docker/service deployment.
- `build_process_supervision_report()`: allows restarts for safe monitor/report jobs while blocking automatic restarts for order-submission jobs.
- `build_job_lease_report()`: models lock-file or database-lease acquisition so overlapping scheduled jobs cannot both submit orders.
- `build_command_idempotency_report()`: generates and checks command/date/scope idempotency keys for pilots, monitors, cleanups, and rehearsals.
- `build_artifact_retention_report()`: decides which old reports to keep, archive, or preserve for live-readiness evidence windows.
- `build_secret_management_guidance_report()`: checks `.env`, gitignore, paper URL, live lock, and plaintext-secret safety expectations.
- `build_broker_audit_log_report()`: records run id, command, config hash, evidence paths, broker-touch status, and decision status.
- `build_alert_routing_report()`: verifies alert types and severities route to configured sinks.
- `build_notification_sink_report()`: requires a local notification sink and records optional email/Slack/Discord/webhook sinks.
- `build_deployment_health_check_report()`: checks provider, broker REST/account state, websocket, storage, scheduler, and artifact write health.
- `build_readiness_page_refresh_report()`: records readiness-page refresh evidence after scheduled paper jobs.
- `build_operator_inbox_report()`: lists unresolved operator review items with severity, action, and source artifact metadata.
- `build_deployment_machine_rehearsal_report()`: records rehearsal evidence from the actual intended machine and deployment profile.
- `evaluate_promotion_queue()`: final enablement gate for promoted strategies, combining research promotion, edge, optional capacity, paper scorecard, regime fit, and operator approval.
- `PaperSessionRiskBudget`: per-session safety budget for minimum quantity/notional, maximum session notional, maximum new exposure, turnover, cash reserve, cooldown symbols, and repeated-reject lockouts.
- `alpaca_paper_soak_profiles()`: named dry-run, micro-notional, and full-paper-rehearsal presets with explicit provider, execution-mode, paper URL, paper-trading, credential validation, committee exposure caps, and execution sizing policies. The micro-notional profile uses fractional planning plus a $25 absolute target-notional cap so its planned session notional stays inside the proof budget instead of merely being blocked after planning.
- `evaluate_pre_live_readiness()`: final live-unlock guard that requires clean multi-session paper soaks, submitted-paper evidence, restart-recovery proof, broker-statement matching, no unresolved orders, explicit live implementation proof, and operator approval.

`src.operations.paper_escalation` defines the paper capital ladder and final paper-readiness evidence layer:

- `build_paper_notional_escalation_report()`: graduates paper notional from $25 to $50, $100, $250, $500, and $1,000 only when the required clean-session, exit, scorecard, scheduler, monitor, dashboard, portfolio-risk, and kill-switch evidence exists.
- `build_paper_notional_downshift_decision()`: automatically recommends downshifting after failed monitors, reject streaks, unresolved orders, failed strategy scorecards, or data outages.
- `build_strategy_paper_capital_ladder_report()`: evaluates per-strategy paper ladders so one strategy can remain micro while another graduates.
- `build_paper_live_fire_drill_report()`: tracks flatten-all, cancel-all, stale-order, broker-outage, data-outage, and process-crash paper drill evidence.
- `build_strategy_family_overnight_gate_report()`: blocks overnight holds for any strategy family without a clean paper flatten proof.
- `build_paper_active_evidence_report()`: requires 30 clean paper-active trading days before live micro-capital consideration.
- `build_regime_performance_review_report()`, `build_undertrading_evidence_report()`, and `build_cash_decision_respect_report()`: prove behavior across regimes, including the ability to stay in cash when conditions are poor.
- `build_paper_month_end_review_report()` and `build_scheduler_uptime_evidence_report()`: require complete month-end review sections and two weeks of stable scheduler/deployment uptime before live unlock.

`src.operations.live_readiness` defines the locked live workflow architecture:

- `build_live_broker_adapter_boundary_report()`: verifies paper/live endpoint separation, account fingerprint allowlisting, and no shared live submit defaults.
- `build_live_order_preview_report()`: creates final live-intended orders while explicitly refusing to submit them.
- `build_live_micro_trade_proof_report()`: represents the tiny single-symbol live proof as an operator-approved preview with immediate monitor evidence, still submitted=false in the current MVP.
- `build_live_account_monitor_report()`: compares expected live exposure against broker positions with stricter quantity tolerances than paper.
- `build_live_order_lifecycle_reconciliation_report()`: requires intent, submit, and reconcile lifecycle stages before a live order can be considered complete.
- `build_live_position_flatten_plan_report()`: creates a live flatten preview behind operator approval and an emergency procedure path.
- `build_live_readiness_validation_evidence_report()` and `build_live_release_bundle_report()`: require live-typed evidence plus current paper soak, deployment, monitor, risk, and operator approval.
- `build_live_risk_cap_report()`, `build_live_scheduler_mode_report()`, `build_live_command_confirmation_report()`, `build_one_live_order_per_day_report()`, `build_live_post_order_lockout_report()`, and `build_live_paper_parity_replay_report()`: encode the first live phase as manual, tiny, one-order-per-day, locked after every order until monitor/reconciliation/daily review pass, and replayed against paper/backtest behavior.

`src.operations.live_ramp` defines the live micro-capital ramp discipline:

- `build_live_micro_phase_scope_report()`: restricts the first live phase to one strategy, one symbol or tiny pair, one order per day, and strict max notional.
- `build_live_micro_order_evidence_report()`: requires every live micro order to have preview, monitor, reconciliation, daily report, and parity evidence.
- `build_live_notional_ramp_report()`: allows notional increases only after clean live micro trades, current paper evidence, and operator approval.
- `build_live_issue_response_report()`: locks or downshifts after monitor mismatches, unresolved orders, data outages, rejected orders, slippage breaches, or drawdown breaches.
- `build_parallel_paper_control_report()` and `build_live_paper_fill_comparison_report()`: keep paper control orders active and compare live fills against paper fills.
- `build_live_strategy_quarantine_report()`: quarantines or retires strategies when live fill quality or behavior parity diverges.
- `build_live_capital_ramp_approval_report()`, `build_live_loss_budget_report()`, and `build_post_micro_capital_boundary_report()`: require approval artifacts for every size increase, enforce at least three clean micro months below a loss budget, and treat anything beyond micro-capital as a fresh roadmap phase.

`src.validation.pre_live_evidence` defines the final pre-live proof bundle:

- `build_validation_profile_gate_report()`: requires current passing `fast`, `paper-dry-run`, `paper-submit`, `release`, and `live-gate` profile evidence.
- `build_release_candidate_evidence_bundle_report()`: captures code version, config hash, artifact digests, and readiness HTML for a release candidate.
- `build_paper_trading_day_evidence_report()`, `build_promoted_portfolio_submit_exit_report()`, and `build_drill_count_report()`: gate the required clean paper days, promoted submit/exit cycles, restart recovery drills, outage drills, and flatten/cancel drills.
- `build_live_candidate_strategy_evidence_report()`: requires stable scorecards plus current walk-forward, holdout, cost-stress, and market-cluster evidence for every live candidate.
- `build_deployment_environment_evidence_report()`, `build_secret_leakage_evidence_report()`, `build_live_preview_block_proof_report()`, and `build_operator_emergency_capability_report()`: prove deployment jobs, artifact hygiene, submit blocking, and manual emergency capability.
- `build_written_pre_live_review_report()`: records strategy, rationale, max live notional, stop conditions, rollback procedure, approval, and storage status.
- `build_final_pre_live_evidence_report()` and `build_first_live_micro_order_authorization_report()`: aggregate every blocker and only authorize the first tiny live proof when all prior gates, immediate reconciliation, immediate monitor, and automatic lockout are present.

`src.reporting.build_daily_paper_trading_report()` aggregates paper-session, portfolio-session, soak, and promotion-queue outputs into a daily operator report with decisions, planned/submitted orders, missed or unsubmitted fills, reconciliation/recovery status, scorecard status, warnings, and next-session recommendations.

`src.reporting.paper_observability` defines the first dashboard/reporting view layer:

- `build_paper_dashboard_report()`: combines expected exposure, broker exposure, monitor states, strategy states, open orders, PnL, risk state, and next scheduled action into one operator snapshot. `render_paper_dashboard_html()` and `write_paper_dashboard_html()` turn that snapshot into a reviewable page.
- `build_strategy_review_report()`: assembles strategy-level research evidence, latest trades, scorecards, enablement state, and notes. `render_strategy_review_html()` and `write_strategy_review_html()` produce the first strategy detail page.
- `build_order_lifecycle_timeline()`: records broker-order stages from intent through submit/fill/cancel/reconcile so a paper order can be audited as a timeline instead of a loose group of artifacts.
- `build_position_lifecycle_timeline()`: records active paper-position lifecycle events from entry through exit, including failed or unresolved steps.
- `build_paper_run_comparison_report()`: ranks repeated paper pilot runs by a selected metric so operator reviews can compare sessions over time without digging through raw JSON.

`src.reporting.paper_review` is the modular review and live-readiness layer:

- `build_slippage_fill_quality_report()`: creates chart-ready fill-quality points by symbol, strategy, order type, and timestamp.
- `build_data_drift_chart_report()`: turns provider comparison rows into drift chart points and breach counts.
- `build_readiness_trend_report()`: tracks readiness score, missing checks, failed checks, and stale evidence over time.
- `build_paper_pnl_attribution_chart_report()`: groups paper PnL by strategy, regime, symbol, and holding period.
- `build_paper_review_summary_report()`: summarizes daily, weekly, or monthly paper reports without opening raw artifacts.
- `build_anomaly_highlight_report()`: highlights unusual fill, PnL, exposure, spread, or broker-state observations.
- `build_operator_decision_log_report()`: records operator comments and approvals with timestamped decision context.
- `build_release_candidate_signoff_report()`: summarizes code/config identity, release checks, operator approval, and blockers.
- `build_why_no_live_yet_report()`: lists remaining live gates and keeps the live path explicitly locked until all pass.
- `build_live_readiness_score_report()`: scores live readiness separately from paper readiness; simulated or paper evidence can be recorded, but it cannot satisfy live-only gates.

The current research bench includes three pressure/cycle candidates added after the first Alpaca paper-session submit:

- `volumePressureBreakout`: Donchian breakout filtered by close-location volume pressure and efficiency ratio.
- `absorptionSweepReversal`: liquidity-sweep reversal filtered by high-volume absorption and pressure.
- `hurstCycleReversion`: z-score mean reversion gated by low Hurst persistence.

Latest 10-market Alpaca daily bulk test (`SPY, QQQ, IWM, DIA, TLT, GLD, SLV, USO, XLE, XLK`, 2y) shows optimized `hurstCycleReversion` as the only new candidate selected over buy-and-hold by the benchmark-relative selector, on `SPY` and `DIA`; it averaged lower return than buy-and-hold but with materially lower drawdown. The pressure breakout and absorption reversal are currently defensive/drawdown-control ideas, not return leaders.

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

Items 1-475 are now implemented or planned at the MVP/scaffold level. The operational paper-daemon phase has crossed from architecture into real Alpaca paper proof: one clean submitted intraday daemon activation exists, its resulting SPY micro position was closed and verified flat, and the supervised-soak gate now tracks how many more clean submitted activations and active windows are needed. Trustworthy always-on use still depends on multi-window supervised soaks, stale-heartbeat monitoring, single-instance locks, data parity, restart drills, broker reconciliation evidence, active-position stewardship, and repeatable flatten drills.

## Development Notes

- Prefer `RuntimeConfig` and `load_runtime_config()` for new workflows.
- Prefer `src.backtesting` for historical simulation.
- Prefer `src.reporting` for summaries, plots, JSON, and HTML output.
- Keep generated artifacts under `runs/` or `reports/`.
- Keep `PAPER_TRADING=true` unless live execution is deliberately implemented later.
- Do not connect this to live capital until the broker reconciliation, risk halt, persistence, and kill-switch roadmap items are complete and tested.

Additional deployment notes are in `docs/DEPLOYMENT.md`.
