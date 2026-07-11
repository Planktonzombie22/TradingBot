from abc import ABC, abstractmethod
from typing import Iterable

import pandas as pd


class Indicator(ABC):
    """Base class for deterministic, dataframe-backed indicators."""

    required_columns: tuple[str, ...] = ("Close",)

    def __init__(self, df: pd.DataFrame):
        self.df = self._validated_frame(df, self.required_columns)

    @abstractmethod
    def calculate(self) -> pd.Series:
        raise NotImplementedError

    @staticmethod
    def _validated_frame(df: pd.DataFrame, required_columns: Iterable[str]) -> pd.DataFrame:
        if df.empty:
            raise ValueError("Indicator input data cannot be empty.")

        missing = set(required_columns).difference(df.columns)
        if missing:
            raise ValueError(f"Indicator input is missing required columns: {sorted(missing)}")

        frame = df.copy()
        for column in required_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return frame
