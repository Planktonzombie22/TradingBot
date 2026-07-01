from dataclasses import dataclass, field
from typing import Dict

from src.models import Position


@dataclass
class PortfolioBook:
    """Simple in-memory view of open positions keyed by symbol."""

    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)

    def add_position(self, position: Position) -> None:
        self.positions[position.symbol] = position

    def remove_position(self, symbol: str) -> Position:
        return self.positions.pop(symbol)

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    @property
    def gross_exposure(self) -> float:
        return sum(abs(position.shares * position.entry_price) for position in self.positions.values())
