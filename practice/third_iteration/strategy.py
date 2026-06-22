#cspell:words DEMA
import indicators as ind
from data import df
import pandas as pd


"""TODO: implement strategy separation and eliminate look-ahead bias"""


st = ind.SuperTrend(df)

indicator_df = pd.DataFrame({
    'ATR': ind.ATR(df).calculate(),
    'SuperTrend': st.calculate(),
    'SuperTrend_Flip': st.get_flip_signals(),
    'ADX': ind.ADX(df).calculate(),
    'RSI': ind.RSI(df).calculate(),
    'DEMA': ind.DEMA(df).calculate(),
}, index=df.index).interpolate(method='time', limit_area='inside')

class tuffSystem():
    def __init__(self, adx_deviation, rsi_deviation):
        self.adx_deviation = adx_deviation
        self.rsi_deviation = rsi_deviation

    def generate_buy_signals():
        return (
            (df["Close"] > indicator_df["DEMA"]) &
            (indicator_df["RSI"] > 55) &
            (indicator_df["ADX"] > 30) &
            (indicator_df["ATR"] > 0) &
            (indicator_df["SuperTrend"] < df["Close"])
        ).fillna(False)

    def generate_sell_signals():
        return (
            (df["Close"] < indicator_df["DEMA"]) &
            (indicator_df["RSI"] < 45) &
            (indicator_df["ADX"] > 30) &
            (indicator_df["ATR"] > 0) &
            (indicator_df["SuperTrend"] > df["Close"])
        ).fillna(False)
