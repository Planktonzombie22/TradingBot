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
        "cryptoAdaptiveTrend",
        "fvgRebalance",
        "ichimokuCloudTrend",
        "liquiditySweepReversal",
        "managedFuturesMomentum",
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


def test_managed_futures_momentum_emits_volatility_targeted_entries_with_stops():
    index = pd.date_range("2024-01-01", periods=90)
    closes = [100 + offset for offset in range(90)]
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
    strategy = get_strategy("managedFuturesMomentum")(
        "SPY",
        short_lookback=5,
        medium_lookback=10,
        long_lookback=20,
        macro_lookback=30,
        volatility_lookback=10,
        atr_period=5,
    )

    signals = strategy.generate_signals(data)
    buy_signals = [signal for signal in signals if signal.action == "BUY"]
    result = run_backtest(strategy, data, BacktestConfig(force_flat_at_end=False))

    assert buy_signals
    assert 0 < buy_signals[0].meta["target_position_fraction"] <= 1.0
    assert buy_signals[0].stop_loss is not None
    assert buy_signals[0].meta["rebalance_reason"] == "trend_entry"
    assert any(fill.order.side == "BUY" and fill.order.stop_price is not None for fill in result.fills)


def test_managed_futures_momentum_can_reverse_after_trend_flip():
    index = pd.date_range("2024-01-01", periods=140)
    closes = list(range(100, 170)) + list(range(170, 100, -1))
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
    strategy = get_strategy("managedFuturesMomentum")(
        "SPY",
        short_lookback=5,
        medium_lookback=10,
        long_lookback=20,
        macro_lookback=30,
        volatility_lookback=10,
        atr_period=5,
        min_signal_strength=0.2,
        exit_threshold=0.0,
    )

    signals = strategy.generate_signals(data)

    assert any(signal.action == "BUY" for signal in signals)
    assert any(signal.action == "SELL" for signal in signals)


def test_crypto_adaptive_trend_emits_volatility_targeted_long_with_trailing_stop():
    index = pd.date_range("2024-01-01", periods=140)
    closes = [100 * (1.01**offset) for offset in range(140)]
    data = pd.DataFrame(
        {
            "Open": closes,
            "High": [close * 1.01 for close in closes],
            "Low": [close * 0.99 for close in closes],
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=index,
    )
    strategy = get_strategy("cryptoAdaptiveTrend")(
        "BTC-USD",
        fast_ema=5,
        slow_ema=15,
        momentum_lookback=10,
        sharpe_lookback=10,
        volatility_lookback=10,
        drawdown_lookback=30,
        atr_period=5,
        min_trend_score=0.05,
        min_rolling_sharpe=0.0,
        max_long_fraction=0.75,
    )

    signals = strategy.generate_signals(data)
    buy_signals = [signal for signal in signals if signal.action == "BUY"]
    result = run_backtest(strategy, data, BacktestConfig(force_flat_at_end=False))

    assert buy_signals
    assert 0 < buy_signals[0].meta["target_position_fraction"] <= 0.75
    assert buy_signals[0].meta["rolling_sharpe"] > 0
    assert buy_signals[0].meta["trailing_stop"] is not None
    assert any(fill.order.side == "BUY" for fill in result.fills)


def test_crypto_adaptive_trend_caps_short_exposure_in_bearish_crypto_tape():
    index = pd.date_range("2024-01-01", periods=140)
    closes = [300 * (0.99**offset) for offset in range(140)]
    data = pd.DataFrame(
        {
            "Open": closes,
            "High": [close * 1.01 for close in closes],
            "Low": [close * 0.99 for close in closes],
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=index,
    )
    strategy = get_strategy("cryptoAdaptiveTrend")(
        "ETH-USD",
        fast_ema=5,
        slow_ema=15,
        momentum_lookback=10,
        sharpe_lookback=10,
        volatility_lookback=10,
        drawdown_lookback=30,
        atr_period=5,
        min_trend_score=0.05,
        min_rolling_sharpe=0.0,
        max_short_fraction=0.25,
        allow_short=True,
    )

    signals = strategy.generate_signals(data)
    sell_signals = [signal for signal in signals if signal.action == "SELL"]

    assert sell_signals
    assert -0.25 <= sell_signals[0].meta["target_position_fraction"] < 0
    assert sell_signals[0].meta["rolling_sharpe"] < 0
