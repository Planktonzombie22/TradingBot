from abc import ABC, abstractmethod

import pandas as pd

from src.models import Signal


class Strategy(ABC):
    """Produces one Signal per bar — the sole contract between strategy and execution."""

    def __init__(self, symbol: str):
        self.symbol = symbol

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Return a Series of Signal objects aligned to df.index."""
        raise NotImplementedError

    @property
    def indicators(self) -> pd.DataFrame:
        """Optional indicator snapshot for analysis and charting."""
        return pd.DataFrame()
