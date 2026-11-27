import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pandas as pd

from src.config import AlpacaConfig
from src.data import HistoricalDataCache
from src.data.alpaca import AlpacaHistoricalDataFeed
from src.execution import AlpacaPaperBroker
from src.models import Order
from src.utils.retry import RetryPolicy
from src.utils.alpaca_rest import AlpacaRequestError, AlpacaRestClient


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

    monkeypatch.setattr("src.utils.alpaca_rest.urlopen", fake_urlopen)
    feed = AlpacaHistoricalDataFeed(AlpacaConfig(api_key="key", secret_key="secret"))

    data = feed.get_historical("SPY", interval="1d")

    assert list(data.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert data.iloc[0]["Close"] == 10.5


def test_alpaca_historical_feed_follows_pagination():
    calls = []

    class FakeClient:
        def request(self, method, url, payload=None):
            calls.append(url)
            if "page_token=next" in url:
                return {
                    "bars": [
                        {
                            "t": "2024-01-02T14:30:00Z",
                            "o": 11,
                            "h": 12,
                            "l": 10,
                            "c": 11.5,
                            "v": 2000,
                        }
                    ]
                }
            return {
                "bars": [
                    {
                        "t": "2024-01-01T14:30:00Z",
                        "o": 10,
                        "h": 11,
                        "l": 9,
                        "c": 10.5,
                        "v": 1000,
                    }
                ],
                "next_page_token": "next",
            }

    feed = AlpacaHistoricalDataFeed(AlpacaConfig(api_key="key", secret_key="secret"))
    feed.client = FakeClient()

    data = feed.get_historical("SPY", interval="1d")

    assert len(calls) == 2
    assert all("adjustment=all" in url for url in calls)
    assert len(data) == 2
    assert data.iloc[-1]["Close"] == 11.5


def test_alpaca_historical_feed_translates_period_to_start_query():
    calls = []

    class FakeClient:
        def request(self, method, url, payload=None):
            calls.append(url)
            return {
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

    feed = AlpacaHistoricalDataFeed(AlpacaConfig(api_key="key", secret_key="secret"))
    feed.client = FakeClient()

    data = feed.get_historical("SPY", interval="1d", period="2y")

    query = parse_qs(urlparse(calls[0]).query)
    assert "start" in query
    assert query["timeframe"] == ["1Day"]
    assert len(data) == 1


def test_alpaca_historical_feed_handles_null_bars_payload():
    class FakeClient:
        def request(self, method, url, payload=None):
            return {"bars": None}

    feed = AlpacaHistoricalDataFeed(AlpacaConfig(api_key="key", secret_key="secret"))
    feed.client = FakeClient()

    data = feed.get_historical("SPY", interval="1d")

    assert data.empty
    assert list(data.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_alpaca_historical_feed_reads_from_cache_without_client_call(tmp_path):
    cache = HistoricalDataCache(tmp_path)
    source = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.0],
            "Close": [10.5],
            "Volume": [1000.0],
        },
        index=pd.to_datetime(["2024-01-02T05:00:00Z"]),
    )
    source.index.name = "timestamp"
    cache.write("alpaca-adjusted-all", "SPY", "1Day", source, "2024-01-02T00:00:00Z", "2024-01-06T00:00:00Z")

    class FailingClient:
        def request(self, method, url, payload=None):
            raise AssertionError("Client should not be called when cache is warm.")

    feed = AlpacaHistoricalDataFeed(AlpacaConfig(api_key="key", secret_key="secret"), cache=cache)
    feed.client = FailingClient()

    cached = feed.get_historical("SPY", start="2024-01-02T00:00:00Z", end="2024-01-06T00:00:00Z", interval="1d")

    assert len(cached) == len(source)
    assert list(cached.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_alpaca_paper_broker_submits_order_and_records_report(monkeypatch):
    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        assert body["symbol"] == "SPY"
        return FakeResponse({"id": "broker-1", "status": "accepted"})

    monkeypatch.setattr("src.utils.alpaca_rest.urlopen", fake_urlopen)
    broker = AlpacaPaperBroker(AlpacaConfig(api_key="key", secret_key="secret"))

    submitted = broker.submit_order(Order(symbol="SPY", side="BUY", quantity=1))

    assert submitted.status == "PENDING"
    assert broker.reports[submitted.id].broker_order_id == "broker-1"


def test_alpaca_paper_broker_polls_execution_reports_from_rest():
    calls = []

    class FakeClient:
        def request(self, method, url, payload=None):
            calls.append((method, url, payload))
            if method == "POST":
                return {"id": "broker-1", "status": "accepted"}
            if method == "GET":
                return {
                    "id": "broker-1",
                    "status": "filled",
                    "filled_qty": "1",
                    "filled_avg_price": "101.25",
                }
            return {}

    broker = AlpacaPaperBroker(AlpacaConfig(api_key="key", secret_key="secret"))
    broker.client = FakeClient()
    submitted = broker.submit_order(Order(symbol="SPY", side="BUY", quantity=1))

    reports = list(broker.poll_execution_reports([submitted]))

    assert reports[0].status == "FILLED"
    assert reports[0].broker_order_id == "broker-1"
    assert reports[0].filled_quantity == 1
    assert reports[0].average_fill_price == 101.25
    assert broker.orders[submitted.id].status == "FILLED"
    assert calls[-1][0] == "GET"


def test_alpaca_rest_client_classifies_http_errors(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            {},
            BytesIO(b'{"message":"rate limit exceeded"}'),
        )

    monkeypatch.setattr("src.utils.alpaca_rest.urlopen", fake_urlopen)
    client = AlpacaRestClient(
        AlpacaConfig(api_key="key", secret_key="secret"),
        retry_policy=RetryPolicy(attempts=1, delay_seconds=0),
    )

    try:
        client.request("GET", "https://data.alpaca.markets/v2/test")
    except AlpacaRequestError as exc:
        assert exc.status_code == 429
        assert "rate limit exceeded" in str(exc)
    else:
        raise AssertionError("Expected AlpacaRequestError")
