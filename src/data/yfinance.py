from typing import Iterable, Optional

import pandas as pd
import yfinance as yf

from src.models import Bar

from .interface import DataFeed


class YFinanceDataFeed(DataFeed):
    def get_historical(
        self,
        symbol: str,
        start=None,
        end=None,
        interval: str = "1d",
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        kwargs = {
            "tickers": symbol,
            "interval": interval,
        }
        if period is not None:
            kwargs["period"] = period
        else:
            kwargs["start"] = start
            kwargs["end"] = end

        df = yf.download(**kwargs)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        return df.sort_index()

    def get_stream(self, symbol: str) -> Iterable[Bar]:
        raise NotImplementedError("Live streaming is not implemented yet.")
