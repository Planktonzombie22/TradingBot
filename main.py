import argparse
from typing import Optional

from src.app import TradingApplication
from src.config import load_runtime_config
from src.engine import EngineEvent
from src.engine import EngineState
from src.reporting import format_backtest_summary, plot_backtest, write_backtest_html_report, write_backtest_report
from src.storage import JsonlStore
from src.utils.logger import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradingBot MVP runner")
    parser.add_argument("mode", nargs="?", choices=["backtest", "stream", "paper", "report"], default="backtest")
    parser.add_argument("--provider", default="sample", choices=["sample", "yfinance", "alpaca"])
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--strategy", default="buyHold")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--output", help="Optional path for a JSON backtest report.")
    parser.add_argument("--html-output", default="reports/backtest.html", help="Path for an HTML report in report mode.")
    parser.add_argument("--store-dir", default="runs", help="Directory for JSONL run artifacts.")
    parser.add_argument("--execution-mode", choices=["dry-run", "paper"], help="Broker execution mode. Defaults to EXECUTION_MODE or dry-run.")
    return parser


def build_config(args: argparse.Namespace):
    return load_runtime_config(
        {
            "symbol": args.symbol,
            "provider": args.provider,
            "period": args.period,
            "interval": args.interval,
            "strategy": args.strategy,
            "execution_mode": getattr(args, "execution_mode", None),
        }
    )


def run_backtest_app(
    app: TradingApplication,
    show_plot: bool = False,
    output: Optional[str] = None,
    store_dir: str = "runs",
) -> None:
    data = app.load_data()
    strategy = app.create_strategy()
    result = app.run_backtest(data, strategy)
    print(format_backtest_summary(result))
    store = JsonlStore(store_dir)
    store.write_many("equity", [{"timestamp": str(index), "equity": value} for index, value in result.equity.items()])
    store.write_many("fills", [{"order_id": fill.order.id, "symbol": fill.order.symbol, "side": fill.order.side, "quantity": fill.quantity, "price": fill.price} for fill in result.fills])
    if output:
        destination = write_backtest_report(result, output)
        print(f"Report written: {destination}")
    if show_plot:
        try:
            plot_backtest(data, strategy, result)
        except ValueError as exc:
            print(f"Plot skipped: {exc}")


def run_stream_app(app: TradingApplication, store_dir: str = "runs", label: str = "Stream") -> None:
    engine = app.create_engine()
    event_count = 0
    store = JsonlStore(store_dir)

    def print_event(event: EngineEvent) -> None:
        nonlocal event_count
        event_count += 1
        store.append("engine-events", {"type": event.event_type.value, "message": event.message, "payload": event.payload, "timestamp": event.timestamp})
        if event.event_type.value == "SIGNAL" and event.payload.get("action") == "HOLD":
            return
        if event.event_type.value in {"STARTED", "STOPPED", "SIGNAL", "ORDER", "FILL", "ERROR"}:
            print(f"{event.event_type.value}: {event.message} {event.payload}")

    engine.add_handler(print_event)
    try:
        engine.start()
    except KeyboardInterrupt:
        print("Stream interrupted by user.")
    finally:
        if engine.state != EngineState.STOPPED:
            engine.stop()
    print(f"{label} run complete. Engine events: {event_count}")


def run_report_app(app: TradingApplication, html_output: str) -> None:
    data = app.load_data()
    strategy = app.create_strategy()
    result = app.run_backtest(data, strategy)
    destination = write_backtest_html_report(result, html_output)
    print(format_backtest_summary(result))
    print(f"HTML report written: {destination}")


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    app = TradingApplication(build_config(args))
    if args.mode == "stream":
        run_stream_app(app, store_dir=args.store_dir, label="Stream")
    elif args.mode == "paper":
        run_stream_app(app, store_dir=args.store_dir, label="Paper")
    elif args.mode == "report":
        run_report_app(app, args.html_output)
    else:
        run_backtest_app(app, show_plot=args.plot, output=args.output, store_dir=args.store_dir)


if __name__ == "__main__":
    main()
