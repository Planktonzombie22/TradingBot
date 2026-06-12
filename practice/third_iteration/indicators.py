#cspell:words supertrend dema
import config as cfg
import numpy as np
import pandas as pd
from data import df

class ATR:
    def __init__(self, df=df, period=cfg.ATR_PERIOD):
        self.df = df.copy()
        self.period = period

    def calculate(self):
        tr = np.maximum(self.df['High'] - self.df['Low'],
                        np.maximum(abs(self.df['High'] - self.df['Close'].shift(1)),
                                   abs(self.df['Low'] - self.df['Close'].shift(1))))
        return tr.ewm(com=self.period - 1, adjust=False).mean()
    
class SuperTrend:
    def __init__(self, df=df, period=cfg.SUPER_TREND_PERIOD, multiplier=cfg.SUPER_TREND_MULTIPLIER):
        self.df = df.copy()
        self.period = period
        self.multiplier = multiplier

    def calculate(self):
        direction = 1
        self.df['SuperTrend'] = np.nan
        st_loc = self.df.columns.get_loc('SuperTrend')
        self.df['ATR'] = ATR(self.df).calculate()
        for index, row in enumerate(self.df.itertuples()):
            if index < self.period:
                continue
            
            previous = self.df.iloc[index - 1, st_loc]
            if pd.isna(previous):
                previous = (row.High + row.Low) / 2
            
            if direction == 1:
                current = (row.High + row.Low) / 2 - row.ATR * self.multiplier
                self.df.iloc[index, st_loc] = current if current > previous else previous
                if row.Close < self.df.iloc[index, st_loc]:
                    direction = -1
            
            elif direction == -1:
                current = (row.High + row.Low) / 2 + row.ATR * self.multiplier
                self.df.iloc[index, st_loc] = current if current < previous else previous
                if row.Close > self.df.iloc[index, st_loc]:
                    direction = 1
        return self.df['SuperTrend']
    

class ADX:
    def __init__(self, df, period=14):
        self.df = df.copy()
        self.period = period
    
    def calculate(self):
        self.df["+DM"] = (self.df["High"] - self.df["High"].shift(1)).clip(lower=0).rolling(self.period).mean()
        self.df["-DM"] = (self.df["Low"].shift(1) - self.df["Low"]).clip(lower=0).rolling(self.period).mean()
        atr = ATR(self.df).calculate().replace(0, np.nan)
        self.df["+DI"] = 100 * self.df["+DM"] / atr
        self.df["-DI"] = 100 * self.df["-DM"] / atr
        self.df["DX"] = 100 * abs(self.df["+DI"] - self.df["-DI"]) / (self.df["+DI"] + self.df["-DI"])
        self.df["ADX"] = self.df["DX"].ewm(com=self.period-1, adjust=False).mean()
        return self.df["ADX"].dropna()


class RSI:
    def __init__(self, df, period=14):
        self.df = df.copy()
        self.period = period
    
    def calculate(self):
        self.df["Delta"] = self.df['Close'].diff()
        self.df["Gain"] = self.df["Delta"].clip(lower=0)
        self.df["Loss"] = -self.df["Delta"].clip(upper=0)
        self.df["Avg_Gain"] = self.df["Gain"].ewm(com=self.period-1, adjust=False).mean()
        self.df["Avg_Loss"] = self.df["Loss"].ewm(com=self.period-1, adjust=False).mean()
        self.df["RS"] = self.df["Avg_Gain"] / self.df["Avg_Loss"]
        self.df["RSI"] = 100 - (100 / (1 + self.df["RS"]))
        return self.df["RSI"].dropna()

class DEMA:
    def __init__(self, df=df, period=cfg.DEMA_PERIOD):
        self.df = df.copy()
        self.period = period
    
    def calculate(self):
        self.df['DEMA1'] = self.df['Close'].ewm(span=self.period, adjust=False).mean()
        self.df['DEMA2'] = self.df['DEMA1'].ewm(span=self.period, adjust=False).mean()
        return 2 * self.df['DEMA1'] - self.df['DEMA2']