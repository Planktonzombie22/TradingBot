from dataclasses import dataclass
from typing import Sequence

from src.models import BacktestResult


@dataclass(frozen=True)
class CapacityAnalysisConfig:
    capital_levels: tuple[float, ...] = (10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000)
    spread_bps: float = 2.0
    impact_bps_per_volume_share: float = 25.0
    commission_bps: float = 0.0
    annual_borrow_rate: float = 0.03
    max_short_notional_fraction: float = 1.0
    slippage_stress_multiplier: float = 1.0
    periods_per_year: int = 252
    max_volume_participation: float = 0.10
    min_net_return: float = 0.0


@dataclass(frozen=True)
class StrategyCapacityProfile:
    strategy: str
    gross_return: float
    gross_trade_notional: float
    average_trade_notional: float
    average_bar_volume_notional: float
    turnover: float
    short_notional_fraction: float
    trades: int

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "gross_return": self.gross_return,
            "gross_trade_notional": self.gross_trade_notional,
            "average_trade_notional": self.average_trade_notional,
            "average_bar_volume_notional": self.average_bar_volume_notional,
            "turnover": self.turnover,
            "short_notional_fraction": self.short_notional_fraction,
            "trades": self.trades,
        }


@dataclass(frozen=True)
class CapacityPoint:
    capital: float
    gross_return: float
    estimated_cost_return: float
    net_return: float
    turnover: float
    volume_participation: float
    spread_cost_return: float
    impact_cost_return: float
    commission_cost_return: float
    borrow_cost_return: float
    capacity_ok: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "capital": self.capital,
            "gross_return": self.gross_return,
            "estimated_cost_return": self.estimated_cost_return,
            "net_return": self.net_return,
            "turnover": self.turnover,
            "volume_participation": self.volume_participation,
            "spread_cost_return": self.spread_cost_return,
            "impact_cost_return": self.impact_cost_return,
            "commission_cost_return": self.commission_cost_return,
            "borrow_cost_return": self.borrow_cost_return,
            "capacity_ok": self.capacity_ok,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CapacityAnalysisReport:
    profile: StrategyCapacityProfile
    config: CapacityAnalysisConfig
    points: tuple[CapacityPoint, ...]

    @property
    def estimated_capacity(self) -> float | None:
        ok_points = [point.capital for point in self.points if point.capacity_ok]
        return max(ok_points) if ok_points else None

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.to_dict(),
            "estimated_capacity": self.estimated_capacity,
            "config": {
                "capital_levels": list(self.config.capital_levels),
                "spread_bps": self.config.spread_bps,
                "impact_bps_per_volume_share": self.config.impact_bps_per_volume_share,
                "commission_bps": self.config.commission_bps,
                "annual_borrow_rate": self.config.annual_borrow_rate,
                "max_short_notional_fraction": self.config.max_short_notional_fraction,
                "slippage_stress_multiplier": self.config.slippage_stress_multiplier,
                "periods_per_year": self.config.periods_per_year,
                "max_volume_participation": self.config.max_volume_participation,
                "min_net_return": self.config.min_net_return,
            },
            "points": [point.to_dict() for point in self.points],
        }


def analyze_capacity(
    profile: StrategyCapacityProfile,
    config: CapacityAnalysisConfig | None = None,
) -> CapacityAnalysisReport:
    config = config or CapacityAnalysisConfig()
    points = tuple(_capacity_point(profile, capital, config) for capital in config.capital_levels)
    return CapacityAnalysisReport(profile=profile, config=config, points=points)


def capacity_profile_from_backtest(
    result: BacktestResult,
    strategy: str,
    average_bar_volume_notional: float,
) -> StrategyCapacityProfile:
    starting_equity = float(result.metrics.get("starting_equity", 0.0) or 0.0)
    if starting_equity <= 0 and len(result.equity):
        starting_equity = float(result.equity.iloc[0])
    gross_trade_notional = sum(abs(_fill_notional(fill)) for fill in result.fills)
    trades = len(result.trades)
    average_trade_notional = gross_trade_notional / len(result.fills) if result.fills else 0.0
    short_notional = sum(abs(_fill_notional(fill)) for fill in result.fills if getattr(getattr(fill, "order", None), "side", "") == "SELL")
    return StrategyCapacityProfile(
        strategy=strategy,
        gross_return=float(result.total_pnl_pct),
        gross_trade_notional=gross_trade_notional,
        average_trade_notional=average_trade_notional,
        average_bar_volume_notional=average_bar_volume_notional,
        turnover=gross_trade_notional / starting_equity if starting_equity else 0.0,
        short_notional_fraction=short_notional / gross_trade_notional if gross_trade_notional else 0.0,
        trades=trades,
    )


def analyze_backtest_capacity(
    result: BacktestResult,
    strategy: str,
    average_bar_volume_notional: float,
    config: CapacityAnalysisConfig | None = None,
) -> CapacityAnalysisReport:
    return analyze_capacity(capacity_profile_from_backtest(result, strategy, average_bar_volume_notional), config)


def compare_capacity_reports(reports: Sequence[CapacityAnalysisReport]) -> list[dict]:
    rows = []
    for report in reports:
        rows.append(
            {
                "strategy": report.profile.strategy,
                "estimated_capacity": report.estimated_capacity,
                "gross_return": report.profile.gross_return,
                "best_net_return": max((point.net_return for point in report.points), default=0.0),
                "turnover": report.profile.turnover,
                "trades": report.profile.trades,
            }
        )
    return sorted(rows, key=lambda row: ((row["estimated_capacity"] or 0), row["best_net_return"]), reverse=True)


def _capacity_point(profile: StrategyCapacityProfile, capital: float, config: CapacityAnalysisConfig) -> CapacityPoint:
    scale = _capital_scale(profile, capital)
    volume_participation = 0.0
    if profile.average_bar_volume_notional > 0:
        volume_participation = min(1.0, profile.average_trade_notional * scale / profile.average_bar_volume_notional)
    stress = max(config.slippage_stress_multiplier, 0.0)
    spread_cost = profile.turnover * config.spread_bps * stress / 2 / 10_000
    impact_cost = profile.turnover * config.impact_bps_per_volume_share * stress * volume_participation / 10_000
    commission_cost = profile.turnover * config.commission_bps / 10_000
    borrow_cost = profile.short_notional_fraction * config.annual_borrow_rate / max(config.periods_per_year, 1)
    total_cost = spread_cost + impact_cost + commission_cost + borrow_cost
    net_return = profile.gross_return - total_cost
    capacity_ok, reason = _capacity_decision(profile, net_return, volume_participation, config)
    return CapacityPoint(
        capital=capital,
        gross_return=profile.gross_return,
        estimated_cost_return=total_cost,
        net_return=net_return,
        turnover=profile.turnover,
        volume_participation=volume_participation,
        spread_cost_return=spread_cost,
        impact_cost_return=impact_cost,
        commission_cost_return=commission_cost,
        borrow_cost_return=borrow_cost,
        capacity_ok=capacity_ok,
        reason=reason,
    )


def _capital_scale(profile: StrategyCapacityProfile, capital: float) -> float:
    if profile.gross_trade_notional <= 0 or profile.average_trade_notional <= 0:
        return 0.0
    implied_starting_equity = profile.gross_trade_notional / max(profile.turnover, 0.000001)
    return capital / implied_starting_equity if implied_starting_equity > 0 else 0.0


def _capacity_decision(
    profile: StrategyCapacityProfile,
    net_return: float,
    volume_participation: float,
    config: CapacityAnalysisConfig,
) -> tuple[bool, str]:
    if volume_participation > config.max_volume_participation:
        return False, "volume_participation_too_high"
    if profile.short_notional_fraction > config.max_short_notional_fraction:
        return False, "borrow_availability_too_low"
    if net_return < config.min_net_return:
        return False, "net_return_below_threshold"
    return True, "capacity_ok"


def _fill_notional(fill: object) -> float:
    if hasattr(fill, "notional"):
        return float(getattr(fill, "notional"))
    price = float(getattr(fill, "price", 0.0))
    quantity = float(getattr(fill, "quantity", 0.0))
    return price * quantity
