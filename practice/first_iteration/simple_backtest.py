import yfinance as yf
import pandas as pd

df = yf.download("SPY", period="5y")
df["SMA20"] = df["Close"].rolling(20).mean()
df["SMA50"] = df["Close"].rolling(50).mean()
df["Buy"] = (df["SMA20"] > df["SMA50"]) & (df["SMA20"].shift(1) <= df["SMA50"].shift(1))
df["Sell"] = (df["SMA20"] < df["SMA50"]) & (df["SMA20"].shift(1) >= df["SMA50"].shift(1))
df.loc[df["Buy"] | df["Sell"], ["Buy", "Sell", "SMA20", "SMA50"]]