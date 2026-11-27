@echo off
setlocal
cd /d "%~dp0"
if exist "runs\paper-daemon.kill" (
  echo Paper daemon kill switch is active: runs\paper-daemon.kill
  echo Run "trading_env\Scripts\python.exe main.py paper-daemon-clear-stop" before starting.
  exit /b 1
)
if exist "trading_env\Scripts\python.exe" (
  "trading_env\Scripts\python.exe" main.py paper-daemon --provider alpaca --execution-mode paper --symbol SPY --paper-profile micro-notional --submit-orders
) else (
  py main.py paper-daemon --provider alpaca --execution-mode paper --symbol SPY --paper-profile micro-notional --submit-orders
)
