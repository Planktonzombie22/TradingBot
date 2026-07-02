from pathlib import Path
from typing import Union

from src.models import BacktestResult


def render_backtest_html(result: BacktestResult, title: str = "TradingBot Backtest Report") -> str:
    rows = "".join(
        f"<tr><td>{key}</td><td>{value}</td></tr>"
        for key, value in {
            "Total PnL": f"${result.total_pnl:,.2f}",
            "Total Return": f"{result.total_pnl_pct:.2%}",
            "Trades": len(result.trades),
            "Fills": len(result.fills),
            "Rejections": len(result.rejections),
            "Max Drawdown": f"{result.metrics.get('max_drawdown', 0.0):.2%}",
        }.items()
    )
    equity_rows = "".join(
        f"<tr><td>{timestamp}</td><td>{equity:,.2f}</td></tr>"
        for timestamp, equity in result.equity.tail(20).items()
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #17202a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0 28px; }}
    th, td {{ border: 1px solid #d5d8dc; padding: 8px 10px; text-align: left; }}
    th {{ background: #f4f6f7; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <h2>Summary</h2>
  <table><tbody>{rows}</tbody></table>
  <h2>Recent Equity Points</h2>
  <table><thead><tr><th>Timestamp</th><th>Equity</th></tr></thead><tbody>{equity_rows}</tbody></table>
</body>
</html>"""


def write_backtest_html_report(result: BacktestResult, path: Union[str, Path]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_backtest_html(result), encoding="utf-8")
    return destination
