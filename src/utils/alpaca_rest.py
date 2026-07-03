import json
from dataclasses import dataclass
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.config import AlpacaConfig
from src.utils.retry import RetryPolicy


@dataclass(frozen=True)
class AlpacaRequestError(RuntimeError):
    method: str
    url: str
    status_code: Optional[int]
    message: str

    def __str__(self) -> str:
        status = self.status_code if self.status_code is not None else "network"
        return f"Alpaca {self.method} {self.url} failed ({status}): {self.message}"


@dataclass(frozen=True)
class AlpacaRestClient:
    """Authenticated Alpaca REST client with retry and error classification."""

    config: AlpacaConfig
    retry_policy: RetryPolicy = RetryPolicy(attempts=3, delay_seconds=0.25, backoff=2.0, jitter_seconds=0.1)
    timeout_seconds: int = 30

    def request(self, method: str, url: str, payload: Optional[dict[str, Any]] = None) -> Any:
        self._validate_credentials()
        return self.retry_policy.run(lambda: self._send(method, url, payload))

    def _send(self, method: str, url: str, payload: Optional[dict[str, Any]]) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "APCA-API-KEY-ID": self.config.api_key,
                "APCA-API-SECRET-KEY": self.config.secret_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AlpacaRequestError(method, url, exc.code, _error_message(body)) from exc
        except URLError as exc:
            raise AlpacaRequestError(method, url, None, str(exc.reason)) from exc
        return json.loads(body) if body else {}

    def _validate_credentials(self) -> None:
        if not self.config.api_key or not self.config.secret_key:
            raise ValueError("Alpaca API credentials are missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env.")


def _error_message(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    return str(payload.get("message") or payload.get("error") or payload)
