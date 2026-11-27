@echo off
setlocal
cd /d "%~dp0"
if exist "trading_env\Scripts\python.exe" (
  "trading_env\Scripts\python.exe" gui_app.py
) else (
  py gui_app.py
)
