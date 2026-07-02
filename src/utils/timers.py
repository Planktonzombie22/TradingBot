from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Iterator


@dataclass(frozen=True)
class TimerResult:
    name: str
    elapsed_seconds: float


@contextmanager
def timer(name: str = "operation") -> Iterator[Callable[[], TimerResult]]:
    """Measure elapsed time while keeping logging/reporting optional."""

    start = perf_counter()
    result = {"elapsed": 0.0}
    try:
        yield lambda: TimerResult(name=name, elapsed_seconds=result["elapsed"])
    finally:
        result["elapsed"] = perf_counter() - start
