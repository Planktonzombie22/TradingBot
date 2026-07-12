from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Optional, Union

import pandas as pd


@dataclass(frozen=True)
class HistoricalDataCache:
    """Simple CSV cache for hydrated historical OHLCV data."""

    root: Union[str, Path]
    storage_format: str = "csv"

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
        if self.storage_format == "parquet":
            _require_parquet_support()
            data = pd.read_parquet(path, engine="pyarrow")
        else:
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
        if self.storage_format == "parquet":
            _require_parquet_support()
            data.to_parquet(path, engine="pyarrow", compression="snappy")
        else:
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
        suffix = ".parquet" if self.storage_format == "parquet" else ".csv"
        return Path(self.root) / f"{safe_key}{suffix}"


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)


def _require_parquet_support() -> None:
    if find_spec("pyarrow") is None:
        raise RuntimeError("Parquet cache support requires the research dependency profile: pip install -r requirements/research.txt")
