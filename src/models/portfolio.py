from dataclasses import dataclass, field
from typing import Optional

from src.models.position import Position


@dataclass
class Portfolio:
    """Account snapshot at a point in time."""

    cash: float
    equity: float
    position: Optional[Position] = None
    available_margin: float = field(default=0.0)

    @property
    def has_position(self) -> bool:
        return self.position is not None
