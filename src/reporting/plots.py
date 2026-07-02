# cspell:words DEMA figsize sharex xlabel ylabel zorder backtest
import matplotlib.pyplot as plt
import pandas as pd

from src.models import BacktestResult
from src.strategies.base import Strategy


def plot_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    result: BacktestResult,
) -> None:
    indicator_df = strategy.indicators
    if indicator_df.empty:
        raise ValueError("Strategy indicators are empty; call generate_signals(df) before plotting.")

    trades = result.trades_df
    equity = result.equity
    money_available = result.money_available

    fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, sharex=True, figsize=(14, 14))

    ax1.plot(df.index, df["Close"], label="Close Price", color="teal")
    ax1.plot(indicator_df.index, indicator_df["DEMA"], label="DEMA", color="orange")
    ax1.plot(
        indicator_df.index,
        indicator_df["SuperTrend"],
        label="SuperTrend",
        color="blue",
    )
    ax1.set_title("Price, DEMA and SuperTrend")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left")

    ax2.plot(indicator_df.index, indicator_df["RSI"], label="RSI", color="red")
    ax2.plot(indicator_df.index, indicator_df["ADX"], label="ADX", color="yellow")
    ax2.set_title("RSI and ADX")
    ax2.set_ylabel("Indicator")
    ax2.legend(loc="upper left")

    ax3.plot(equity.index, equity, label="Equity Curve", color="purple")
    ax3.set_title("Equity Curve")
    ax3.set_ylabel("Equity")
    ax3.set_xlabel("Date")
    ax3.legend(loc="upper left")

    ax4.plot(
        money_available.index,
        money_available,
        label="Money Available",
        color="pink",
    )
    ax4.set_title("Money Available")
    ax4.set_ylabel("Money")
    ax4.set_xlabel("Date")
    ax4.legend(loc="upper left")

    if not trades.empty:
        longs = trades[trades["Type"] == "Long"]
        shorts = trades[trades["Type"] == "Short"]

        if not longs.empty:
            ax1.scatter(
                longs["Entry Date"],
                longs["Entry Price"],
                marker="^",
                color="green",
                s=60,
                label="Long Entry",
                zorder=5,
            )
            ax1.scatter(
                longs["Exit Date"],
                longs["Exit Price"],
                marker="o",
                color="green",
                s=60,
                label="Long Exit",
                zorder=5,
            )
            ax2.scatter(
                longs["Entry Date"],
                indicator_df.loc[longs["Entry Date"], "RSI"],
                marker="^",
                color="green",
                s=60,
                zorder=5,
            )
            ax2.scatter(
                longs["Exit Date"],
                indicator_df.loc[longs["Exit Date"], "RSI"],
                marker="o",
                color="green",
                s=60,
                zorder=5,
            )
            ax3.scatter(
                longs["Entry Date"],
                longs["Entry Equity"],
                marker="^",
                color="green",
                s=60,
                zorder=5,
            )
            ax3.scatter(
                longs["Exit Date"],
                longs["Exit Equity"],
                marker="o",
                color="green",
                s=60,
                zorder=5,
            )
            ax4.scatter(
                longs["Entry Date"],
                money_available.loc[longs["Entry Date"]],
                marker="^",
                color="green",
                s=60,
                zorder=5,
            )
            ax4.scatter(
                longs["Exit Date"],
                money_available.loc[longs["Exit Date"]],
                marker="o",
                color="green",
                s=60,
                zorder=5,
            )

        if not shorts.empty:
            ax1.scatter(
                shorts["Entry Date"],
                shorts["Entry Price"],
                marker="v",
                color="red",
                s=60,
                label="Short Entry",
                zorder=5,
            )
            ax1.scatter(
                shorts["Exit Date"],
                shorts["Exit Price"],
                marker="o",
                color="red",
                s=60,
                label="Short Exit",
                zorder=5,
            )
            ax2.scatter(
                shorts["Entry Date"],
                indicator_df.loc[shorts["Entry Date"], "RSI"],
                marker="v",
                color="red",
                s=60,
                zorder=5,
            )
            ax2.scatter(
                shorts["Exit Date"],
                indicator_df.loc[shorts["Exit Date"], "RSI"],
                marker="o",
                color="red",
                s=60,
                zorder=5,
            )
            ax3.scatter(
                shorts["Entry Date"],
                shorts["Entry Equity"],
                marker="v",
                color="red",
                s=60,
                zorder=5,
            )
            ax3.scatter(
                shorts["Exit Date"],
                shorts["Exit Equity"],
                marker="o",
                color="red",
                s=60,
                zorder=5,
            )
            ax4.scatter(
                shorts["Entry Date"],
                money_available.loc[shorts["Entry Date"]],
                marker="v",
                color="red",
                s=60,
                zorder=5,
            )
            ax4.scatter(
                shorts["Exit Date"],
                money_available.loc[shorts["Exit Date"]],
                marker="o",
                color="red",
                s=60,
                zorder=5,
            )

        ax1.legend(loc="upper left")

    plt.tight_layout()
    plt.show()

    print(f"Total PnL: {result.total_pnl_pct:.2%}")
    print(f"Total PnL: ${result.total_pnl:.2f}")
