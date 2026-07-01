from src.app import TradingApplication
from src.backtest import plot_backtest
from src.config import RuntimeConfig


def main() -> None:
    app = TradingApplication(RuntimeConfig())
    df = app.load_data()
    strategy = app.create_strategy()
    result = app.run_backtest(df, strategy)
    plot_backtest(df, strategy, result)


if __name__ == "__main__":
    main()
