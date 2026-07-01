# cspell:words dotenv ATR SUPER_TREND ADX RSI DEMA SUPERTREND
import os

from dotenv import load_dotenv

load_dotenv()

# Live trading (future)
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# Indicator periods
ATR_PERIOD = 10
SUPER_TREND_PERIOD = 10
SUPER_TREND_MULTIPLIER = 4
ADX_PERIOD = 14
RSI_PERIOD = 14
DEMA_PERIOD = 50

# Backtest defaults
ACCOUNT_SIZE = 10_000
PERCENTAGE_INVESTED = 0.01
MARGIN_RATIO = 5
PERCENTAGE_RISKED = PERCENTAGE_INVESTED * MARGIN_RATIO
RISK_PER_TRADE = 1

MARKET = "SPY"
PERIOD = "2y"
INTERVAL = "4h"

DEFAULT_STRATEGY = "tuffSystem"
