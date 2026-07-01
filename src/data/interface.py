from abc import ABC, abstractmethod
from typing import Iterable, Optional

import pandas as pd

from src.models import Bar


class DataFeed(ABC):
    """Source of market data for backtests, paper trading, or live trading."""

    @abstractmethod
    def get_historical(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        interval: str = "1d",
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_stream(self, symbol: str) -> Iterable[Bar]:
        raise NotImplementedError
