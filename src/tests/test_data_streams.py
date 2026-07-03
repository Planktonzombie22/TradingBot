import sys
from types import SimpleNamespace

from src.config import AlpacaConfig
from src.data import AlpacaMarketDataStream, MarketDataEventType


def test_alpaca_stream_builds_auth_and_subscription_messages():
    stream = AlpacaMarketDataStream(AlpacaConfig(api_key="key", secret_key="secret"))
    stream.subscribe_bars(["SPY", "QQQ"])

    assert stream.auth_message()["action"] == "auth"
    assert stream.subscription_message() == {"action": "subscribe", "bars": ["SPY", "QQQ"]}


def test_alpaca_stream_parses_bar_messages():
    stream = AlpacaMarketDataStream(AlpacaConfig(api_key="key", secret_key="secret"))
    received = []
    stream.add_handler(received.append)

    stream.handle_raw_message(
        '[{"T":"b","S":"SPY","t":"2024-01-01T14:30:00Z","o":10,"h":11,"l":9,"c":10.5,"v":1000}]'
    )

    assert len(received) == 1
    assert received[0].event_type == MarketDataEventType.BAR
    assert received[0].bar.close == 10.5
    assert stream.health.last_message_at is not None
    assert stream.health.last_bar_at is not None
    assert not stream.is_stale()


def test_alpaca_stream_run_forever_uses_websocket(monkeypatch):
    sent = []

    class FakeSocket:
        def connect(self, url):
            self.url = url

        def settimeout(self, timeout):
            self.timeout = timeout

        def send(self, message):
            sent.append(message)

        def recv(self):
            return '[{"T":"b","S":"SPY","t":"2024-01-01T14:30:00Z","o":10,"h":11,"l":9,"c":10.5,"v":1000}]'

        def close(self):
            self.closed = True

    monkeypatch.setitem(sys.modules, "websocket", SimpleNamespace(WebSocket=FakeSocket))
    stream = AlpacaMarketDataStream(AlpacaConfig(api_key="key", secret_key="secret"))
    stream.subscribe_bars(["SPY"])
    received = []

    def stop_after_first(event):
        received.append(event)
        stream.stop()

    stream.add_handler(stop_after_first)
    stream.run_forever()

    assert len(sent) == 2
    assert received[0].event_type == MarketDataEventType.BAR


def test_alpaca_stream_reconnects_and_replays_subscription(monkeypatch):
    sent = []
    sockets = {"count": 0}

    class FakeSocket:
        def __init__(self):
            sockets["count"] += 1
            self.index = sockets["count"]

        def connect(self, url):
            self.url = url

        def settimeout(self, timeout):
            self.timeout = timeout

        def send(self, message):
            sent.append(message)

        def recv(self):
            if self.index == 1:
                raise RuntimeError("temporary disconnect")
            return '[{"T":"b","S":"SPY","t":"2024-01-01T14:30:00Z","o":10,"h":11,"l":9,"c":10.5,"v":1000}]'

        def close(self):
            self.closed = True

    monkeypatch.setitem(sys.modules, "websocket", SimpleNamespace(WebSocket=FakeSocket))
    stream = AlpacaMarketDataStream(
        AlpacaConfig(api_key="key", secret_key="secret"),
        reconnect_attempts=1,
        reconnect_delay_seconds=0,
    )
    stream.subscribe_bars(["SPY"])
    received = []

    def stop_after_first(event):
        received.append(event)
        stream.stop()

    stream.add_handler(stop_after_first)
    stream.run_forever()

    assert sockets["count"] == 2
    assert len(sent) == 4
    assert stream.health.reconnects == 1
    assert received[0].event_type == MarketDataEventType.BAR
