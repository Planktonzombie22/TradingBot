import json
import logging
from datetime import datetime

import pytest

from src.data.calendar import MarketSession, MarketSessionCalendar, MarketSessionPolicy
from src.data import YFinancePollingStream
from src.execution import PaperBroker
from src.models import Order
from src.risk import ExitOrderPolicy, StopLossPolicy, TrailingStop
from src.utils.logger import configure_logging
from src.utils.retry import RetryPolicy


def test_exit_policy_builds_stop_and_take_profit():
    policy = ExitOrderPolicy(StopLossPolicy(fixed_percent=0.05), take_profit_percent=0.10)

    plan = policy.from_entry("LONG", 100)

    assert plan.stop_loss == 95
    assert plan.take_profit == pytest.approx(110)


def test_trailing_stop_only_tightens():
    trailing = TrailingStop("LONG", trail_percent=0.10)

    assert trailing.update(100) == 90
    assert trailing.update(110) == 99
    assert trailing.update(105) == 99


def test_paper_broker_replaces_order():
    broker = PaperBroker(auto_fill_market_orders=False)
    submitted = broker.submit_order(Order("SPY", "BUY", 1, order_type="LIMIT", limit_price=100))

    replaced = broker.replace_order(submitted.id, Order("SPY", "BUY", 2, order_type="LIMIT", limit_price=99))

    assert replaced.id == submitted.id
    assert replaced.quantity == 2
    assert replaced.limit_price == 99


def test_market_session_calendar_regular_hours():
    calendar = MarketSessionCalendar()

    assert calendar.is_open_at(datetime.fromisoformat("2024-01-02T10:00:00-05:00"))
    assert not calendar.is_open_at(datetime.fromisoformat("2024-01-06T10:00:00-05:00"))
    assert not calendar.is_open_at(datetime.fromisoformat("2024-01-02T20:00:00-05:00"))


def test_market_session_calendar_extended_hours_and_policy():
    calendar = MarketSessionCalendar(holidays={"2024-01-01"}, early_closes={"2024-07-03": datetime.strptime("13:00", "%H:%M").time()})

    assert calendar.session_at(datetime.fromisoformat("2024-01-02T08:00:00-05:00")) == MarketSession.PRE_MARKET
    assert calendar.session_at(datetime.fromisoformat("2024-07-03T14:00:00-04:00")) == MarketSession.AFTER_HOURS
    assert calendar.session_at(datetime.fromisoformat("2024-01-01T10:00:00-05:00")) == MarketSession.CLOSED
    assert not calendar.is_tradable_at(datetime.fromisoformat("2024-01-02T08:00:00-05:00"))
    assert calendar.is_tradable_at(
        datetime.fromisoformat("2024-01-02T08:00:00-05:00"),
        MarketSessionPolicy(allow_pre_market=True),
    )


def test_json_rotating_logging_writes_file(tmp_path):
    log_path = tmp_path / "bot.log"

    configure_logging(json_logs=True, log_file=str(log_path), max_bytes=10_000, backup_count=1)
    logging.getLogger("test").info("structured")

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["message"] == "structured"
    assert payload["level"] == "INFO"


def test_retry_policy_retries_until_success():
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 2:
            raise RuntimeError("try again")
        return "ok"

    assert RetryPolicy(attempts=2, delay_seconds=0).run(flaky) == "ok"
    assert calls["count"] == 2


def test_yfinance_stream_export_survives_file_merge():
    stream = YFinancePollingStream()
    stream.subscribe_bars(["SPY"])

    assert stream.symbols == ["SPY"]
