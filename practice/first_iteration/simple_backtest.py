import yfinance as yf
import pandas as pd

BIG_SMA = 100
SMALL_SMA = 50
ACCOUNT_SIZE = 10000
PERCENTAGE_INVESTED = 1.0

df = yf.download("SPY", period="2y", interval="4h", multi_level_index=False)

df[f"SMA{SMALL_SMA}"] = df["Close"].rolling(SMALL_SMA).mean()
df[f"SMA{BIG_SMA}"] = df["Close"].rolling(BIG_SMA).mean()

df["Buy"] = (df[f"SMA{SMALL_SMA}"] > df[f"SMA{BIG_SMA}"]) & (df[f"SMA{SMALL_SMA}"].shift(1) <= df[f"SMA{BIG_SMA}"].shift(1))
df["Sell"] = (df[f"SMA{SMALL_SMA}"] < df[f"SMA{BIG_SMA}"]) & (df[f"SMA{SMALL_SMA}"].shift(1) >= df[f"SMA{BIG_SMA}"].shift(1))

first_sell_date = df[df["Sell"]].index.min()
last_buy_date = df[df["Buy"]].index.max()

df.loc[first_sell_date, "Sell"] = False 
df.loc[last_buy_date, "Buy"] = False 

df["In Position"] = pd.NA
df.loc[df["Buy"], "In Position"] = True
df.loc[df["Sell"], "In Position"] = False
df["In Position"] = df["In Position"].ffill().fillna(False)

df["Position Change"] = (~df["In Position"].shift(1).fillna(False) & df["Buy"]) | (df["In Position"].shift(1).fillna(False) & df["Sell"])

events = df.loc[df["Position Change"], ["Position Change", "Close", "Buy", "Sell"]]

entries = events.loc[df["Buy"], "Close"]
exits = events.loc[df["Sell"], "Close"]

try:
    trades = pd.DataFrame({'Entry Date': entries.index, 'Entry Price': entries.values, 'Exit Date': exits.index, 'Exit Price': exits.values})
except ValueError:
    print("Error: The number of buy and sell signals do not match. Please check the data. Buy signals:", len(entries), "Sell signals:", len(exits))
    raise

trades["Return"] = (trades["Exit Price"] - trades["Entry Price"]) / trades["Entry Price"]

total_return = (1 + trades["Return"]).cumprod().iloc[-1] - 1

print(f"Total Return: {total_return * 100:.2f}%")
print(f"Total Equity: {total_return * ACCOUNT_SIZE * PERCENTAGE_INVESTED:.2f}%")