from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Sequence


REQUIRED_OPTIONS_CAPABILITIES: tuple[str, ...] = (
    "option_chains",
    "implied_volatility_surface",
    "greeks",
    "option_fills",
    "assignment_exercise",
    "option_margin",
    "liquidity_slippage",
    "tail_stress",
)


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying: str
    expiration: str
    strike: float
    option_type: str
    multiplier: int = 100

    def __post_init__(self) -> None:
        option_type = self.option_type.lower()
        if option_type not in {"call", "put"}:
            raise ValueError("option_type must be 'call' or 'put'.")
        if self.strike <= 0:
            raise ValueError("Option strike must be positive.")
        if self.multiplier <= 0:
            raise ValueError("Option multiplier must be positive.")

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "expiration": self.expiration,
            "strike": self.strike,
            "option_type": self.option_type.lower(),
            "multiplier": self.multiplier,
        }


@dataclass(frozen=True)
class OptionGreeks:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float = 0.0
    implied_volatility: float | None = None

    def to_dict(self) -> dict:
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "rho": self.rho,
            "implied_volatility": self.implied_volatility,
        }


@dataclass(frozen=True)
class OptionQuote:
    bid: float
    ask: float
    last: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    greeks: OptionGreeks | None = None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return max(0.0, self.ask - self.bid)

    def to_dict(self) -> dict:
        return {
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "spread": self.spread,
            "last": self.last,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "greeks": self.greeks.to_dict() if self.greeks else None,
        }


@dataclass(frozen=True)
class OptionChainSnapshot:
    underlying: str
    timestamp: datetime
    underlying_price: float
    quotes: Mapping[OptionContract, OptionQuote]

    def to_dict(self) -> dict:
        return {
            "underlying": self.underlying,
            "timestamp": self.timestamp.isoformat(),
            "underlying_price": self.underlying_price,
            "quotes": [
                {"contract": contract.to_dict(), "quote": quote.to_dict()}
                for contract, quote in self.quotes.items()
            ],
        }


@dataclass(frozen=True)
class OptionPosition:
    contract: OptionContract
    quantity: int
    average_price: float
    underlying_price: float

    @property
    def notional_multiplier(self) -> int:
        return abs(self.quantity) * self.contract.multiplier

    def to_dict(self) -> dict:
        return {
            "contract": self.contract.to_dict(),
            "quantity": self.quantity,
            "average_price": self.average_price,
            "underlying_price": self.underlying_price,
        }


@dataclass(frozen=True)
class OptionTailStressScenario:
    name: str
    underlying_move_pct: float
    volatility_shift: float = 0.0
    days_elapsed: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "underlying_move_pct": self.underlying_move_pct,
            "volatility_shift": self.volatility_shift,
            "days_elapsed": self.days_elapsed,
        }


@dataclass(frozen=True)
class OptionTailStressResult:
    scenario: OptionTailStressScenario
    stressed_underlying_price: float
    stressed_intrinsic_value: float
    estimated_pnl: float

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario.to_dict(),
            "stressed_underlying_price": self.stressed_underlying_price,
            "stressed_intrinsic_value": self.stressed_intrinsic_value,
            "estimated_pnl": self.estimated_pnl,
        }


@dataclass(frozen=True)
class OptionsCapabilityStatus:
    name: str
    available: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class OptionsPromotionGateResult:
    strategy_family: str
    capabilities: tuple[OptionsCapabilityStatus, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def missing_capabilities(self) -> tuple[str, ...]:
        return tuple(status.name for status in self.capabilities if not status.available)

    @property
    def passed(self) -> bool:
        return not self.missing_capabilities

    @property
    def decision(self) -> str:
        return "promote" if self.passed else "block"

    def to_dict(self) -> dict:
        return {
            "strategy_family": self.strategy_family,
            "decision": self.decision,
            "passed": self.passed,
            "missing_capabilities": list(self.missing_capabilities),
            "warnings": list(self.warnings),
            "capabilities": [status.to_dict() for status in self.capabilities],
        }


def evaluate_options_promotion_gate(
    capabilities: Mapping[str, bool | str],
    strategy_family: str = "volatility_risk_premium",
    required: Sequence[str] = REQUIRED_OPTIONS_CAPABILITIES,
) -> OptionsPromotionGateResult:
    """Block option-income promotion until every options-specific subsystem exists."""

    statuses = []
    warnings = []
    for capability in required:
        raw_value = capabilities.get(capability, False)
        available = bool(raw_value)
        detail = raw_value if isinstance(raw_value, str) else ""
        statuses.append(OptionsCapabilityStatus(capability, available, detail))

    unknown = sorted(set(capabilities).difference(required))
    if unknown:
        warnings.append(f"Unknown options capabilities were ignored: {', '.join(unknown)}")

    return OptionsPromotionGateResult(
        strategy_family=strategy_family,
        capabilities=tuple(statuses),
        warnings=tuple(warnings),
    )


def intrinsic_value(contract: OptionContract, underlying_price: float) -> float:
    if contract.option_type.lower() == "call":
        return max(0.0, underlying_price - contract.strike)
    return max(0.0, contract.strike - underlying_price)


def stress_option_position(
    position: OptionPosition,
    scenarios: Sequence[OptionTailStressScenario],
) -> tuple[OptionTailStressResult, ...]:
    """Estimate intrinsic-value stress PnL for option positions.

    This is intentionally conservative scaffolding, not an option pricer. It gives
    the roadmap gate a concrete tail-risk object while keeping promotion blocked
    until full IV surface, Greeks, margin, assignment, and fill modeling exist.
    """

    entry_value = position.average_price * position.contract.multiplier * position.quantity
    results = []
    for scenario in scenarios:
        stressed_underlying = position.underlying_price * (1 + scenario.underlying_move_pct)
        stressed_intrinsic = intrinsic_value(position.contract, stressed_underlying)
        stressed_value = stressed_intrinsic * position.contract.multiplier * position.quantity
        results.append(
            OptionTailStressResult(
                scenario=scenario,
                stressed_underlying_price=stressed_underlying,
                stressed_intrinsic_value=stressed_intrinsic,
                estimated_pnl=stressed_value - entry_value,
            )
        )
    return tuple(results)
