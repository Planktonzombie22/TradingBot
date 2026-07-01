from dataclasses import dataclass
from typing import Dict

import pandas as pd


@dataclass(frozen=True)
class PerformanceAnalyzer:
    """Portfolio analytics that are independent of any specific simulator."""

    risk_free_rate: float = 0.0

    def summarize(self, equity: pd.Series) -> Dict[str, float]:
        if equity.empty:
            return {}

        returns = equity.pct_change().dropna()
        drawdown = equity / equity.cummax() - 1
        total_return = equity.iloc[-1] / equity.iloc[0] - 1 if equity.iloc[0] else 0.0
        volatility = returns.std() if not returns.empty else 0.0
        sharpe = 0.0
        if volatility and pd.notna(volatility):
            sharpe = (returns.mean() - self.risk_free_rate) / volatility

        return {
            "starting_equity": float(equity.iloc[0]),
            "ending_equity": float(equity.iloc[-1]),
            "total_return": float(total_return),
            "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
            "volatility": float(volatility) if pd.notna(volatility) else 0.0,
            "sharpe": float(sharpe) if pd.notna(sharpe) else 0.0,
        }
