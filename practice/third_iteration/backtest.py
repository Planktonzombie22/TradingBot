#cspell:words backtest DEMA
import config as cfg
import pandas as pd
import indicators as ind
from data import df


indicator_df = pd.DataFrame({'ATR': ind.ATR(df).calculate(),
                            'SuperTrend': ind.SuperTrend(df).calculate(),
                            'ADX': ind.ADX(df).calculate(),
                            'RSI': ind.RSI(df).calculate(),
                            'DEMA': ind.DEMA(df).calculate()}, index=df.index).dropna()


for row in indicator_df.itertuples():
    pass