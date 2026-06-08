import yfinance as yf
import pandas as pd

BIG_SMA = 100
SMALL_SMA = 50
STOP_LOSS_PERCENTAGE = 0.02
RR_RATIO = 2
ACCOUNT_SIZE = 10000
PERCENTAGE_INVESTED = 1.0

df = yf.download("SPY", period="2y", interval="4h", multi_level_index=False)

df["SMA100"] = df["Close"].rolling(BIG_SMA).mean()
df["SMA50"] = df["Close"].rolling(SMALL_SMA).mean()

df["Change"] = df["Close"] - df["Close"].shift(1)
df["Increase"] = df["Change"].clip(lower=0)
df["Decrease"] = (df["Change"].clip(upper=0)).abs()

df["RSI"] = 100 - (100 / (1 + df["Increase"].rolling(14).mean() / df["Decrease"].rolling(14).mean()))
df.dropna(inplace=True)

in_position = False
trades = []

for row in df.itertuples():
    if row.RSI < 30:
        if not in_position:
            print(f"Buy at {row.Close}")
            in_position = True
            trades.append({"Entry Date": row.index, "Exit Date": None, "Entry Price": row.Close, "Stop Loss": row.Close * (1 - STOP_LOSS_PERCENTAGE), "Take Profit": row.Close * (1 + STOP_LOSS_PERCENTAGE * RR_RATIO)})
    elif row.RSI > 70:
        if in_position:
            print(f"Sell at {row.Close}")
            in_position = False
            trades[-1]["Exit Price"] = row.Close
            trades[-1]["Exit Date"] = row.index

    if in_position:
        if row.Close <= trades[-1]["Stop Loss"]:
            print(f"Stop Loss hit at {row.Close}")
            in_position = False
            trades[-1]["Exit Price"] = row.Close
            trades[-1]["Exit Date"] = row.index
        elif row.Close >= trades[-1]["Take Profit"]:
            print(f"Take Profit hit at {row.Close}")
            in_position = False
            trades[-1]["Exit Price"] = row.Close
            trades[-1]["Exit Date"] = row.index

if "Exit Price" not in trades[-1]:
    trades[-1]["Exit Price"] = df.iloc[-1]["Close"]

trades_df = pd.DataFrame(trades)
trades_df["PnL"] = trades_df["Exit Price"] - trades_df["Entry Price"]
trades_df["PnL %"] = trades_df["PnL"] / trades_df["Entry Price"] * 100
trades_df["PnL Equity"] = trades_df["PnL %"] * ACCOUNT_SIZE * PERCENTAGE_INVESTED

print(f"Total PnL: {trades_df['PnL'].sum():.2f}")
print(f"Total PnL %: {(1 + (trades_df['PnL %'] / 100)).prod() - 1:.2f}%")
print(f"Total PnL Equity: {trades_df['PnL Equity'].sum():.2f}")