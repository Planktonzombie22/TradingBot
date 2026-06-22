#cspell:words backtest DEMA SUPERTREND sharex figsize ylabel xlabel zorder
import config as cfg
import pandas as pd
import indicators as ind
import data
import matplotlib.pyplot as plt

#Gather indicator data
df = data.df.dropna()

#iterate through simulation
position = None
current_trade = None
trades = []
equity_curve = []
equity_current = cfg.ACCOUNT_SIZE
money_available_curve = []

for ts, row in df.iterrows():
    if current_trade is None:
        available_money = equity_current

    # exit first (at close)
    if position is not None and indicator_df.loc[ts, "SuperTrend_Flip"]:
        current_trade["Exit Date"] = ts
        current_trade["Exit Price"] = row.Close
        pnl = current_trade["Shares"] * (row.Close - current_trade["Entry Price"])
        current_trade["PnL"] = pnl
        equity_current = current_trade["Entry Equity"] + pnl
        current_trade["Exit Equity"] = equity_current
        trades.append(current_trade)
        position = None
        current_trade = None
        available_money = equity_current

    percentage = cfg.PERCENTAGE_RISKED 
    if percentage > 1:
        percentage /= 100
    max_investment = max(available_money, 0.0) * percentage

    if row.Buy and position != "Long" and available_money > 0:
        stop_distance = row.Close - indicator_df.loc[ts, "SuperTrend"]
        if stop_distance > 0:
            shares = max_investment / stop_distance
            cost = shares * row.Close
            max_exposure = available_money * cfg.MARGIN_RATIO
            if cost > max_exposure:
                shares = max_exposure / row.Close
                cost = shares * row.Close
            if shares > 0:
                current_trade = {
                    "Entry Date": ts,
                    "Entry Price": row.Close,
                    "Type": "Long",
                    "Shares": shares,
                    "Entry Equity": equity_current,
                }
                position = "Long"
                available_money -= cost / cfg.MARGIN_RATIO

    elif row.Sell and position != "Short" and available_money > 0:
        stop_distance = indicator_df.loc[ts, "SuperTrend"] - row.Close
        if stop_distance > 0:
            shares = max_investment / stop_distance
            cost = shares * row.Close
            max_exposure = available_money * cfg.MARGIN_RATIO
            if cost > max_exposure:
                shares = max_exposure / row.Close
                cost = shares * row.Close
            if shares > 0:
                current_trade = {
                    "Entry Date": ts,
                    "Entry Price": row.Close,
                    "Type": "Short",
                    "Shares": -shares,
                    "Entry Equity": equity_current,
                }
                position = "Short"
                available_money -= cost / cfg.MARGIN_RATIO

    # mark-to-market equity for this bar
    if position is not None and current_trade is not None:
        pnl = current_trade["Shares"] * (row.Close - current_trade["Entry Price"])
        equity_point = current_trade["Entry Equity"] + pnl
    else:
        equity_point = equity_current

    equity_curve.append(equity_point)
    money_available_curve.append(available_money)

# close any open trade at the last bar
if current_trade is not None:
    last_ts = df.index[-1]
    last_price = df["Close"].iloc[-1]
    current_trade["Exit Date"] = last_ts
    current_trade["Exit Price"] = last_price
    pnl = current_trade["Shares"] * (last_price - current_trade["Entry Price"])
    current_trade["PnL"] = pnl
    equity_current = current_trade["Entry Equity"] + pnl
    current_trade["Exit Equity"] = equity_current
    trades.append(current_trade)
    equity_curve[-1] = equity_current
    money_available_curve[-1] = equity_current

equity = pd.Series(equity_curve, index=df.index)
money_available = pd.Series(money_available_curve, index=df.index)
trades = pd.DataFrame(trades)

#PnL calculation
total_PnL_pct = (equity.iloc[-1] - cfg.ACCOUNT_SIZE) / cfg.ACCOUNT_SIZE
total_PnL = (equity.iloc[-1] - cfg.ACCOUNT_SIZE)

#Plot data
fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, sharex=True, figsize=(14, 14))

ax1.plot(df.index, df["Close"], label="Close Price", color="teal")
ax1.plot(indicator_df.index, indicator_df["DEMA"], label="DEMA", color="orange")
ax1.plot(indicator_df.index, indicator_df["SuperTrend"], label="SuperTrend", color="blue")
ax1.set_title("Price, DEMA and SuperTrend")
ax1.set_ylabel("Price")
ax1.legend(loc="upper left")

ax2.plot(indicator_df.index, indicator_df["RSI"], label="RSI", color="red")
ax2.plot(indicator_df.index, indicator_df["ADX"], label="ADX", color="yellow")
ax2.set_title("RSI and ADX")
ax2.set_ylabel("Indicator")
ax2.legend(loc="upper left")

ax3.plot(equity.index, equity, label="Equity Curve", color="purple")
ax3.set_title("Equity Curve")
ax3.set_ylabel("Equity")
ax3.set_xlabel("Date")
ax3.legend(loc="upper left")

ax4.plot(money_available.index, money_available, label="Money Available", color="pink")
ax4.set_title("Money Available")
ax4.set_ylabel("Money")
ax4.set_xlabel("Date")
ax4.legend(loc="upper left")

if not trades.empty:
    longs = trades[trades["Type"] == "Long"]
    shorts = trades[trades["Type"] == "Short"]

    if not longs.empty:
        ax1.scatter(longs["Entry Date"], longs["Entry Price"], marker="^", color="green", s=60, label="Long Entry", zorder=5)
        ax1.scatter(longs["Exit Date"], longs["Exit Price"], marker="o", color="green", s=60, label="Long Exit", zorder=5)
        ax2.scatter(longs["Entry Date"], indicator_df.loc[longs["Entry Date"], "RSI"], marker="^", color="green", s=60, label="Long Entry", zorder=5)
        ax2.scatter(longs["Exit Date"], indicator_df.loc[longs["Exit Date"], "RSI"], marker="o", color="green", s=60, label="Long Exit", zorder=5)
        ax3.scatter(longs["Entry Date"], longs["Entry Equity"], marker="^", color="green", s=60, label="Long Entry", zorder=5)
        ax3.scatter(longs["Exit Date"], longs["Exit Equity"], marker="o", color="green", s=60, label="Long Exit", zorder=5)
        ax4.scatter(longs["Entry Date"], money_available.loc[longs["Entry Date"]], marker="^", color="green", s=60, label="Long Entry", zorder=5)
        ax4.scatter(longs["Exit Date"], money_available.loc[longs["Exit Date"]], marker="o", color="green", s=60, label="Long Exit", zorder=5)

    if not shorts.empty:
        ax1.scatter(shorts["Entry Date"], shorts["Entry Price"], marker="v", color="red", s=60, label="Short Entry", zorder=5)
        ax1.scatter(shorts["Exit Date"], shorts["Exit Price"], marker="o", color="red", s=60, label="Short Exit", zorder=5)
        ax2.scatter(shorts["Entry Date"], indicator_df.loc[shorts["Entry Date"], "RSI"], marker="v", color="red", s=60, label="Short Entry", zorder=5)
        ax2.scatter(shorts["Exit Date"], indicator_df.loc[shorts["Exit Date"], "RSI"], marker="o", color="red", s=60, label="Short Exit", zorder=5)
        ax3.scatter(shorts["Entry Date"], shorts["Entry Equity"], marker="v", color="red", s=60, label="Short Entry", zorder=5)
        ax3.scatter(shorts["Exit Date"], shorts["Exit Equity"], marker="o", color="red", s=60, label="Short Exit", zorder=5)
        ax4.scatter(shorts["Entry Date"], money_available.loc[shorts["Entry Date"]], marker="v", color="red", s=60, label="Short Entry", zorder=5)
        ax4.scatter(shorts["Exit Date"], money_available.loc[shorts["Exit Date"]], marker="o", color="red", s=60, label="Short Exit", zorder=5)

    ax1.legend(loc="upper left")

plt.tight_layout()
plt.show()
print(f"Total PnL: {total_PnL_pct:.2%}")
print(f"Total PnL: ${total_PnL:.2f}")