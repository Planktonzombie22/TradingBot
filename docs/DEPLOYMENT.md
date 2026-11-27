# TradingBot Deployment Notes

This project is still a research/paper-trading system. Do not connect it to live capital until broker reconciliation, risk controls, market calendar coverage, and kill-switch behavior have been reviewed.

## 1. Environment

```powershell
python -m venv trading_env
trading_env\Scripts\python.exe -m pip install -r requirements.txt
```

Create `.env` from `.env.example` and fill provider credentials as needed.

## 2. Verify

```powershell
trading_env\Scripts\python.exe -m compileall src main.py
trading_env\Scripts\python.exe -m pytest src\tests
```

## 3. Offline Backtest

```powershell
trading_env\Scripts\python.exe main.py backtest --provider sample --strategy buyHold
```

## 4. Paper Runtime Replay

```powershell
trading_env\Scripts\python.exe main.py paper --provider sample --strategy buyHold
```

## 5. Alpaca Paper Stream

```powershell
trading_env\Scripts\python.exe main.py paper --provider alpaca --symbol SPY
```

Required `.env` values:

```dotenv
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_STREAM_URL=wss://stream.data.alpaca.markets/v2/iex
```

## 6. Reports

```powershell
trading_env\Scripts\python.exe main.py report --html-output reports\backtest.html
trading_env\Scripts\python.exe main.py backtest --output reports\backtest.json
```

## 7. Operating Notes

- Keep `PAPER_TRADING=true` until live execution is deliberately implemented.
- Store generated run artifacts under `runs/` or `reports/`.
- Review logs and broker reports before trusting order state.
- Add a process supervisor only after the paper runtime is stable.

## 8. Deployment Profiles

The code exposes deployment profile scaffolds in `src.deployment`:

- `local_windows_task_profile()`: Windows Task Scheduler shape.
- `docker_profile()`: container command/env shape.
- `small_server_profile()`: small always-on server shape.

Treat these as templates, not a green light for unattended trading. Run the paper soak checklist first.

## 9. Windows Paper Daemon

For a manual double-click start, use `Run Paper Daemon.bat`. It refuses to start when `runs\paper-daemon.kill` exists.

For Windows Task Scheduler, create a task that starts in this repository directory and runs:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon --provider alpaca --execution-mode paper --symbol SPY --paper-profile micro-notional --submit-orders
```

Useful operator commands:

```powershell
trading_env\Scripts\python.exe main.py paper-daemon-status
trading_env\Scripts\python.exe main.py paper-daemon-stop
trading_env\Scripts\python.exe main.py paper-daemon-clear-stop
```

The daemon now uses a local single-instance lock at `runs\paper-daemon.lock`. If a prior process crashed, the lock can be replaced after the configured stale age with `--paper-daemon-lock-stale-seconds`.

Do not configure automatic restart for paper order submission until the daemon has clean soak evidence, current monitor evidence, and a tested kill-switch drill.

## 10. Soak Checklist

Before unattended paper trading, complete `docs/PAPER_TRADING_SOAK_CHECKLIST.md`.

## 11. Desktop GUI Packaging

The GUI can already be opened with:

```powershell
trading_env\Scripts\python.exe gui_app.py
```

`src.deployment.build_gui_executable_packaging_report()` now creates a PyInstaller packaging plan for a future one-file Windows operator app. The report validates that `gui_app.py`, `main.py`, and `src/` exist, records the included config/docs paths, and emits the exact command shape without running the freezer. Treat this as release evidence first; build the executable only after the GUI has clean smoke tests and current paper-soak artifacts.
