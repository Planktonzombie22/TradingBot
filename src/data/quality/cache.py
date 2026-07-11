from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import pandas as pd


@dataclass(frozen=True)
class HistoricalDataCache:
    """Simple CSV cache for hydrated historical OHLCV data."""

    root: Union[str, Path]

    def read(
        self,
        provider: str,
        symbol: str,
        interval: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        path = self.path_for(provider, symbol, interval, start, end)
        if not path.exists():
            return None
        data = pd.read_csv(path, index_col=0, parse_dates=True)
        data.index.name = "timestamp"
        return data

    def write(
        self,
        provider: str,
        symbol: str,
        interval: str,
        data: pd.DataFrame,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Path:
        path = self.path_for(provider, symbol, interval, start, end)
        path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(path)
        return path

    def path_for(
        self,
        provider: str,
        symbol: str,
        interval: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Path:
        safe_key = "__".join(
            _safe(part)
            for part in [
                provider,
                symbol,
                interval,
                start or "none",
                end or "none",
            ]
        )
        return Path(self.root) / f"{safe_key}.csv"


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
