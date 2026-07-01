from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

import pandas as pd

from src.models.trade import Trade


@dataclass
class BacktestResult:
    """Output of a historical simulation."""

    trades: List[Trade]
    equity: pd.Series
    money_available: pd.Series
    total_pnl: float
    total_pnl_pct: float
    fills: Sequence[Any] = field(default_factory=list)
    rejections: Sequence[Any] = field(default_factory=list)
    account_history: Sequence[Any] = field(default_factory=list)
    events: Sequence[Any] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    config: Any = None

    @property
    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = [
            {
                "Entry Date": t.entry_time,
                "Entry Price": t.entry_price,
                "Type": "Long" if t.side == "LONG" else "Short",
                "Shares": t.shares,
                "Entry Equity": t.entry_equity,
                "Exit Date": t.exit_time,
                "Exit Price": t.exit_price,
                "Exit Equity": t.exit_equity,
                "PnL": t.pnl,
            }
            for t in self.trades
        ]
        return pd.DataFrame(rows)
