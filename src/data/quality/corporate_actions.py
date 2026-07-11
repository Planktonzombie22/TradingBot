from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Iterable, List, Optional

import pandas as pd


class PriceAdjustmentMode(str, Enum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"


@dataclass(frozen=True)
class SplitAction:
    symbol: str
    effective_date: date
    ratio: float


@dataclass(frozen=True)
class DividendAction:
    symbol: str
    ex_date: date
    amount: float


@dataclass(frozen=True)
class SymbolChangeAction:
    old_symbol: str
    new_symbol: str
    effective_date: date


@dataclass(frozen=True)
class CorporateActionSet:
    splits: List[SplitAction] = field(default_factory=list)
    dividends: List[DividendAction] = field(default_factory=list)
    symbol_changes: List[SymbolChangeAction] = field(default_factory=list)

    @classmethod
    def from_iterables(
        cls,
        splits: Optional[Iterable[SplitAction]] = None,
        dividends: Optional[Iterable[DividendAction]] = None,
        symbol_changes: Optional[Iterable[SymbolChangeAction]] = None,
    ) -> "CorporateActionSet":
        return cls(list(splits or []), list(dividends or []), list(symbol_changes or []))


@dataclass(frozen=True)
class CorporateActionPolicy:
    """Explicit historical price adjustment policy for research data."""

    mode: PriceAdjustmentMode = PriceAdjustmentMode.RAW

    def apply(self, symbol: str, data: pd.DataFrame, actions: CorporateActionSet) -> pd.DataFrame:
        adjusted = data.copy()
        if self.mode == PriceAdjustmentMode.RAW or adjusted.empty:
            return adjusted

        for split in sorted(actions.splits, key=lambda item: item.effective_date):
            if split.symbol != symbol or split.ratio <= 0:
                continue
            mask = adjusted.index.date < split.effective_date
            adjusted.loc[mask, ["Open", "High", "Low", "Close"]] = adjusted.loc[mask, ["Open", "High", "Low", "Close"]] / split.ratio
            if "Volume" in adjusted.columns:
                adjusted.loc[mask, "Volume"] = adjusted.loc[mask, "Volume"] * split.ratio

        if self.mode == PriceAdjustmentMode.TOTAL_RETURN:
            for dividend in sorted(actions.dividends, key=lambda item: item.ex_date):
                if dividend.symbol != symbol or dividend.amount <= 0:
                    continue
                mask = adjusted.index.date < dividend.ex_date
                reference = adjusted.loc[adjusted.index.date >= dividend.ex_date, "Close"]
                if reference.empty or reference.iloc[0] <= 0:
                    continue
                factor = max((reference.iloc[0] - dividend.amount) / reference.iloc[0], 0)
                adjusted.loc[mask, ["Open", "High", "Low", "Close"]] = adjusted.loc[mask, ["Open", "High", "Low", "Close"]] * factor

        return adjusted

    def resolve_symbol(self, symbol: str, as_of: date, actions: CorporateActionSet) -> str:
        resolved = symbol
        for change in sorted(actions.symbol_changes, key=lambda item: item.effective_date):
            if change.old_symbol == resolved and as_of >= change.effective_date:
                resolved = change.new_symbol
        return resolved
