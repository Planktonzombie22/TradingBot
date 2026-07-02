import json
from pathlib import Path
from typing import Any, Dict, Union

from src.models import BacktestResult


def format_backtest_summary(result: BacktestResult) -> str:
    metrics = result.metrics or {}
    lines = [
        "Backtest complete",
        f"Starting equity: ${metrics.get('starting_equity', 0.0):,.2f}",
        f"Ending equity:   ${metrics.get('ending_equity', 0.0):,.2f}",
        f"Total PnL:       ${result.total_pnl:,.2f} ({result.total_pnl_pct:.2%})",
        f"Max drawdown:    {metrics.get('max_drawdown', 0.0):.2%}",
        f"Trades:          {len(result.trades)}",
        f"Fills:           {len(result.fills)}",
        f"Rejections:      {len(result.rejections)}",
    ]
    return "\n".join(lines)


def backtest_result_payload(result: BacktestResult) -> Dict[str, Any]:
    return {
        "total_pnl": result.total_pnl,
        "total_pnl_pct": result.total_pnl_pct,
        "metrics": result.metrics,
        "trades": result.trades_df.to_dict(orient="records"),
        "fills": [
            {
                "symbol": fill.order.symbol,
                "side": fill.order.side,
                "quantity": fill.quantity,
                "price": fill.price,
                "commission": fill.commission,
                "timestamp": fill.timestamp.isoformat() if hasattr(fill.timestamp, "isoformat") else str(fill.timestamp),
            }
            for fill in result.fills
        ],
        "rejections": [
            {
                "symbol": rejection.order.symbol,
                "side": rejection.order.side,
                "quantity": rejection.order.quantity,
                "reason": rejection.reason.value,
                "message": rejection.message,
                "timestamp": rejection.timestamp.isoformat()
                if hasattr(rejection.timestamp, "isoformat")
                else str(rejection.timestamp),
            }
            for rejection in result.rejections
        ],
    }


def write_backtest_report(result: BacktestResult, path: Union[str, Path]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(backtest_result_payload(result), indent=2, default=str), encoding="utf-8")
    return destination
