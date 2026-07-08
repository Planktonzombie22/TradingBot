import pandas as pd

from src.backtesting import BacktestConfig, run_backtest
from src.data import sample_ohlcv
from src.models import Signal
from src.strategies import get_strategy, list_strategies, strategy_schema
from src.strategies.base import Strategy
from src.strategies.buy_hold import BuyAndHoldStrategy


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


class StopOnlyStrategy(Strategy):
    def generate_signals(self, df):
        signals = []
        for index, timestamp in enumerate(df.index):
            if index == 0:
                signals.append(Signal("BUY", self.symbol, timestamp, stop_loss=95.0))
            else:
                signals.append(Signal.hold(self.symbol, timestamp))
        return pd.Series(signals, index=df.index, dtype=object)


class ShortThenCloseStrategy(Strategy):
    def generate_signals(self, df):
        signals = []
        for index, timestamp in enumerate(df.index):
            if index == 0:
                signals.append(Signal("SELL", self.symbol, timestamp, stop_loss=110.0))
            elif index == 2:
                signals.append(Signal("CLOSE", self.symbol, timestamp))
            else:
                signals.append(Signal.hold(self.symbol, timestamp))
        return pd.Series(signals, index=df.index, dtype=object)


class ShortStopOnlyStrategy(Strategy):
    def generate_signals(self, df):
        signals = []
        for index, timestamp in enumerate(df.index):
            if index == 0:
                signals.append(Signal("SELL", self.symbol, timestamp, stop_loss=110.0))
            else:
                signals.append(Signal.hold(self.symbol, timestamp))
        return pd.Series(signals, index=df.index, dtype=object)


def test_strategy_registry_exposes_tuff_system():
    assert get_strategy("tuffSystem").__name__ == "TuffSystem"


def test_research_systems_are_registered_and_emit_signals():
    data = sample_ohlcv(periods=160)

    for name in [
        "aroonVortexTrend",
        "choppinessRange",
        "fvgRebalance",
        "ichimokuCloudTrend",
        "liquiditySweepReversal",
        "momentumRegime",
        "meanReversion",
        "publishedSmaCross",
        "volatilityBreakout",
        "trendPullback",
        "volumeMomentum",
        "squeezeExpansion",
        "gapFade",
        "skewReversion",
        "structureBreakoutRetest",
        "tuffConsensus",
        "tuffRegimeSwitch",
        "tuffContrarian",
        "vwapValueReversion",
    ]:
        strategy_cls = get_strategy(name)
        strategy = strategy_cls("SPY")
        signals = strategy.generate_signals(data)

        assert name in list_strategies()
        assert len(signals) == len(data)
        assert {"BUY", "SELL", "CLOSE", "HOLD"}.issuperset({signal.action for signal in signals})
        assert strategy_schema(name)["parameters"]


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


def test_backtest_engine_executes_signal_stop_loss():
    index = pd.date_range("2024-01-01", periods=3)
    data = pd.DataFrame(
        {
            "Open": [100, 100, 94],
            "High": [101, 101, 96],
            "Low": [99, 90, 93],
            "Close": [100, 94, 94],
            "Volume": [1000] * 3,
        },
        index=index,
    )

    result = run_backtest(StopOnlyStrategy("SPY"), data, BacktestConfig(force_flat_at_end=False))

    assert len(result.fills) == 2
    assert result.fills[1].order.order_type == "STOP"
    assert result.fills[1].price == 95.0
    assert result.account_history[-1].positions == {}
    assert round(result.total_pnl, 2) == -500.0


def test_buy_hold_uses_target_notional_without_default_stop_loss():
    index = pd.date_range("2024-01-01", periods=3)
    data = pd.DataFrame(
        {
            "Open": [100, 100, 120],
            "High": [101, 121, 121],
            "Low": [99, 90, 119],
            "Close": [100, 120, 120],
            "Volume": [1000] * 3,
        },
        index=index,
    )

    result = run_backtest(BuyAndHoldStrategy("SPY"), data, BacktestConfig(force_flat_at_end=False))

    assert len(result.fills) == 1
    assert result.fills[0].order.stop_price is None
    assert round(result.fills[0].notional, 2) == 10_000.0
    assert round(result.total_pnl, 2) == 2_000.0


def test_backtest_engine_accounts_for_profitable_short_round_trip():
    index = pd.date_range("2024-01-01", periods=3)
    data = pd.DataFrame(
        {
            "Open": [100, 95, 90],
            "High": [101, 96, 91],
            "Low": [99, 94, 89],
            "Close": [100, 95, 90],
            "Volume": [1000] * 3,
        },
        index=index,
    )

    result = run_backtest(ShortThenCloseStrategy("SPY"), data)

    assert len(result.fills) == 2
    assert result.fills[0].order.side == "SELL"
    assert result.fills[1].order.side == "BUY"
    assert round(result.total_pnl, 2) == 500.0
    assert round(result.total_pnl_pct, 4) == 0.05


def test_backtest_engine_executes_short_stop_loss():
    index = pd.date_range("2024-01-01", periods=3)
    data = pd.DataFrame(
        {
            "Open": [100, 108, 110],
            "High": [101, 111, 112],
            "Low": [99, 107, 109],
            "Close": [100, 109, 110],
            "Volume": [1000] * 3,
        },
        index=index,
    )

    result = run_backtest(ShortStopOnlyStrategy("SPY"), data, BacktestConfig(force_flat_at_end=False))

    assert len(result.fills) == 2
    assert result.fills[1].order.order_type == "STOP"
    assert result.fills[1].price == 110.0
    assert result.account_history[-1].positions == {}
    assert round(result.total_pnl, 2) == -500.0


def test_backtest_engine_rejects_short_entry_when_shorting_disabled():
    index = pd.date_range("2024-01-01", periods=3)
    data = pd.DataFrame(
        {
            "Open": [100, 95, 90],
            "High": [101, 96, 91],
            "Low": [99, 94, 89],
            "Close": [100, 95, 90],
            "Volume": [1000] * 3,
        },
        index=index,
    )

    result = run_backtest(
        ShortStopOnlyStrategy("SPY"),
        data,
        BacktestConfig(allow_shorting=False, force_flat_at_end=False),
    )

    assert len(result.fills) == 0
    assert len(result.rejections) == 1
    assert round(result.total_pnl, 2) == 0.0


def test_published_sma_cross_uses_target_position_fraction_for_reversals():
    index = pd.date_range("2024-01-01", periods=12)
    closes = [12, 11, 10, 9, 10, 11, 12, 13, 12, 11, 10, 9]
    data = pd.DataFrame(
        {
            "Open": closes,
            "High": [close + 1 for close in closes],
            "Low": [close - 1 for close in closes],
            "Close": closes,
            "Volume": [1000] * len(closes),
        },
        index=index,
    )

    result = run_backtest(
        get_strategy("publishedSmaCross")("SPY", fast_period=2, slow_period=3, signal_delay_bars=1),
        data,
        BacktestConfig(force_flat_at_end=False),
    )

    assert len(result.fills) >= 3
    assert any(fill.order.side == "BUY" for fill in result.fills)
    assert any(fill.order.side == "SELL" for fill in result.fills)
    assert result.account_history[-1].positions["SPY"] < 0
