import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import sleep
from typing import Any, Dict, Optional, Sequence

from src.config import AlpacaConfig
from .events import MarketDataEvent, MarketDataEventType
from .stream import MarketDataHandler, MarketDataStream
from ..quality.normalization import normalize_bar


@dataclass
class StreamHealth:
    last_message_at: Optional[datetime] = None
    last_bar_at: Optional[datetime] = None
    reconnects: int = 0
    errors: int = 0

    def record_message(self, timestamp: Optional[datetime] = None) -> None:
        self.last_message_at = timestamp or datetime.now(timezone.utc)

    def record_bar(self, timestamp: Optional[datetime] = None) -> None:
        self.last_bar_at = timestamp or datetime.now(timezone.utc)

    def is_stale(self, max_age_seconds: float, now: Optional[datetime] = None) -> bool:
        if self.last_message_at is None:
            return True
        now = now or datetime.now(timezone.utc)
        return (now - self.last_message_at).total_seconds() > max_age_seconds


@dataclass
class AlpacaMarketDataStream(MarketDataStream):
    """Minimal Alpaca WebSocket adapter for live bar events."""

    config: AlpacaConfig
    reconnect_attempts: int = 3
    reconnect_delay_seconds: float = 0.25
    socket_timeout_seconds: float = 30.0
    stale_timeout_seconds: float = 60.0
    handlers: list[MarketDataHandler] = field(default_factory=list)
    symbols: Sequence[str] = field(default_factory=list)
    running: bool = False
    health: StreamHealth = field(default_factory=StreamHealth)
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

        try:
            attempts = 0
            while self.running:
                try:
                    self._connect_and_subscribe(websocket.WebSocket)
                    attempts = 0
                    while self.running:
                        raw = self._socket.recv()
                        if raw:
                            self.handle_raw_message(raw)
                except Exception:
                    self.health.errors += 1
                    self._close_socket()
                    if not self.running:
                        break
                    attempts += 1
                    self.health.reconnects += 1
                    if attempts > self.reconnect_attempts:
                        self.running = False
                        raise
                    if self.reconnect_delay_seconds > 0:
                        sleep(self.reconnect_delay_seconds)
        finally:
            self.stop()

    def stop(self) -> None:
        self.running = False
        self._close_socket()

    def is_stale(self) -> bool:
        return self.health.is_stale(self.stale_timeout_seconds)

    def _connect_and_subscribe(self, socket_factory) -> None:
        self._socket = socket_factory()
        if hasattr(self._socket, "settimeout"):
            self._socket.settimeout(self.socket_timeout_seconds)
        self._socket.connect(self.config.data_stream_url)
        self._socket.send(json.dumps(self.auth_message()))
        self._socket.send(json.dumps(self.subscription_message()))

    def _close_socket(self) -> None:
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
            now = datetime.now(timezone.utc)
            self.health.record_message(now)
            event = self._parse_message(message)
            if event is None:
                continue
            if event.event_type == MarketDataEventType.BAR:
                self.health.record_bar(now)
            for handler in self.handlers:
                handler(event)

    def _validate_credentials(self) -> None:
        if not self.config.api_key or not self.config.secret_key:
            raise ValueError("Alpaca API credentials are missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env.")

    @staticmethod
    def _parse_message(message: Dict[str, Any]) -> Optional[MarketDataEvent]:
        event_type = message.get("T")
        if event_type == "b":
            return normalize_bar(message["S"], message)
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
