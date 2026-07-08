import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, Union

import pandas as pd


@dataclass(frozen=True)
class UniverseConfig:
    symbols: Sequence[str] = field(default_factory=tuple)
    watchlist_path: Optional[str] = None
    groups: Sequence[str] = field(default_factory=tuple)
    screen: Optional[str] = None


class UniverseLoader:
    """Load tradeable/research universes from config, files, broker assets, or screens."""

    def load(
        self,
        config: UniverseConfig,
        broker_assets: Optional[Iterable[Mapping[str, object]]] = None,
        screen_data: Optional[pd.DataFrame] = None,
    ) -> list[str]:
        symbols: list[str] = []
        symbols.extend(config.symbols)
        if config.watchlist_path:
            symbols.extend(self.from_file(config.watchlist_path, groups=config.groups))
        if broker_assets is not None:
            symbols.extend(self.from_broker_assets(broker_assets))
        if config.screen and screen_data is not None:
            symbols.extend(self.from_screen(config.screen, screen_data))
        return _dedupe_symbols(symbols)

    def from_file(self, path: Union[str, Path], groups: Sequence[str] = tuple()) -> list[str]:
        path = Path(path)
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        if path.suffix.lower() == ".json":
            payload = json.loads(text)
            if isinstance(payload, dict):
                if "symbols" in payload:
                    return _dedupe_symbols(payload.get("symbols", []))
                return _dedupe_symbols(_symbols_from_group_payload(payload, groups))
            return _dedupe_symbols(payload)
        parts = []
        for line in text.splitlines():
            parts.extend(line.split(","))
        return _dedupe_symbols(parts)

    def from_broker_assets(self, assets: Iterable[Mapping[str, object]]) -> list[str]:
        symbols = []
        for asset in assets:
            if asset.get("tradable", True) is False:
                continue
            symbol = asset.get("symbol")
            if symbol:
                symbols.append(str(symbol))
        return _dedupe_symbols(symbols)

    def from_screen(self, screen: str, data: pd.DataFrame, limit: int = 50) -> list[str]:
        if "symbol" not in data.columns:
            raise ValueError("Screen data must include a symbol column.")
        screen = screen.lower()
        if screen == "top_volume":
            if "Volume" not in data.columns:
                raise ValueError("top_volume screen requires a Volume column.")
            ranked = data.sort_values("Volume", ascending=False)
        elif screen == "top_close":
            if "Close" not in data.columns:
                raise ValueError("top_close screen requires a Close column.")
            ranked = data.sort_values("Close", ascending=False)
        else:
            raise ValueError(f"Unsupported universe screen: {screen}")
        return _dedupe_symbols(ranked["symbol"].head(limit).tolist())


def _symbols_from_group_payload(payload: Mapping[str, object], groups: Sequence[str]) -> list[object]:
    selected_groups = groups or tuple(payload.keys())
    symbols: list[object] = []
    for group in selected_groups:
        value = payload.get(group)
        if isinstance(value, dict):
            symbols.extend(value.get("symbols", []))
        elif isinstance(value, list):
            symbols.extend(value)
    return symbols


def _dedupe_symbols(symbols: Iterable[object]) -> list[str]:
    seen = set()
    normalized = []
    for symbol in symbols:
        value = str(symbol).strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized
