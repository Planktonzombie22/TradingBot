import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from src.config import AlpacaConfig
from src.models import Bar

from .events import MarketDataEvent, MarketDataEventType
from .stream import MarketDataHandler, MarketDataStream


@dataclass
class AlpacaMarketDataStream(MarketDataStream):
    """Minimal Alpaca WebSocket adapter for live bar events."""

    config: AlpacaConfig
    handlers: list[MarketDataHandler] = field(default_factory=list)
    symbols: Sequence[str] = field(default_factory=list)
    running: bool = False
    _socket: Any = None

    def subscribe_bars(self, symbols: Sequence[str]) -> None:
        self.symbols = tuple(symbols)

    def add_handler(self, handler: MarketDataHandler) -> None:
        self.handlers.append(handler)

    def run_forever(self) -> None:
        self._validate_credentials()
        self.running = True
        try:
            import websocket
        except ImportError as exc:
            raise RuntimeError("Install websocket-client to use the Alpaca stream.") from exc

        self._socket = websocket.WebSocket()
        self._socket.connect(self.config.data_stream_url)
        self._socket.send(json.dumps(self.auth_message()))
        self._socket.send(json.dumps(self.subscription_message()))

        try:
            while self.running:
                raw = self._socket.recv()
                if raw:
                    self.handle_raw_message(raw)
        finally:
            self.stop()

    def stop(self) -> None:
        self.running = False
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def auth_message(self) -> Dict[str, str]:
        return {
            "action": "auth",
            "key": self.config.api_key,
            "secret": self.config.secret_key,
        }

    def subscription_message(self) -> Dict[str, Any]:
        return {"action": "subscribe", "bars": list(self.symbols)}

    def handle_raw_message(self, raw: str) -> None:
        payload = json.loads(raw)
        messages = payload if isinstance(payload, list) else [payload]
        for message in messages:
            event = self._parse_message(message)
            if event is None:
                continue
            for handler in self.handlers:
                handler(event)

    def _validate_credentials(self) -> None:
        if not self.config.api_key or not self.config.secret_key:
            raise ValueError("Alpaca API credentials are missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env.")

    @staticmethod
    def _parse_message(message: Dict[str, Any]) -> Optional[MarketDataEvent]:
        event_type = message.get("T")
        if event_type == "b":
            timestamp = _parse_timestamp(message.get("t"))
            symbol = message["S"]
            bar = Bar(
                timestamp=timestamp,
                open=float(message["o"]),
                high=float(message["h"]),
                low=float(message["l"]),
                close=float(message["c"]),
                volume=float(message.get("v", 0.0)),
            )
            return MarketDataEvent(
                event_type=MarketDataEventType.BAR,
                symbol=symbol,
                timestamp=timestamp,
                bar=bar,
                payload=message,
            )
        if event_type == "success":
            return MarketDataEvent(
                event_type=MarketDataEventType.HEARTBEAT,
                symbol="",
                timestamp=datetime.now(timezone.utc),
                payload=message,
            )
        if event_type == "error":
            return MarketDataEvent(
                event_type=MarketDataEventType.ERROR,
                symbol="",
                timestamp=datetime.now(timezone.utc),
                payload=message,
            )
        return None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)
