#cspell:words backtest DEMA SUPERTREND sharex figsize ylabel xlabel zorder stoplosses
import config as cfg
import pandas as pd
import data
import matplotlib.pyplot as plt
import strategy as sty

def fill_in_trade_entry(ts, price, type, shares, equity):
    return {
            "Entry Date": ts,
            "Entry Price": price,
            "Type": type,
            "Shares": shares,
            "Entry Equity": equity
            }
    
def fill_in_trade_exit(trade, ts, price):
    pnl = trade["Shares"] * (price - trade["Entry Price"])
    trade["PnL"] = pnl
    trade["Exit Date"] = ts
    trade["Exit Price"] = price
    trade["Exit Equity"] = trade["Entry Equity"] + pnl
    return trade


strategy = sty.STRATEGIES[cfg.SYSTEM]()
buy_signals = strategy.generate_buy_signals()
sell_signals = strategy.generate_sell_signals()
stop_signals = strategy.generate_stop_signals()
stoplosses = strategy.generate_stoplosses()

#Gather indicator data
df = data.df.dropna()

#iterate through simulation
position = None
current_trade = {}
trades, equity_curve, money_available_curve = [], [], []
equity_current = cfg.ACCOUNT_SIZE

for ts, row in df.iterrows():
    if not current_trade:
        available_money = equity_current

    # exit first (at close)
    if position is not None and stop_signals[ts]:
        current_trade = fill_in_trade_exit(current_trade, ts, row.Close)
        equity_current = current_trade["Exit Equity"]
        trades.append(current_trade)
        current_trade = {}
        position = None
        available_money = equity_current

    percentage = cfg.PERCENTAGE_RISKED 
    if percentage > 1:
        percentage /= 100
    max_investment = max(available_money, 0.0) * percentage

    if buy_signals[ts] and position != "Long" and available_money > 0:
        stop_distance = row.Close - stoplosses[ts]
        if stop_distance > 0:
            shares = max_investment / stop_distance
            cost = shares * row.Close
            max_exposure = available_money * cfg.MARGIN_RATIO
            if cost > max_exposure:
                shares = max_exposure / row.Close
                cost = shares * row.Close
            if shares > 0:
                current_trade = fill_in_trade_entry(ts, row.Close, "Long", shares, equity_current)
                position = "Long"
                available_money -= cost / cfg.MARGIN_RATIO

    elif sell_signals[ts] and position != "Short" and available_money > 0:
        stop_distance = stoplosses[ts] - row.Close
        if stop_distance > 0:
            shares = max_investment / stop_distance
            cost = shares * row.Close
            max_exposure = available_money * cfg.MARGIN_RATIO
            if cost > max_exposure:
                shares = max_exposure / row.Close
                cost = shares * row.Close
            if shares > 0:
                current_trade = fill_in_trade_entry(ts, row.Close, "Short", -shares, equity_current)
                position = "Short"
                available_money -= cost / cfg.MARGIN_RATIO

    # mark-to-market equity for this bar
    if position is not None and current_trade:
        pnl = current_trade["Shares"] * (row.Close - current_trade["Entry Price"])
        equity_point = current_trade["Entry Equity"] + pnl
    else:
        equity_point = equity_current

    equity_curve.append(equity_point)
    money_available_curve.append(available_money)

# close any open trade at the last bar
if current_trade:
    current_trade = fill_in_trade_exit(current_trade, df.index[-1], df["Close"].iloc[-1])
    equity_current = current_trade["Exit Equity"]
    trades.append(current_trade)
    equity_curve[-1] = equity_current
    money_available_curve[-1] = equity_current

equity = pd.Series(equity_curve, index=df.index)
money_available = pd.Series(money_available_curve, index=df.index)
trades = pd.DataFrame(trades)

#PnL calculation
total_PnL_pct = (equity.iloc[-1] - cfg.ACCOUNT_SIZE) / cfg.ACCOUNT_SIZE
total_PnL = (equity.iloc[-1] - cfg.ACCOUNT_SIZE)