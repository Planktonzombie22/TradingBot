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
        atr = ATR(self.df).calculate().to_numpy()
        high = self.df['High'].to_numpy()
        low = self.df['Low'].to_numpy()
        close = self.df['Close'].to_numpy()

        st = np.full(len(self.df), np.nan)
        direction = np.full(len(self.df), 1, dtype=int)

        for i in range(self.period, len(self.df)):
            hl2 = (high[i] + low[i]) / 2.0
            
            if direction[i-1] == 1:
                current = hl2 - atr[i] * self.multiplier
                st[i] = current if i == self.period else max(current, st[i-1]) if not np.isnan(st[i-1]) else current
                direction[i] = -1 if close[i] < st[i] else 1
                if direction[i] == -1:
                    st[i] = hl2 + atr[i] * self.multiplier
            else:
                current = hl2 + atr[i] * self.multiplier
                st[i] = current if i == self.period else min(current, st[i-1]) if not np.isnan(st[i-1]) else current
                direction[i] = 1 if close[i] > st[i] else -1
                if direction[i] == 1:
                    st[i] = hl2 - atr[i] * self.multiplier

        return pd.Series(st, index=self.df.index, name='SuperTrend')
    

class ADX:
    def __init__(self, df, period=14):
        self.df = df.copy()
        self.period = period
    
    def calculate(self):
        up = self.df["High"] - self.df["High"].shift(1)
        down = self.df["Low"].shift(1) - self.df["Low"]

        dmp = up.where((up > down) & (up > 0), 0)
        dmm = down.where((down > up) & (down > 0), 0)

        dmp = dmp.ewm(com=self.period-1, adjust=False).mean()
        dmm = dmm.ewm(com=self.period-1, adjust=False).mean()

        atr = ATR(self.df).calculate().replace(0, np.nan)
        dip = 100 * dmp / atr
        dim = 100 * dmm / atr

        denom = (dip + dim).replace(0, np.nan)
        dx = 100 * (dip - dim).abs() / denom
        adx = dx.ewm(com=self.period-1, adjust=False).mean()
        adx[:self.period] = np.nan
        return adx


class RSI:
    def __init__(self, df, period=14):
        self.df = df.copy()
        self.period = period
    
    def calculate(self):
        delta = self.df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=self.period-1, adjust=False).mean()
        avg_loss = loss.ewm(com=self.period-1, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        rsi.iloc[:self.period] = np.nan
        return rsi

class DEMA:
    def __init__(self, df=df, period=cfg.DEMA_PERIOD):
        self.df = df.copy()
        self.period = period
    
    def calculate(self):
        dema1 = self.df['Close'].ewm(span=self.period, adjust=False).mean()
        dema2 = dema1.ewm(span=self.period, adjust=False).mean()
        return pd.Series(2 * dema1 - dema2, index=self.df.index, name='DEMA')