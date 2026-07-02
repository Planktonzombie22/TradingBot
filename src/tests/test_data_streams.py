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


def test_alpaca_stream_run_forever_uses_websocket(monkeypatch):
    sent = []

    class FakeSocket:
        def connect(self, url):
            self.url = url

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
