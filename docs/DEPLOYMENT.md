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

## 9. Soak Checklist

Before unattended paper trading, complete `docs/PAPER_TRADING_SOAK_CHECKLIST.md`.
