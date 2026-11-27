import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PASSING_STATUSES = {"passed", "pass", "ok", "green", "ready", "clean", "approved"}
BLOCKING_STATUSES = {"failed", "fail", "blocked", "red", "halted", "stale", "missing", "rejected"}


def status_passed(value: Any) -> bool:
    return str(value).lower() in PASSING_STATUSES


def status_blocking(value: Any) -> bool:
    return str(value).lower() in BLOCKING_STATUSES


def utc_timestamp(value: str | datetime | None = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    return str(value)


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def write_json_payload(payload: Mapping[str, Any], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return destination


def write_text_payload(content: str, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination
