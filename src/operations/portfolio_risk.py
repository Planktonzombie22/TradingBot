import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class PortfolioExposureLine:
    symbol: str
    strategy_name: str
    sector: str
    asset_class: str
    quantity: float
    market_value: float
    pending_order_notional: float
    target_notional: float | None = None

    @property
    def net_notional(self) -> float:
        return self.market_value + self.pending_order_notional

    @property
    def gross_notional(self) -> float:
        return abs(self.net_notional)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "sector": self.sector,
            "asset_class": self.asset_class,
            "quantity": self.quantity,
            "market_value": self.market_value,
            "pending_order_notional": self.pending_order_notional,
            "target_notional": self.target_notional,
            "net_notional": self.net_notional,
            "gross_notional": self.gross_notional,
        }


@dataclass(frozen=True)
class PortfolioExposureReport:
    lines: tuple[PortfolioExposureLine, ...]
    cash: float | None = None
    buying_power: float | None = None
    equity: float | None = None
    artifact_path: str | None = None

    @property
    def gross_exposure(self) -> float:
        return sum(line.gross_notional for line in self.lines)

    @property
    def net_exposure(self) -> float:
        return sum(line.net_notional for line in self.lines)

    @property
    def long_exposure(self) -> float:
        return sum(max(0.0, line.net_notional) for line in self.lines)

    @property
    def short_exposure(self) -> float:
        return sum(abs(min(0.0, line.net_notional)) for line in self.lines)

    @property
    def passed(self) -> bool:
        return self.equity is None or self.equity >= 0.0

    @property
    def reason(self) -> str:
        return "portfolio_exposure_created" if self.passed else "negative_account_equity"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "cash": self.cash,
            "buying_power": self.buying_power,
            "equity": self.equity,
            "gross_exposure": self.gross_exposure,
            "net_exposure": self.net_exposure,
            "long_exposure": self.long_exposure,
            "short_exposure": self.short_exposure,
            "lines": [line.to_dict() for line in self.lines],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class BetaVolAdjustedExposureLine:
    symbol: str
    notional: float
    beta: float
    volatility: float
    beta_adjusted_notional: float
    vol_adjusted_notional: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "notional": self.notional,
            "beta": self.beta,
            "volatility": self.volatility,
            "beta_adjusted_notional": self.beta_adjusted_notional,
            "vol_adjusted_notional": self.vol_adjusted_notional,
        }


@dataclass(frozen=True)
class BetaVolAdjustedExposureReport:
    lines: tuple[BetaVolAdjustedExposureLine, ...]
    max_beta_adjusted_gross: float | None = None
    max_vol_adjusted_gross: float | None = None
    artifact_path: str | None = None

    @property
    def beta_adjusted_gross(self) -> float:
        return sum(abs(line.beta_adjusted_notional) for line in self.lines)

    @property
    def vol_adjusted_gross(self) -> float:
        return sum(abs(line.vol_adjusted_notional) for line in self.lines)

    @property
    def passed(self) -> bool:
        if self.max_beta_adjusted_gross is not None and self.beta_adjusted_gross > self.max_beta_adjusted_gross:
            return False
        if self.max_vol_adjusted_gross is not None and self.vol_adjusted_gross > self.max_vol_adjusted_gross:
            return False
        return True

    @property
    def reason(self) -> str:
        if self.max_beta_adjusted_gross is not None and self.beta_adjusted_gross > self.max_beta_adjusted_gross:
            return "beta_adjusted_exposure_above_limit"
        if self.max_vol_adjusted_gross is not None and self.vol_adjusted_gross > self.max_vol_adjusted_gross:
            return "vol_adjusted_exposure_above_limit"
        return "beta_vol_adjusted_exposure_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "beta_adjusted_gross": self.beta_adjusted_gross,
            "vol_adjusted_gross": self.vol_adjusted_gross,
            "max_beta_adjusted_gross": self.max_beta_adjusted_gross,
            "max_vol_adjusted_gross": self.max_vol_adjusted_gross,
            "lines": [line.to_dict() for line in self.lines],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class CorrelationCluster:
    name: str
    symbols: tuple[str, ...]
    gross_exposure: float
    max_cluster_exposure: float | None = None

    @property
    def passed(self) -> bool:
        return self.max_cluster_exposure is None or self.gross_exposure <= self.max_cluster_exposure

    @property
    def reason(self) -> str:
        return "passed" if self.passed else "correlation_cluster_exposure_above_limit"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "symbols": list(self.symbols),
            "gross_exposure": self.gross_exposure,
            "max_cluster_exposure": self.max_cluster_exposure,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CorrelationClusterCapReport:
    clusters: tuple[CorrelationCluster, ...]
    correlation_threshold: float = 0.80
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(cluster.passed for cluster in self.clusters)

    @property
    def reason(self) -> str:
        if self.passed:
            return "correlation_cluster_caps_passed"
        return next(cluster.reason for cluster in self.clusters if not cluster.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "correlation_threshold": self.correlation_threshold,
            "clusters": [cluster.to_dict() for cluster in self.clusters],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class ExposureCapStatus:
    group_type: str
    group: str
    exposure: float
    limit: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "group_type": self.group_type,
            "group": self.group,
            "exposure": self.exposure,
            "limit": self.limit,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PortfolioExposureCapReport:
    statuses: tuple[ExposureCapStatus, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(status.passed for status in self.statuses)

    @property
    def reason(self) -> str:
        if self.passed:
            return "portfolio_exposure_caps_passed"
        return next(status.reason for status in self.statuses if not status.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "statuses": [status.to_dict() for status in self.statuses],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StrategyCapitalBudgetDecision:
    strategy_name: str
    current_budget: float
    requested_budget: float
    paper_scorecard_passed: bool
    operator_approved: bool
    approved_budget: float
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason in {"budget_unchanged", "budget_increase_approved", "budget_reduction_allowed"}

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "current_budget": self.current_budget,
            "requested_budget": self.requested_budget,
            "paper_scorecard_passed": self.paper_scorecard_passed,
            "operator_approved": self.operator_approved,
            "approved_budget": self.approved_budget,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StrategyCapitalBudgetReport:
    decisions: tuple[StrategyCapitalBudgetDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "strategy_capital_budgets_passed"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class CapitalDecayDecision:
    strategy_name: str
    current_budget: float
    decayed_budget: float
    decay_rate: float
    reason: str

    @property
    def decayed(self) -> bool:
        return self.decayed_budget < self.current_budget

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "current_budget": self.current_budget,
            "decayed_budget": self.decayed_budget,
            "decay_rate": self.decay_rate,
            "decayed": self.decayed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CapitalDecayReport:
    decisions: tuple[CapitalDecayDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return True

    @property
    def reason(self) -> str:
        return "capital_decay_evaluated"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class LossLimitReport:
    daily_loss: float
    weekly_loss: float
    max_daily_loss: float | None = None
    max_weekly_loss: float | None = None
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        if self.max_daily_loss is not None and self.daily_loss > self.max_daily_loss:
            return False
        if self.max_weekly_loss is not None and self.weekly_loss > self.max_weekly_loss:
            return False
        return True

    @property
    def reason(self) -> str:
        if self.max_daily_loss is not None and self.daily_loss > self.max_daily_loss:
            return "daily_loss_limit_breached"
        if self.max_weekly_loss is not None and self.weekly_loss > self.max_weekly_loss:
            return "weekly_loss_limit_breached"
        return "loss_limits_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "daily_loss": self.daily_loss,
            "weekly_loss": self.weekly_loss,
            "max_daily_loss": self.max_daily_loss,
            "max_weekly_loss": self.max_weekly_loss,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class DrawdownLockoutReport:
    current_equity: float
    peak_equity: float
    drawdown: float
    drawdown_pct: float
    max_drawdown_pct: float
    prior_locked: bool = False
    manual_reset: bool = False
    locked: bool = False
    observed_at: str = ""
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return not self.locked

    @property
    def reason(self) -> str:
        if self.locked and self.prior_locked and not self.manual_reset:
            return "drawdown_lockout_persisted"
        if self.locked:
            return "drawdown_lockout_triggered"
        if self.manual_reset:
            return "drawdown_lockout_reset"
        return "drawdown_within_limit"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "current_equity": self.current_equity,
            "peak_equity": self.peak_equity,
            "drawdown": self.drawdown,
            "drawdown_pct": self.drawdown_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "prior_locked": self.prior_locked,
            "manual_reset": self.manual_reset,
            "locked": self.locked,
            "observed_at": self.observed_at,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class VolatilityShockLine:
    symbol: str
    notional: float
    shock_pct: float
    estimated_pnl: float
    estimated_loss: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "notional": self.notional,
            "shock_pct": self.shock_pct,
            "estimated_pnl": self.estimated_pnl,
            "estimated_loss": self.estimated_loss,
        }


@dataclass(frozen=True)
class VolatilityShockReport:
    lines: tuple[VolatilityShockLine, ...]
    total_estimated_loss: float
    max_loss: float | None = None
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.max_loss is None or self.total_estimated_loss <= self.max_loss

    @property
    def reason(self) -> str:
        return "volatility_shock_passed" if self.passed else "volatility_shock_loss_above_limit"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "total_estimated_loss": self.total_estimated_loss,
            "max_loss": self.max_loss,
            "lines": [line.to_dict() for line in self.lines],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class GapThroughStopStressLine:
    symbol: str
    quantity: float
    current_price: float
    stop_price: float
    stressed_exit_price: float
    estimated_gap_loss: float
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "current_price": self.current_price,
            "stop_price": self.stop_price,
            "stressed_exit_price": self.stressed_exit_price,
            "estimated_gap_loss": self.estimated_gap_loss,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GapThroughStopStressReport:
    lines: tuple[GapThroughStopStressLine, ...]
    total_estimated_gap_loss: float
    max_gap_loss: float | None = None
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(line.passed for line in self.lines) and (self.max_gap_loss is None or self.total_estimated_gap_loss <= self.max_gap_loss)

    @property
    def reason(self) -> str:
        if any(not line.passed for line in self.lines):
            return next(line.reason for line in self.lines if not line.passed)
        if self.max_gap_loss is not None and self.total_estimated_gap_loss > self.max_gap_loss:
            return "gap_through_stop_loss_above_budget"
        return "gap_through_stop_stress_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "total_estimated_gap_loss": self.total_estimated_gap_loss,
            "max_gap_loss": self.max_gap_loss,
            "lines": [line.to_dict() for line in self.lines],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class MarginPressureReport:
    equity: float
    buying_power: float
    maintenance_required: float
    concentration_notional: float
    max_concentration_pct: float | None = None
    artifact_path: str | None = None

    @property
    def concentration_pct(self) -> float | None:
        return self.concentration_notional / self.equity if self.equity else None

    @property
    def passed(self) -> bool:
        if self.maintenance_required > self.equity:
            return False
        if self.max_concentration_pct is not None and self.concentration_pct is not None:
            if self.concentration_pct > self.max_concentration_pct:
                return False
        return True

    @property
    def reason(self) -> str:
        if self.maintenance_required > self.equity:
            return "maintenance_margin_above_equity"
        if self.max_concentration_pct is not None and self.concentration_pct is not None:
            if self.concentration_pct > self.max_concentration_pct:
                return "concentration_above_margin_limit"
        return "margin_pressure_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "equity": self.equity,
            "buying_power": self.buying_power,
            "maintenance_required": self.maintenance_required,
            "concentration_notional": self.concentration_notional,
            "concentration_pct": self.concentration_pct,
            "max_concentration_pct": self.max_concentration_pct,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class CashReserveReport:
    cash: float
    pending_entry_notional: float
    pending_exit_credit: float
    projected_cash: float
    required_reserve: float
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.projected_cash >= self.required_reserve

    @property
    def reason(self) -> str:
        return "cash_reserve_passed" if self.passed else "cash_reserve_below_requirement"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "cash": self.cash,
            "pending_entry_notional": self.pending_entry_notional,
            "pending_exit_credit": self.pending_exit_credit,
            "projected_cash": self.projected_cash,
            "required_reserve": self.required_reserve,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class DynamicPositionScalingDecision:
    symbol: str
    strategy_name: str
    base_notional: float
    scaled_notional: float
    confidence: float
    paper_scorecard_quality: float
    regime_fit: float
    volatility: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "base_notional": self.base_notional,
            "scaled_notional": self.scaled_notional,
            "confidence": self.confidence,
            "paper_scorecard_quality": self.paper_scorecard_quality,
            "regime_fit": self.regime_fit,
            "volatility": self.volatility,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DynamicPositionScalingReport:
    decisions: tuple[DynamicPositionScalingDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return True

    @property
    def reason(self) -> str:
        return "dynamic_position_scaling_evaluated"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PortfolioRebalanceDecision:
    symbol: str
    current_notional: float
    target_notional: float
    delta_notional: float
    action: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_notional": self.current_notional,
            "target_notional": self.target_notional,
            "delta_notional": self.delta_notional,
            "action": self.action,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PortfolioRebalanceReport:
    decisions: tuple[PortfolioRebalanceDecision, ...]
    rebalance_threshold_notional: float = 25.0
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return True

    @property
    def reason(self) -> str:
        return "portfolio_rebalance_evaluated"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "rebalance_threshold_notional": self.rebalance_threshold_notional,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class SymbolConflictDecision:
    symbol: str
    long_strategies: tuple[str, ...]
    short_strategies: tuple[str, ...]
    net_requested_notional: float
    action: str
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason in {"no_conflict", "netted_conflict"}

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "long_strategies": list(self.long_strategies),
            "short_strategies": list(self.short_strategies),
            "net_requested_notional": self.net_requested_notional,
            "action": self.action,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SymbolConflictReport:
    decisions: tuple[SymbolConflictDecision, ...]
    allow_netting: bool = True
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "symbol_conflicts_resolved"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "allow_netting": self.allow_netting,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class StrategyStopTradingDecision:
    strategy_name: str
    stopped: bool
    stopped_until: str | None
    reason: str
    evidence: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return not self.stopped

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "stopped": self.stopped,
            "stopped_until": self.stopped_until,
            "passed": self.passed,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class StrategyStopTradingReport:
    decisions: tuple[StrategyStopTradingDecision, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(decision.passed for decision in self.decisions)

    @property
    def reason(self) -> str:
        if self.passed:
            return "strategy_stop_rules_clear"
        return next(decision.reason for decision in self.decisions if not decision.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class PortfolioKillSwitchReport:
    triggered: bool
    reason: str
    cancel_open_orders: bool
    flatten_positions: bool
    disable_new_orders: bool
    cancel_order_count: int
    flatten_order_count: int
    flatten_orders: tuple[Mapping[str, Any], ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return not self.triggered

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "triggered": self.triggered,
            "reason": self.reason,
            "cancel_open_orders": self.cancel_open_orders,
            "flatten_positions": self.flatten_positions,
            "disable_new_orders": self.disable_new_orders,
            "cancel_order_count": self.cancel_order_count,
            "flatten_order_count": self.flatten_order_count,
            "flatten_orders": [dict(order) for order in self.flatten_orders],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class AccountRiskPercentageStatus:
    name: str
    value: float
    pct_of_equity: float | None
    limit_pct: float | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.reason == "passed"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "pct_of_equity": self.pct_of_equity,
            "limit_pct": self.limit_pct,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AccountRiskPercentageReport:
    statuses: tuple[AccountRiskPercentageStatus, ...]
    equity: float
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(status.passed for status in self.statuses)

    @property
    def reason(self) -> str:
        if self.passed:
            return "account_risk_percentages_passed"
        return next(status.reason for status in self.statuses if not status.passed)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "equity": self.equity,
            "statuses": [status.to_dict() for status in self.statuses],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class RiskDashboardCard:
    name: str
    passed: bool
    reason: str
    severity: str
    value: float | str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "severity": self.severity,
            "value": self.value,
        }


@dataclass(frozen=True)
class RiskDashboardSummaryReport:
    cards: tuple[RiskDashboardCard, ...]
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(card.passed for card in self.cards)

    @property
    def critical_count(self) -> int:
        return sum(1 for card in self.cards if card.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for card in self.cards if card.severity == "warning")

    @property
    def reason(self) -> str:
        return "risk_dashboard_clear" if self.passed else "risk_dashboard_has_alerts"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "cards": [card.to_dict() for card in self.cards],
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class VarCvarExposureLine:
    symbol: str
    notional: float
    var: float
    cvar: float
    scenarios: int

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "notional": self.notional,
            "var": self.var,
            "cvar": self.cvar,
            "scenarios": self.scenarios,
        }


@dataclass(frozen=True)
class VarCvarExposureReport:
    lines: tuple[VarCvarExposureLine, ...]
    confidence: float = 0.95
    max_var: float | None = None
    max_cvar: float | None = None
    artifact_path: str | None = None

    @property
    def total_var(self) -> float:
        return sum(line.var for line in self.lines)

    @property
    def total_cvar(self) -> float:
        return sum(line.cvar for line in self.lines)

    @property
    def passed(self) -> bool:
        if self.max_var is not None and self.total_var > self.max_var:
            return False
        if self.max_cvar is not None and self.total_cvar > self.max_cvar:
            return False
        return True

    @property
    def reason(self) -> str:
        if self.max_var is not None and self.total_var > self.max_var:
            return "portfolio_var_above_limit"
        if self.max_cvar is not None and self.total_cvar > self.max_cvar:
            return "portfolio_cvar_above_limit"
        return "portfolio_var_cvar_passed"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "confidence": self.confidence,
            "total_var": self.total_var,
            "total_cvar": self.total_cvar,
            "max_var": self.max_var,
            "max_cvar": self.max_cvar,
            "lines": [line.to_dict() for line in self.lines],
            "artifact_path": self.artifact_path,
        }


def build_portfolio_exposure_report(
    account_snapshot: Mapping[str, Any] | None = None,
    broker_positions: Sequence[Mapping[str, Any]] = (),
    expected_positions: Sequence[Mapping[str, Any]] = (),
    open_orders: Sequence[Mapping[str, Any]] = (),
    strategy_targets: Sequence[Mapping[str, Any]] = (),
) -> PortfolioExposureReport:
    account = account_snapshot or {}
    pending = _pending_notional_by_symbol(open_orders)
    targets = _target_notional_by_symbol(strategy_targets)
    expected = _expected_by_symbol(expected_positions)
    symbols = sorted({*_symbols(broker_positions), *expected.keys(), *pending.keys(), *targets.keys()})
    lines = tuple(_exposure_line(symbol, broker_positions, expected, pending, targets) for symbol in symbols)
    return PortfolioExposureReport(
        lines=lines,
        cash=_optional_float(account.get("cash")),
        buying_power=_optional_float(account.get("buying_power")),
        equity=_optional_float(account.get("equity") or account.get("portfolio_value")),
    )


def build_beta_vol_adjusted_exposure_report(
    exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]],
    risk_by_symbol: Mapping[str, Mapping[str, Any]],
    max_beta_adjusted_gross: float | None = None,
    max_vol_adjusted_gross: float | None = None,
    volatility_target: float = 0.20,
) -> BetaVolAdjustedExposureReport:
    lines = _exposure_lines(exposure)
    adjusted = tuple(_beta_vol_line(line, risk_by_symbol.get(line.symbol, {}), volatility_target) for line in lines)
    return BetaVolAdjustedExposureReport(
        adjusted,
        max_beta_adjusted_gross=max_beta_adjusted_gross,
        max_vol_adjusted_gross=max_vol_adjusted_gross,
    )


def build_correlation_cluster_cap_report(
    exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]],
    correlations: Mapping[tuple[str, str] | str, float],
    max_cluster_exposure: float | None = None,
    correlation_threshold: float = 0.80,
) -> CorrelationClusterCapReport:
    lines = _exposure_lines(exposure)
    clusters = _correlation_clusters(tuple(line.symbol for line in lines), correlations, correlation_threshold)
    exposure_by_symbol = {line.symbol: line.gross_notional for line in lines}
    reports = tuple(
        CorrelationCluster(
            name="cluster_" + "_".join(cluster),
            symbols=cluster,
            gross_exposure=sum(exposure_by_symbol.get(symbol, 0.0) for symbol in cluster),
            max_cluster_exposure=max_cluster_exposure,
        )
        for cluster in clusters
    )
    return CorrelationClusterCapReport(reports, correlation_threshold=correlation_threshold)


def build_portfolio_exposure_cap_report(
    exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]],
    symbol_caps: Mapping[str, float] | None = None,
    sector_caps: Mapping[str, float] | None = None,
    asset_class_caps: Mapping[str, float] | None = None,
    strategy_caps: Mapping[str, float] | None = None,
    total_gross_cap: float | None = None,
    total_net_cap: float | None = None,
) -> PortfolioExposureCapReport:
    lines = _exposure_lines(exposure)
    statuses = []
    statuses.extend(_group_cap_status("symbol", _sum_by(lines, "symbol"), symbol_caps or {}))
    statuses.extend(_group_cap_status("sector", _sum_by(lines, "sector"), sector_caps or {}))
    statuses.extend(_group_cap_status("asset_class", _sum_by(lines, "asset_class"), asset_class_caps or {}))
    statuses.extend(_group_cap_status("strategy", _sum_by(lines, "strategy_name"), strategy_caps or {}))
    gross = sum(line.gross_notional for line in lines)
    net = abs(sum(line.net_notional for line in lines))
    statuses.append(_cap_status("total", "gross", gross, total_gross_cap))
    statuses.append(_cap_status("total", "net", net, total_net_cap))
    return PortfolioExposureCapReport(tuple(statuses))


def build_strategy_capital_budget_report(
    requests: Sequence[Mapping[str, Any]],
    current_budgets: Mapping[str, float],
) -> StrategyCapitalBudgetReport:
    decisions = tuple(_strategy_capital_decision(request, current_budgets) for request in requests)
    return StrategyCapitalBudgetReport(decisions)


def build_capital_decay_report(
    strategies: Sequence[Mapping[str, Any]],
    default_decay_rate: float = 0.25,
) -> CapitalDecayReport:
    return CapitalDecayReport(tuple(_capital_decay_decision(strategy, default_decay_rate) for strategy in strategies))


def build_loss_limit_report(
    pnl_rows: Sequence[Mapping[str, Any]],
    max_daily_loss: float | None = None,
    max_weekly_loss: float | None = None,
) -> LossLimitReport:
    daily = sum(_loss_from_row(row, "daily") for row in pnl_rows)
    weekly = sum(_loss_from_row(row, "weekly") for row in pnl_rows)
    return LossLimitReport(daily, weekly, max_daily_loss=max_daily_loss, max_weekly_loss=max_weekly_loss)


def build_drawdown_lockout_report(
    account_snapshot: Mapping[str, Any],
    prior_state: Mapping[str, Any] | None = None,
    max_drawdown_pct: float = 0.10,
    manual_reset: bool = False,
    observed_at: datetime | None = None,
) -> DrawdownLockoutReport:
    current_equity = _optional_float(account_snapshot.get("equity") or account_snapshot.get("portfolio_value")) or 0.0
    prior_peak = _optional_float((prior_state or {}).get("peak_equity"))
    prior_locked = bool((prior_state or {}).get("locked", False))
    peak = max(prior_peak or current_equity, current_equity)
    drawdown = max(0.0, peak - current_equity)
    drawdown_pct = drawdown / peak if peak else 0.0
    lock_triggered = drawdown_pct > max_drawdown_pct
    locked = False if manual_reset and not lock_triggered else bool(lock_triggered or prior_locked)
    return DrawdownLockoutReport(
        current_equity=current_equity,
        peak_equity=peak,
        drawdown=drawdown,
        drawdown_pct=drawdown_pct,
        max_drawdown_pct=max_drawdown_pct,
        prior_locked=prior_locked,
        manual_reset=manual_reset,
        locked=locked,
        observed_at=(observed_at or datetime.now(timezone.utc)).isoformat(),
    )


def build_volatility_shock_report(
    exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]],
    shocks_by_symbol: Mapping[str, float],
    max_loss: float | None = None,
) -> VolatilityShockReport:
    lines = tuple(_volatility_shock_line(line, shocks_by_symbol.get(line.symbol, 0.0)) for line in _exposure_lines(exposure))
    return VolatilityShockReport(lines, sum(line.estimated_loss for line in lines), max_loss=max_loss)


def build_gap_through_stop_stress_report(
    positions: Sequence[Mapping[str, Any]],
    default_gap_pct: float = 0.02,
    max_gap_loss: float | None = None,
) -> GapThroughStopStressReport:
    lines = tuple(_gap_through_stop_line(position, default_gap_pct) for position in positions)
    return GapThroughStopStressReport(lines, sum(line.estimated_gap_loss for line in lines), max_gap_loss=max_gap_loss)


def build_margin_pressure_report(
    exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]],
    account_snapshot: Mapping[str, Any],
    margin_by_symbol: Mapping[str, float] | None = None,
    default_maintenance_margin: float = 0.30,
    max_concentration_pct: float | None = None,
) -> MarginPressureReport:
    lines = _exposure_lines(exposure)
    margins = {str(symbol).upper(): float(value) for symbol, value in (margin_by_symbol or {}).items()}
    equity = _optional_float(account_snapshot.get("equity") or account_snapshot.get("portfolio_value")) or 0.0
    buying_power = _optional_float(account_snapshot.get("buying_power")) or 0.0
    maintenance = sum(line.gross_notional * margins.get(line.symbol, default_maintenance_margin) for line in lines)
    concentration = max((line.gross_notional for line in lines), default=0.0)
    return MarginPressureReport(equity, buying_power, maintenance, concentration, max_concentration_pct=max_concentration_pct)


def build_cash_reserve_report(
    account_snapshot: Mapping[str, Any],
    open_orders: Sequence[Mapping[str, Any]],
    pending_exits: Sequence[Mapping[str, Any]] = (),
    required_reserve: float = 0.0,
) -> CashReserveReport:
    cash = _optional_float(account_snapshot.get("cash")) or 0.0
    entries = sum(_entry_notional(order) for order in open_orders)
    exits = sum(_entry_notional(order) for order in pending_exits)
    projected = cash - entries + exits
    return CashReserveReport(cash, entries, exits, projected, required_reserve)


def build_dynamic_position_scaling_report(
    candidates: Sequence[Mapping[str, Any]],
    volatility_target: float = 0.20,
) -> DynamicPositionScalingReport:
    return DynamicPositionScalingReport(tuple(_dynamic_scaling_decision(candidate, volatility_target) for candidate in candidates))


def build_portfolio_rebalance_report(
    exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]],
    targets: Sequence[Mapping[str, Any]],
    rebalance_threshold_notional: float = 25.0,
) -> PortfolioRebalanceReport:
    lines = {line.symbol: line for line in _exposure_lines(exposure)}
    target_by_symbol = _target_notional_by_symbol(targets)
    symbols = sorted(set(lines) | set(target_by_symbol))
    decisions = tuple(_rebalance_decision(symbol, lines.get(symbol), target_by_symbol.get(symbol, 0.0), rebalance_threshold_notional) for symbol in symbols)
    return PortfolioRebalanceReport(decisions, rebalance_threshold_notional=rebalance_threshold_notional)


def build_symbol_conflict_report(
    intents: Sequence[Mapping[str, Any]],
    allow_netting: bool = True,
) -> SymbolConflictReport:
    by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    for intent in intents:
        by_symbol.setdefault(str(intent.get("symbol") or "").upper(), []).append(intent)
    decisions = tuple(_symbol_conflict_decision(symbol, rows, allow_netting) for symbol, rows in sorted(by_symbol.items()))
    return SymbolConflictReport(decisions, allow_netting=allow_netting)


def build_strategy_stop_trading_report(
    strategy_rows: Sequence[Mapping[str, Any]],
    max_drawdown_pct: float = 0.08,
    max_data_drift_bps: float = 50.0,
    max_slippage_breaches: int = 2,
    max_rejects: int = 2,
    max_missing_fills: int = 1,
    cooldown_minutes: float = 390.0,
    observed_at: datetime | None = None,
) -> StrategyStopTradingReport:
    observed = observed_at or datetime.now(timezone.utc)
    decisions = tuple(
        _strategy_stop_decision(
            row,
            max_drawdown_pct,
            max_data_drift_bps,
            max_slippage_breaches,
            max_rejects,
            max_missing_fills,
            cooldown_minutes,
            observed,
        )
        for row in strategy_rows
    )
    return StrategyStopTradingReport(decisions)


def build_portfolio_kill_switch_report(
    exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]],
    open_orders: Sequence[Mapping[str, Any]] = (),
    triggered: bool = False,
    reason: str = "manual_kill_switch",
    disable_new_orders: bool = True,
) -> PortfolioKillSwitchReport:
    lines = _exposure_lines(exposure)
    flatten_orders = tuple(_flatten_order(line) for line in lines if abs(line.quantity) > 1e-12)
    return PortfolioKillSwitchReport(
        triggered=triggered,
        reason=reason if triggered else "kill_switch_not_triggered",
        cancel_open_orders=triggered and bool(open_orders),
        flatten_positions=triggered and bool(flatten_orders),
        disable_new_orders=triggered and disable_new_orders,
        cancel_order_count=len(open_orders) if triggered else 0,
        flatten_order_count=len(flatten_orders) if triggered else 0,
        flatten_orders=flatten_orders if triggered else (),
    )


def build_account_risk_percentage_report(
    account_snapshot: Mapping[str, Any],
    risk_values: Mapping[str, float],
    limits_pct: Mapping[str, float],
) -> AccountRiskPercentageReport:
    equity = _optional_float(account_snapshot.get("equity") or account_snapshot.get("portfolio_value")) or 0.0
    statuses = tuple(
        _account_risk_status(name, value, equity, limits_pct.get(name))
        for name, value in sorted(risk_values.items())
    )
    return AccountRiskPercentageReport(statuses, equity)


def build_risk_dashboard_summary_report(reports: Mapping[str, Any]) -> RiskDashboardSummaryReport:
    cards = tuple(_risk_dashboard_card(name, report) for name, report in sorted(reports.items()))
    return RiskDashboardSummaryReport(cards)


def build_var_cvar_exposure_report(
    exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]],
    returns_by_symbol: Mapping[str, Sequence[float]],
    confidence: float = 0.95,
    max_var: float | None = None,
    max_cvar: float | None = None,
) -> VarCvarExposureReport:
    lines = tuple(_var_cvar_line(line, returns_by_symbol.get(line.symbol, ()), confidence) for line in _exposure_lines(exposure))
    return VarCvarExposureReport(lines, confidence=confidence, max_var=max_var, max_cvar=max_cvar)


def write_portfolio_exposure_report(report: PortfolioExposureReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_beta_vol_adjusted_exposure_report(report: BetaVolAdjustedExposureReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_correlation_cluster_cap_report(report: CorrelationClusterCapReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_portfolio_exposure_cap_report(report: PortfolioExposureCapReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_strategy_capital_budget_report(report: StrategyCapitalBudgetReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_capital_decay_report(report: CapitalDecayReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_loss_limit_report(report: LossLimitReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_drawdown_lockout_report(report: DrawdownLockoutReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_volatility_shock_report(report: VolatilityShockReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_gap_through_stop_stress_report(report: GapThroughStopStressReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_margin_pressure_report(report: MarginPressureReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_cash_reserve_report(report: CashReserveReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_dynamic_position_scaling_report(report: DynamicPositionScalingReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_portfolio_rebalance_report(report: PortfolioRebalanceReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_symbol_conflict_report(report: SymbolConflictReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_strategy_stop_trading_report(report: StrategyStopTradingReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_portfolio_kill_switch_report(report: PortfolioKillSwitchReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_account_risk_percentage_report(report: AccountRiskPercentageReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_risk_dashboard_summary_report(report: RiskDashboardSummaryReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def write_var_cvar_exposure_report(report: VarCvarExposureReport, path: str | Path) -> str:
    return _write_report(report.to_dict(), path)


def _exposure_line(
    symbol: str,
    broker_positions: Sequence[Mapping[str, Any]],
    expected: Mapping[str, Mapping[str, Any]],
    pending: Mapping[str, float],
    targets: Mapping[str, float],
) -> PortfolioExposureLine:
    position = next((item for item in broker_positions if str(item.get("symbol") or "").upper() == symbol), {})
    fallback = expected.get(symbol, {})
    return PortfolioExposureLine(
        symbol=symbol,
        strategy_name=str(position.get("strategy_name") or fallback.get("strategy_name") or fallback.get("strategy") or "unknown"),
        sector=str(position.get("sector") or fallback.get("sector") or "unknown"),
        asset_class=str(position.get("asset_class") or fallback.get("asset_class") or "equity").lower(),
        quantity=_optional_float(position.get("quantity") or position.get("qty") or fallback.get("quantity")) or 0.0,
        market_value=_optional_float(position.get("market_value") or fallback.get("market_value") or fallback.get("notional")) or 0.0,
        pending_order_notional=pending.get(symbol, 0.0),
        target_notional=targets.get(symbol),
    )


def _pending_notional_by_symbol(open_orders: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    pending: dict[str, float] = {}
    for order in open_orders:
        symbol = str(order.get("symbol") or "").upper()
        side = str(order.get("side") or "").upper()
        quantity = _optional_float(order.get("quantity") or order.get("qty")) or 0.0
        price = _optional_float(order.get("limit_price") or order.get("estimated_price") or order.get("price")) or 0.0
        signed = quantity * price * (-1.0 if side == "SELL" else 1.0)
        pending[symbol] = pending.get(symbol, 0.0) + signed
    return pending


def _target_notional_by_symbol(targets: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    return {
        str(target.get("symbol") or "").upper(): _optional_float(target.get("target_notional") or target.get("notional")) or 0.0
        for target in targets
    }


def _expected_by_symbol(expected_positions: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(position.get("symbol") or "").upper(): position for position in expected_positions}


def _symbols(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")}


def _exposure_lines(exposure: PortfolioExposureReport | Sequence[Mapping[str, Any]]) -> tuple[PortfolioExposureLine, ...]:
    if isinstance(exposure, PortfolioExposureReport):
        return exposure.lines
    return tuple(
        PortfolioExposureLine(
            symbol=str(row.get("symbol") or "").upper(),
            strategy_name=str(row.get("strategy_name") or row.get("strategy") or "unknown"),
            sector=str(row.get("sector") or "unknown"),
            asset_class=str(row.get("asset_class") or "equity").lower(),
            quantity=_optional_float(row.get("quantity") or row.get("qty")) or 0.0,
            market_value=_optional_float(row.get("market_value") or row.get("notional")) or 0.0,
            pending_order_notional=_optional_float(row.get("pending_order_notional")) or 0.0,
            target_notional=_optional_float(row.get("target_notional")),
        )
        for row in exposure
    )


def _beta_vol_line(
    line: PortfolioExposureLine,
    risk: Mapping[str, Any],
    volatility_target: float,
) -> BetaVolAdjustedExposureLine:
    beta = _optional_float(risk.get("beta")) or 1.0
    volatility = _optional_float(risk.get("volatility") or risk.get("annualized_volatility")) or volatility_target
    vol_scale = volatility / volatility_target if volatility_target else 1.0
    return BetaVolAdjustedExposureLine(
        symbol=line.symbol,
        notional=line.net_notional,
        beta=beta,
        volatility=volatility,
        beta_adjusted_notional=line.net_notional * beta,
        vol_adjusted_notional=line.net_notional * vol_scale,
    )


def _correlation_clusters(
    symbols: tuple[str, ...],
    correlations: Mapping[tuple[str, str] | str, float],
    threshold: float,
) -> tuple[tuple[str, ...], ...]:
    remaining = set(symbols)
    clusters = []
    while remaining:
        seed = sorted(remaining)[0]
        cluster = {seed}
        changed = True
        while changed:
            changed = False
            for symbol in list(remaining):
                if symbol in cluster:
                    continue
                if any(abs(_correlation(symbol, peer, correlations)) >= threshold for peer in cluster):
                    cluster.add(symbol)
                    changed = True
        remaining -= cluster
        clusters.append(tuple(sorted(cluster)))
    return tuple(clusters)


def _correlation(left: str, right: str, correlations: Mapping[tuple[str, str] | str, float]) -> float:
    if left == right:
        return 1.0
    for key in ((left, right), (right, left), f"{left}|{right}", f"{right}|{left}"):
        value = correlations.get(key)
        if value is not None:
            return float(value)
    return 0.0


def _sum_by(lines: Sequence[PortfolioExposureLine], attr: str) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for line in lines:
        group = str(getattr(line, attr))
        grouped[group] = grouped.get(group, 0.0) + line.gross_notional
    return grouped


def _group_cap_status(group_type: str, exposures: Mapping[str, float], caps: Mapping[str, float]) -> list[ExposureCapStatus]:
    return [_cap_status(group_type, group, exposure, caps.get(group)) for group, exposure in sorted(exposures.items())]


def _cap_status(group_type: str, group: str, exposure: float, limit: float | None) -> ExposureCapStatus:
    if limit is not None and exposure > limit:
        return ExposureCapStatus(group_type, group, exposure, limit, f"{group_type}_exposure_above_limit")
    return ExposureCapStatus(group_type, group, exposure, limit, "passed")


def _strategy_capital_decision(
    request: Mapping[str, Any],
    current_budgets: Mapping[str, float],
) -> StrategyCapitalBudgetDecision:
    strategy = str(request.get("strategy_name") or request.get("strategy") or "unknown")
    current = float(current_budgets.get(strategy, 0.0))
    requested = _optional_float(request.get("requested_budget") or request.get("budget")) or current
    scorecard_passed = bool(request.get("paper_scorecard_passed", False))
    operator_approved = bool(request.get("operator_approved", False))
    if requested <= current:
        approved = requested
        reason = "budget_unchanged" if requested == current else "budget_reduction_allowed"
    elif not scorecard_passed:
        approved = current
        reason = "missing_passing_paper_scorecard"
    elif not operator_approved:
        approved = current
        reason = "missing_operator_approval"
    else:
        approved = requested
        reason = "budget_increase_approved"
    return StrategyCapitalBudgetDecision(strategy, current, requested, scorecard_passed, operator_approved, approved, reason)


def _capital_decay_decision(strategy: Mapping[str, Any], default_decay_rate: float) -> CapitalDecayDecision:
    name = str(strategy.get("strategy_name") or strategy.get("strategy") or "unknown")
    current = _optional_float(strategy.get("current_budget") or strategy.get("budget")) or 0.0
    decay_rate = _optional_float(strategy.get("decay_rate")) or default_decay_rate
    reasons = []
    if bool(strategy.get("underperformed", False)):
        reasons.append("underperformance")
    if int(strategy.get("execution_errors", 0) or 0) > 0:
        reasons.append("execution_errors")
    if bool(strategy.get("stale_research_evidence", False)):
        reasons.append("stale_research_evidence")
    if bool(strategy.get("paper_scorecard_failed", False)):
        reasons.append("paper_scorecard_failed")
    decayed = max(0.0, current * (1.0 - decay_rate)) if reasons else current
    return CapitalDecayDecision(name, current, decayed, decay_rate, "_".join(reasons) if reasons else "no_decay_required")


def _loss_from_row(row: Mapping[str, Any], horizon: str) -> float:
    if horizon == "daily":
        pnl = (
            (_optional_float(row.get("daily_realized_pnl")) or 0.0)
            + (_optional_float(row.get("daily_unrealized_pnl")) or 0.0)
            + (_optional_float(row.get("daily_strategy_attributed_pnl")) or 0.0)
        )
    else:
        pnl = (
            (_optional_float(row.get("weekly_realized_pnl")) or 0.0)
            + (_optional_float(row.get("weekly_unrealized_pnl")) or 0.0)
            + (_optional_float(row.get("weekly_strategy_attributed_pnl")) or 0.0)
        )
    return max(0.0, -pnl)


def _volatility_shock_line(line: PortfolioExposureLine, shock_pct: float) -> VolatilityShockLine:
    estimated_pnl = line.net_notional * shock_pct
    estimated_loss = max(0.0, -estimated_pnl)
    return VolatilityShockLine(line.symbol, line.net_notional, shock_pct, estimated_pnl, estimated_loss)


def _gap_through_stop_line(position: Mapping[str, Any], default_gap_pct: float) -> GapThroughStopStressLine:
    symbol = str(position.get("symbol") or "").upper()
    quantity = _optional_float(position.get("quantity") or position.get("qty")) or 0.0
    current = _optional_float(position.get("current_price") or position.get("price")) or 0.0
    stop = _optional_float(position.get("stop_price")) or 0.0
    gap = _optional_float(position.get("gap_pct")) or default_gap_pct
    if quantity == 0 or current <= 0 or stop <= 0:
        return GapThroughStopStressLine(symbol, quantity, current, stop, 0.0, 0.0, "missing_stop_stress_inputs")
    if quantity > 0:
        stressed_exit = stop * (1.0 - gap)
        loss = max(0.0, (current - stressed_exit) * quantity)
    else:
        stressed_exit = stop * (1.0 + gap)
        loss = max(0.0, (stressed_exit - current) * abs(quantity))
    return GapThroughStopStressLine(symbol, quantity, current, stop, stressed_exit, loss, "passed")


def _entry_notional(order: Mapping[str, Any]) -> float:
    notional = _optional_float(order.get("notional") or order.get("estimated_notional"))
    if notional is not None:
        return abs(notional)
    quantity = _optional_float(order.get("quantity") or order.get("qty")) or 0.0
    price = _optional_float(order.get("limit_price") or order.get("estimated_price") or order.get("price")) or 0.0
    return abs(quantity * price)


def _dynamic_scaling_decision(candidate: Mapping[str, Any], volatility_target: float) -> DynamicPositionScalingDecision:
    symbol = str(candidate.get("symbol") or "").upper()
    strategy = str(candidate.get("strategy_name") or candidate.get("strategy") or "unknown")
    base = _optional_float(candidate.get("base_notional") or candidate.get("target_notional")) or 0.0
    confidence = _clamp(_optional_float(candidate.get("confidence")) if candidate.get("confidence") is not None else 1.0)
    quality = _clamp(_optional_float(candidate.get("paper_scorecard_quality")) if candidate.get("paper_scorecard_quality") is not None else 1.0)
    regime_fit = _clamp(_optional_float(candidate.get("regime_fit")) if candidate.get("regime_fit") is not None else 1.0)
    volatility = _optional_float(candidate.get("volatility")) or volatility_target
    vol_scale = min(1.5, volatility_target / volatility) if volatility > 0 and volatility_target > 0 else 1.0
    scaled = base * confidence * quality * regime_fit * vol_scale
    return DynamicPositionScalingDecision(symbol, strategy, base, scaled, confidence, quality, regime_fit, volatility, "scaled")


def _rebalance_decision(
    symbol: str,
    line: PortfolioExposureLine | None,
    target: float,
    threshold: float,
) -> PortfolioRebalanceDecision:
    current = line.net_notional if line else 0.0
    delta = target - current
    if abs(delta) < threshold:
        action = "hold"
        reason = "rebalance_delta_below_threshold"
    elif delta > 0:
        action = "increase"
        reason = "increase_to_target"
    else:
        action = "reduce"
        reason = "reduce_to_target"
    return PortfolioRebalanceDecision(symbol, current, target, delta, action, reason)


def _symbol_conflict_decision(
    symbol: str,
    intents: Sequence[Mapping[str, Any]],
    allow_netting: bool,
) -> SymbolConflictDecision:
    long_strategies = tuple(str(intent.get("strategy_name") or intent.get("strategy") or "unknown") for intent in intents if _intent_notional(intent) > 0)
    short_strategies = tuple(str(intent.get("strategy_name") or intent.get("strategy") or "unknown") for intent in intents if _intent_notional(intent) < 0)
    net = sum(_intent_notional(intent) for intent in intents)
    has_conflict = bool(long_strategies and short_strategies)
    if not has_conflict:
        action = "allow"
        reason = "no_conflict"
    elif allow_netting:
        action = "net_to_target"
        reason = "netted_conflict"
    else:
        action = "block"
        reason = "opposing_symbol_exposure_conflict"
    return SymbolConflictDecision(symbol, long_strategies, short_strategies, net, action, reason)


def _strategy_stop_decision(
    row: Mapping[str, Any],
    max_drawdown_pct: float,
    max_data_drift_bps: float,
    max_slippage_breaches: int,
    max_rejects: int,
    max_missing_fills: int,
    cooldown_minutes: float,
    observed_at: datetime,
) -> StrategyStopTradingDecision:
    strategy = str(row.get("strategy_name") or row.get("strategy") or "unknown")
    drawdown_pct = _optional_float(row.get("drawdown_pct")) or 0.0
    data_drift_bps = _optional_float(row.get("data_drift_bps")) or 0.0
    slippage_breaches = int(row.get("slippage_breaches", 0) or 0)
    rejects = int(row.get("rejects", 0) or 0)
    missing_fills = int(row.get("missing_fills", 0) or 0)
    regime_match = bool(row.get("regime_match", True))
    reason = "passed"
    if drawdown_pct > max_drawdown_pct:
        reason = "strategy_drawdown_stop"
    elif abs(data_drift_bps) > max_data_drift_bps:
        reason = "strategy_data_drift_stop"
    elif slippage_breaches >= max_slippage_breaches:
        reason = "strategy_slippage_stop"
    elif rejects >= max_rejects:
        reason = "strategy_reject_stop"
    elif missing_fills >= max_missing_fills:
        reason = "strategy_missing_fill_stop"
    elif not regime_match:
        reason = "strategy_regime_mismatch_stop"
    stopped = reason != "passed"
    stopped_until = datetime.fromtimestamp(observed_at.timestamp() + cooldown_minutes * 60.0, tz=timezone.utc).isoformat() if stopped else None
    evidence = {
        "drawdown_pct": drawdown_pct,
        "data_drift_bps": data_drift_bps,
        "slippage_breaches": slippage_breaches,
        "rejects": rejects,
        "missing_fills": missing_fills,
        "regime_match": regime_match,
    }
    return StrategyStopTradingDecision(strategy, stopped, stopped_until, reason, evidence)


def _flatten_order(line: PortfolioExposureLine) -> Mapping[str, Any]:
    side = "SELL" if line.quantity > 0 else "BUY"
    return {
        "symbol": line.symbol,
        "side": side,
        "quantity": abs(line.quantity),
        "order_type": "MARKET",
        "time_in_force": "day",
        "reason": "portfolio_kill_switch_flatten",
        "strategy_name": line.strategy_name,
    }


def _account_risk_status(name: str, value: float, equity: float, limit_pct: float | None) -> AccountRiskPercentageStatus:
    pct = abs(value) / equity if equity else None
    reason = "passed"
    if limit_pct is not None and pct is not None and pct > limit_pct:
        reason = f"{name}_risk_pct_above_limit"
    elif pct is None:
        reason = "missing_account_equity"
    return AccountRiskPercentageStatus(name, value, pct, limit_pct, reason)


def _risk_dashboard_card(name: str, report: Any) -> RiskDashboardCard:
    payload = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    passed = bool(payload.get("passed", True))
    reason = str(payload.get("reason") or "unknown")
    severity = "info" if passed else "critical" if payload.get("locked") or payload.get("triggered") else "warning"
    value = payload.get("drawdown_pct") or payload.get("total_estimated_loss") or payload.get("total_var") or payload.get("gross_exposure")
    return RiskDashboardCard(name, passed, reason, severity, value)


def _var_cvar_line(line: PortfolioExposureLine, returns: Sequence[float], confidence: float) -> VarCvarExposureLine:
    losses = sorted(max(0.0, -(line.net_notional * float(ret))) for ret in returns)
    if not losses:
        return VarCvarExposureLine(line.symbol, line.net_notional, 0.0, 0.0, 0)
    index = min(len(losses) - 1, max(0, ceil(len(losses) * confidence) - 1))
    var = losses[index]
    tail = losses[index:] or [var]
    cvar = sum(tail) / len(tail)
    return VarCvarExposureLine(line.symbol, line.net_notional, var, cvar, len(losses))


def _intent_notional(intent: Mapping[str, Any]) -> float:
    side = str(intent.get("side") or "").upper()
    signed_notional = _optional_float(intent.get("signed_notional"))
    if signed_notional is not None:
        return signed_notional
    notional = _optional_float(intent.get("notional") or intent.get("target_notional") or intent.get("estimated_notional"))
    if notional is None:
        quantity = _optional_float(intent.get("quantity") or intent.get("qty")) or 0.0
        price = _optional_float(intent.get("price") or intent.get("estimated_price") or intent.get("limit_price")) or 0.0
        notional = abs(quantity * price)
    return -abs(notional) if side in {"SELL", "SHORT"} else abs(notional)


def _clamp(value: float | None, lower: float = 0.0, upper: float = 1.0) -> float:
    if value is None:
        return upper
    return max(lower, min(upper, value))


def _write_report(payload: dict, path: str | Path) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload["artifact_path"] = str(output)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output)


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)
