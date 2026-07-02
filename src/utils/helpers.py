from typing import Optional


def env_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))
