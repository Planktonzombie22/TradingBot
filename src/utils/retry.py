from dataclasses import dataclass
from time import sleep
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    delay_seconds: float = 0.25
    backoff: float = 2.0

    def run(self, operation: Callable[[], T]) -> T:
        if self.attempts <= 0:
            raise ValueError("Retry attempts must be positive.")
        delay = self.delay_seconds
        last_error = None
        for attempt in range(self.attempts):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt == self.attempts - 1:
                    break
                if delay > 0:
                    sleep(delay)
                    delay *= self.backoff
        raise last_error
