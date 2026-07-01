import pandas as pd

from src.backtesting import run_backtest
from src.models import Signal
from src.strategies import get_strategy
from src.strategies.base import Strategy


class OneTradeStrategy(Strategy):
    def generate_signals(self, df):
        signals = []
        for index, timestamp in enumerate(df.index):
            if index == 1:
                signals.append(Signal("BUY", self.symbol, timestamp, stop_loss=9.0))
            elif index == 3:
                signals.append(Signal("CLOSE", self.symbol, timestamp))
            else:
                signals.append(Signal.hold(self.symbol, timestamp))
        return pd.Series(signals, index=df.index, dtype=object)


def test_strategy_registry_exposes_tuff_system():
    assert get_strategy("tuffSystem").__name__ == "TuffSystem"


def test_backtest_engine_keeps_compatibility_result_shape():
    index = pd.date_range("2024-01-01", periods=5)
    data = pd.DataFrame(
        {
            "Open": [10, 10, 11, 12, 12],
            "High": [10, 11, 12, 13, 13],
            "Low": [9, 9, 10, 11, 11],
            "Close": [10, 10, 11, 12, 12],
            "Volume": [1000] * 5,
        },
        index=index,
    )

    result = run_backtest(OneTradeStrategy("SPY"), data)

    assert len(result.trades) == 1
    assert len(result.fills) == 2
    assert "total_return" in result.metrics
    assert not result.trades_df.empty
