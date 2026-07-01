#cspell:words DEMA Supertrend stoplosses
import indicators as ind
from data import df
import pandas as pd


st = ind.SuperTrend(df)

class tuffSystem():
    def __init__(self, adx_minimum=30, rsi_deviation=5):
        self.adx_deviation = adx_minimum
        self.rsi_deviation = rsi_deviation
        self.indicator_df = pd.DataFrame({
                        'ATR': ind.ATR(df).calculate(),
                        'SuperTrend': st.calculate(),
                        'SuperTrend_Flip': st.get_flip_signals(),
                        'ADX': ind.ADX(df).calculate(),
                        'RSI': ind.RSI(df).calculate(),
                        'DEMA': ind.DEMA(df).calculate(),
                                        }, index=df.index).interpolate(method='time', limit_area='inside')

    def generate_buy_signals(self):
        return (
            (df["Close"] > self.indicator_df["DEMA"]) &
            (self.indicator_df["RSI"] > 50 + self.rsi_deviation) &
            (self.indicator_df["ADX"] > self.adx_deviation) &
            (self.indicator_df["ATR"] > 0) &
            (self.indicator_df["SuperTrend"] < df["Close"])
        ).shift(1).fillna(False)

    def generate_sell_signals(self):
        return (
            (df["Close"] < self.indicator_df["DEMA"]) &
            (self.indicator_df["RSI"] < 50 - self.rsi_deviation) &
            (self.indicator_df["ADX"] > self.adx_deviation) &
            (self.indicator_df["ATR"] > 0) &
            (self.indicator_df["SuperTrend"] > df["Close"])
        ).shift(1).fillna(False)
    
    def generate_stop_signals(self):
        return self.indicator_df["SuperTrend_Flip"].shift(1).fillna(False)
    
    def generate_stoplosses(self):
        return self.indicator_df["SuperTrend"].shift(1).fillna(False)

STRATEGIES = {
    "tuffSystem" : tuffSystem
}