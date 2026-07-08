import argparse
import json
from pathlib import Path
from typing import Optional

from src.app import TradingApplication
from src.backtesting import (
    BacktestConfig,
    StrategySelectionPolicy,
    benchmark_relative_report,
    grid_search,
    load_research_matrix,
    run_bulk_backtests,
    run_research_matrix,
)
from src.config import load_runtime_config
from src.engine import EngineEvent
from src.engine import EngineState
from src.engine import TradingEngine
from src.reporting import format_backtest_summary, plot_backtest, write_backtest_html_report, write_backtest_report
from src.storage import JsonlStore
from src.utils.logger import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradingBot MVP runner")
    parser.add_argument("mode", nargs="?", choices=["backtest", "stream", "paper", "report", "optimize", "bulk", "matrix"], default="backtest")
    parser.add_argument("--provider", default="sample", choices=["sample", "yfinance", "alpaca"])
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--symbols", help="Comma-separated symbol list for bulk mode.")
    parser.add_argument("--symbols-file", help="JSON or text watchlist file for bulk mode.")
    parser.add_argument("--max-symbols", type=int, default=100, help="Maximum symbols to run in bulk mode.")
    parser.add_argument("--strategy", default="buyHold")
    parser.add_argument("--strategies", help="Comma-separated strategy list for bulk mode. Defaults to --strategy.")
    parser.add_argument("--strategy-params", default="{}", help="JSON object of strategy constructor parameters.")
    parser.add_argument("--strategy-params-file", help="Path to a JSON strategy parameter file.")
    parser.add_argument("--strategy-param-dir", default="configs/strategies", help="Directory for bulk strategy parameter JSON files.")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--start", help="Optional historical start timestamp/date, for example 2024-01-01T00:00:00Z.")
    parser.add_argument("--end", help="Optional historical end timestamp/date, for example 2024-12-31T00:00:00Z.")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--output", help="Optional path for a JSON backtest report.")
    parser.add_argument("--html-output", default="reports/backtest.html", help="Path for an HTML report in report mode.")
    parser.add_argument("--store-dir", default="runs", help="Directory for JSONL run artifacts.")
    parser.add_argument("--execution-mode", choices=["dry-run", "paper"], help="Broker execution mode. Defaults to EXECUTION_MODE or dry-run.")
    parser.add_argument("--flatten-on-stop", action="store_true", help="Submit flattening orders before stopping a stream/paper run.")
    parser.add_argument("--param-grid", default="{}", help="JSON object of strategy parameter lists for optimize mode.")
    parser.add_argument("--param-grid-file", help="Path to a JSON parameter grid file for optimize mode.")
    parser.add_argument("--metric", default="total_return", help="Metric to optimize.")
    parser.add_argument("--bulk-output", default="reports/bulk-backtest-summary.json", help="Path for a bulk backtest summary JSON report.")
    parser.add_argument("--benchmark-strategy", default="buyHold", help="Benchmark strategy for benchmark-relative bulk reports.")
    parser.add_argument("--benchmark-output", help="Optional path for a benchmark-relative bulk research report.")
    parser.add_argument("--research-matrix-file", default="configs/research/cross_asset_matrix.json", help="JSON research matrix for matrix mode.")
    parser.add_argument("--matrix-output", default="reports/research-matrix-summary.json", help="Path for matrix-mode JSON summary output.")
    return parser


def load_json_options(raw: str = "{}", path: Optional[str] = None) -> dict:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.loads(raw)


def build_config(args: argparse.Namespace):
    return load_runtime_config(
        {
            "symbol": args.symbol,
            "provider": args.provider,
            "period": args.period,
            "interval": args.interval,
            "start": getattr(args, "start", None),
            "end": getattr(args, "end", None),
            "strategy": args.strategy,
            "strategy_params": load_json_options(
                getattr(args, "strategy_params", "{}"),
                getattr(args, "strategy_params_file", None),
            ),
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


def run_stream_app(app: TradingApplication, store_dir: str = "runs", label: str = "Stream", flatten_on_stop: bool = False) -> TradingEngine:
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
        if flatten_on_stop and engine.state in {EngineState.RUNNING, EngineState.PAUSED}:
            engine.flatten_positions()
        if engine.state != EngineState.STOPPED:
            engine.stop()
    print(f"{label} run complete. Engine events: {event_count}")
    return engine


def run_report_app(app: TradingApplication, html_output: str) -> None:
    data = app.load_data()
    strategy = app.create_strategy()
    result = app.run_backtest(data, strategy)
    destination = write_backtest_html_report(result, html_output)
    print(format_backtest_summary(result))
    print(f"HTML report written: {destination}")


def run_optimize_app(app: TradingApplication, param_grid: str, metric: str, store_dir: str = "runs", param_grid_file: Optional[str] = None) -> None:
    data = app.load_data()
    grid = load_json_options(param_grid, param_grid_file)
    results = grid_search(
        strategy_name=app.config.strategy.name,
        symbol=app.config.data.symbol,
        data=data,
        param_grid=grid,
        metric=metric,
    )
    store = JsonlStore(store_dir)
    store.write_many(
        "optimization-results",
        [
            {
                "rank": index + 1,
                "strategy": result.strategy_name,
                "params": result.params,
                "score": result.score,
                "rank_metrics": result.rank_metrics(),
            }
            for index, result in enumerate(results)
        ],
    )
    if results:
        best = results[0]
        print(f"Best params: {best.params} score={best.score:.6f}")
    print(f"Optimization runs: {len(results)}")


def load_symbol_list(symbols: Optional[str] = None, symbols_file: Optional[str] = None, fallback: str = "SPY", max_symbols: int = 100) -> list[str]:
    values = []
    if symbols:
        values.extend(symbols.split(","))
    if symbols_file:
        path = Path(symbols_file)
        text = path.read_text(encoding="utf-8").strip()
        if text:
            if path.suffix.lower() == ".json":
                payload = json.loads(text)
                values.extend(payload.get("symbols", []) if isinstance(payload, dict) else payload)
            else:
                for line in text.splitlines():
                    values.extend(line.split(","))
    if not values:
        values = [fallback]

    normalized = []
    seen = set()
    for value in values:
        symbol = str(value).strip().upper()
        if not symbol or symbol in seen:
            continue
        normalized.append(symbol)
        seen.add(symbol)
        if len(normalized) >= max_symbols:
            break
    return normalized


def load_bulk_strategy_params(strategies: list[str], strategy_param_dir: str, explicit_params: Optional[dict] = None) -> dict[str, dict]:
    params_by_strategy = {}
    directory = Path(strategy_param_dir)
    for strategy in strategies:
        candidates = [
            directory / f"{strategy}_cross_market_candidate.json",
            directory / f"{strategy}_default.json",
            directory / f"{_camel_to_snake(strategy)}_cross_market_candidate.json",
            directory / f"{_camel_to_snake(strategy)}_default.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                params_by_strategy[strategy] = load_json_options(path=str(candidate))
                break
        else:
            params_by_strategy[strategy] = {}
    if explicit_params and len(strategies) == 1:
        params_by_strategy[strategies[0]] = explicit_params
    return params_by_strategy


def run_bulk_backtest_app(args: argparse.Namespace) -> None:
    symbols = load_symbol_list(args.symbols, args.symbols_file, fallback=args.symbol, max_symbols=args.max_symbols)
    strategies = [value.strip() for value in (args.strategies or args.strategy).split(",") if value.strip()]
    explicit_params = load_json_options(getattr(args, "strategy_params", "{}"), getattr(args, "strategy_params_file", None))
    params_by_strategy = load_bulk_strategy_params(strategies, args.strategy_param_dir, explicit_params=explicit_params)

    def load_symbol_data(symbol: str):
        config = load_runtime_config(
            {
                "symbol": symbol,
                "provider": args.provider,
                "period": args.period,
                "interval": args.interval,
                "start": args.start,
                "end": args.end,
            }
        )
        return TradingApplication(config).load_data()

    store = JsonlStore(args.store_dir)
    report = run_bulk_backtests(
        symbols=symbols,
        strategies=strategies,
        data_loader=load_symbol_data,
        strategy_params=params_by_strategy,
        config=BacktestConfig(),
        store=store,
    )

    output = Path(args.bulk_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Bulk backtest complete. Symbols: {len(symbols)} Strategies: {len(strategies)} Completed: {report.completed} Failed: {report.failed}")
    print(f"Bulk summary written: {output}")
    if args.benchmark_output:
        benchmark_report = benchmark_relative_report(
            report.records,
            StrategySelectionPolicy(benchmark_strategy=args.benchmark_strategy),
        )
        benchmark_output = Path(args.benchmark_output)
        benchmark_output.parent.mkdir(parents=True, exist_ok=True)
        benchmark_output.write_text(json.dumps(benchmark_report.to_dict(), indent=2), encoding="utf-8")
        print(f"Benchmark-relative report written: {benchmark_output}")
        for row in benchmark_report.strategy_summary()[:5]:
            print(
                f"{row.strategy} vs {args.benchmark_strategy}: "
                f"avg_excess={row.average_excess_return:.2%} select_rate={row.select_rate:.2%} "
                f"avg_dd_improvement={row.average_drawdown_improvement:.2%}"
            )
    for row in report.strategy_summary():
        print(
            f"{row['strategy']}: markets={row['markets']} "
            f"avg_return={row['average_return']:.2%} median={row['median_return']:.2%} "
            f"win_rate={row['win_rate']:.2%} avg_drawdown={row['average_max_drawdown']:.2%}"
        )


def run_research_matrix_app(args: argparse.Namespace) -> None:
    matrix = load_research_matrix(args.research_matrix_file)
    strategies = [value.strip() for value in (args.strategies or args.strategy).split(",") if value.strip()]
    explicit_params = load_json_options(getattr(args, "strategy_params", "{}"), getattr(args, "strategy_params_file", None))
    params_by_strategy = load_bulk_strategy_params(strategies, args.strategy_param_dir, explicit_params=explicit_params)

    def data_loader_factory(job):
        def load_symbol_data(symbol: str):
            period = job.window.period if job.window.period else None if (job.window.start or job.window.end) else args.period
            config = load_runtime_config(
                {
                    "symbol": symbol,
                    "provider": job.provider,
                    "interval": job.interval,
                    "period": period,
                    "start": job.window.start,
                    "end": job.window.end,
                }
            )
            return TradingApplication(config).load_data()

        return load_symbol_data

    store = JsonlStore(args.store_dir)
    report = run_research_matrix(
        config=matrix,
        strategies=strategies,
        data_loader_factory=data_loader_factory,
        strategy_params=params_by_strategy,
        backtest_config=BacktestConfig(),
        store=store,
        max_symbols_per_group=args.max_symbols,
    )
    output = Path(args.matrix_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Research matrix complete. Jobs: {len(report.job_results)} Completed: {report.completed} Failed: {report.failed}")
    print(f"Research matrix summary written: {output}")
    for row in report.asset_class_summary():
        print(f"{row['asset_class']}: jobs={row['jobs']} completed={row['completed']} failed={row['failed']}")


def _camel_to_snake(value: str) -> str:
    output = []
    for char in value:
        if char.isupper() and output:
            output.append("_")
        output.append(char.lower())
    return "".join(output)


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    app = TradingApplication(build_config(args))
    if args.mode == "stream":
        run_stream_app(app, store_dir=args.store_dir, label="Stream", flatten_on_stop=args.flatten_on_stop)
    elif args.mode == "paper":
        run_stream_app(app, store_dir=args.store_dir, label="Paper", flatten_on_stop=args.flatten_on_stop)
    elif args.mode == "report":
        run_report_app(app, args.html_output)
    elif args.mode == "optimize":
        run_optimize_app(app, args.param_grid, args.metric, store_dir=args.store_dir, param_grid_file=args.param_grid_file)
    elif args.mode == "bulk":
        run_bulk_backtest_app(args)
    elif args.mode == "matrix":
        run_research_matrix_app(args)
    else:
        run_backtest_app(app, show_plot=args.plot, output=args.output, store_dir=args.store_dir)


if __name__ == "__main__":
    main()
