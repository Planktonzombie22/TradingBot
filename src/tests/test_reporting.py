import json

from src.app import TradingApplication
from src.config import MarketDataConfig, RuntimeConfig, StrategyConfig
from src.reporting import write_backtest_report


def test_backtest_report_writes_json(tmp_path):
    app = TradingApplication(
        RuntimeConfig(
            data=MarketDataConfig(provider="sample", symbol="SPY"),
            strategy=StrategyConfig(name="buyHold"),
        )
    )
    result = app.run_backtest()

    path = write_backtest_report(result, tmp_path / "report.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["fills"]
    assert payload["trades"]
    assert payload["metrics"]["ending_equity"] > 0
