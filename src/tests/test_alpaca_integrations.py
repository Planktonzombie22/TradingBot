import json

from src.config import AlpacaConfig
from src.data.alpaca import AlpacaHistoricalDataFeed
from src.execution import AlpacaPaperBroker
from src.models import Order


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_alpaca_historical_feed_parses_bars(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse(
            {
                "bars": [
                    {
                        "t": "2024-01-01T14:30:00Z",
                        "o": 10,
                        "h": 11,
                        "l": 9,
                        "c": 10.5,
                        "v": 1000,
                    }
                ]
            }
        )

    monkeypatch.setattr("src.data.alpaca.urlopen", fake_urlopen)
    feed = AlpacaHistoricalDataFeed(AlpacaConfig(api_key="key", secret_key="secret"))

    data = feed.get_historical("SPY", interval="1d")

    assert list(data.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert data.iloc[0]["Close"] == 10.5


def test_alpaca_paper_broker_submits_order_and_records_report(monkeypatch):
    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        assert body["symbol"] == "SPY"
        return FakeResponse({"id": "broker-1", "status": "accepted"})

    monkeypatch.setattr("src.execution.alpaca_broker.urlopen", fake_urlopen)
    broker = AlpacaPaperBroker(AlpacaConfig(api_key="key", secret_key="secret"))

    submitted = broker.submit_order(Order(symbol="SPY", side="BUY", quantity=1))

    assert submitted.status == "PENDING"
    assert broker.reports[submitted.id].broker_order_id == "broker-1"
