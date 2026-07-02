import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Union

from src.execution import BrokerAccountSnapshot, BrokerPositionSnapshot, BrokerSyncSnapshot, ExecutionReport
from src.models import Order


def _timestamp(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@dataclass(frozen=True)
class BrokerStateSnapshot:
    account: Optional[BrokerAccountSnapshot] = None
    positions: List[BrokerPositionSnapshot] = field(default_factory=list)
    orders: List[Order] = field(default_factory=list)
    reports: List[ExecutionReport] = field(default_factory=list)


class SQLiteStateStore:
    """Durable SQLite store for broker-facing state and restart recovery."""

    def __init__(self, path: Union[str, Path] = "runs/tradingbot.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_order(self, order: Order) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO orders (
                    id, client_order_id, symbol, side, quantity, order_type,
                    limit_price, stop_price, status, created_at, raw_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    client_order_id=excluded.client_order_id,
                    symbol=excluded.symbol,
                    side=excluded.side,
                    quantity=excluded.quantity,
                    order_type=excluded.order_type,
                    limit_price=excluded.limit_price,
                    stop_price=excluded.stop_price,
                    status=excluded.status,
                    raw_json=excluded.raw_json,
                    updated_at=excluded.updated_at
                """,
                (
                    order.id,
                    order.client_order_id,
                    order.symbol,
                    order.side,
                    order.quantity,
                    order.order_type,
                    order.limit_price,
                    order.stop_price,
                    order.status,
                    _timestamp(order.created_at),
                    json.dumps(order.__dict__, default=str),
                    _timestamp(datetime.now(timezone.utc)),
                ),
            )

    def save_execution_report(self, report: ExecutionReport) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO execution_reports (
                    order_id, status, broker_order_id, fill_id, filled_quantity,
                    average_fill_price, submitted_at, raw_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    status=excluded.status,
                    broker_order_id=excluded.broker_order_id,
                    fill_id=excluded.fill_id,
                    filled_quantity=excluded.filled_quantity,
                    average_fill_price=excluded.average_fill_price,
                    submitted_at=excluded.submitted_at,
                    raw_json=excluded.raw_json,
                    updated_at=excluded.updated_at
                """,
                (
                    report.order_id,
                    report.status,
                    report.broker_order_id,
                    report.fill_id,
                    report.filled_quantity,
                    report.average_fill_price,
                    _timestamp(report.submitted_at),
                    json.dumps(report.raw, default=str),
                    _timestamp(datetime.now(timezone.utc)),
                ),
            )

    def save_account_snapshot(self, snapshot: BrokerAccountSnapshot) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO account_snapshots (
                    captured_at, cash, buying_power, equity, daytrade_count,
                    pattern_day_trader, trading_blocked, account_blocked, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _timestamp(snapshot.captured_at),
                    snapshot.cash,
                    snapshot.buying_power,
                    snapshot.equity,
                    snapshot.daytrade_count,
                    int(snapshot.pattern_day_trader),
                    int(snapshot.trading_blocked),
                    int(snapshot.account_blocked),
                    json.dumps(snapshot.raw, default=str),
                ),
            )

    def save_position_snapshots(self, positions: Iterable[BrokerPositionSnapshot], captured_at: Optional[datetime] = None) -> None:
        captured_at = captured_at or datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute("DELETE FROM positions")
            connection.executemany(
                """
                INSERT INTO positions (
                    symbol, quantity, average_entry_price, market_value, raw_json, captured_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        position.symbol,
                        position.quantity,
                        position.average_entry_price,
                        position.market_value,
                        json.dumps(position.raw, default=str),
                        _timestamp(captured_at),
                    )
                    for position in positions
                ],
            )

    def save_sync_snapshot(self, snapshot: BrokerSyncSnapshot) -> None:
        self.save_account_snapshot(snapshot.account)
        self.save_position_snapshots(snapshot.positions, snapshot.captured_at)
        for order in snapshot.open_orders:
            self.save_order(order)
        for report in snapshot.reports:
            self.save_execution_report(report)

    def load_orders(self) -> List[Order]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, client_order_id, symbol, side, quantity, order_type,
                       limit_price, stop_price, status, created_at
                FROM orders
                ORDER BY created_at, id
                """
            ).fetchall()
        return [
            Order(
                id=row["id"],
                client_order_id=row["client_order_id"],
                symbol=row["symbol"],
                side=row["side"],
                quantity=row["quantity"],
                order_type=row["order_type"],
                limit_price=row["limit_price"],
                stop_price=row["stop_price"],
                status=row["status"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def load_execution_reports(self) -> List[ExecutionReport]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT order_id, status, broker_order_id, fill_id, filled_quantity,
                       average_fill_price, submitted_at, raw_json
                FROM execution_reports
                ORDER BY submitted_at, order_id
                """
            ).fetchall()
        return [
            ExecutionReport(
                order_id=row["order_id"],
                status=row["status"],
                broker_order_id=row["broker_order_id"],
                fill_id=row["fill_id"],
                filled_quantity=row["filled_quantity"],
                average_fill_price=row["average_fill_price"],
                submitted_at=datetime.fromisoformat(row["submitted_at"]),
                raw=json.loads(row["raw_json"] or "{}"),
            )
            for row in rows
        ]

    def load_latest_account_snapshot(self) -> Optional[BrokerAccountSnapshot]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT captured_at, cash, buying_power, equity, daytrade_count,
                       pattern_day_trader, trading_blocked, account_blocked, raw_json
                FROM account_snapshots
                ORDER BY captured_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return BrokerAccountSnapshot(
            cash=row["cash"],
            buying_power=row["buying_power"],
            equity=row["equity"],
            daytrade_count=row["daytrade_count"],
            pattern_day_trader=bool(row["pattern_day_trader"]),
            trading_blocked=bool(row["trading_blocked"]),
            account_blocked=bool(row["account_blocked"]),
            raw=json.loads(row["raw_json"] or "{}"),
            captured_at=datetime.fromisoformat(row["captured_at"]),
        )

    def load_positions(self) -> List[BrokerPositionSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, quantity, average_entry_price, market_value, raw_json
                FROM positions
                ORDER BY symbol
                """
            ).fetchall()
        return [
            BrokerPositionSnapshot(
                symbol=row["symbol"],
                quantity=row["quantity"],
                average_entry_price=row["average_entry_price"],
                market_value=row["market_value"],
                raw=json.loads(row["raw_json"] or "{}"),
            )
            for row in rows
        ]

    def load_broker_state(self) -> BrokerStateSnapshot:
        return BrokerStateSnapshot(
            account=self.load_latest_account_snapshot(),
            positions=self.load_positions(),
            orders=self.load_orders(),
            reports=self.load_execution_reports(),
        )

    def restore_paper_broker(self):
        """Rebuild a PaperBroker from persisted local orders and reports."""

        from src.execution import PaperBroker

        state = self.load_broker_state()
        broker = PaperBroker()
        broker.orders = {order.id: order for order in state.orders}
        broker.reports = {report.order_id: report for report in state.reports}
        broker._counter = len(broker.reports)
        return broker

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    client_order_id TEXT UNIQUE,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    order_type TEXT NOT NULL,
                    limit_price REAL,
                    stop_price REAL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_reports (
                    order_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    broker_order_id TEXT,
                    fill_id TEXT NOT NULL,
                    filled_quantity REAL NOT NULL,
                    average_fill_price REAL,
                    submitted_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS account_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at TEXT NOT NULL,
                    cash REAL NOT NULL,
                    buying_power REAL NOT NULL,
                    equity REAL NOT NULL,
                    daytrade_count INTEGER NOT NULL,
                    pattern_day_trader INTEGER NOT NULL,
                    trading_blocked INTEGER NOT NULL,
                    account_blocked INTEGER NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    quantity REAL NOT NULL,
                    average_entry_price REAL NOT NULL,
                    market_value REAL NOT NULL,
                    raw_json TEXT NOT NULL,
                    captured_at TEXT NOT NULL
                );
                """
            )
