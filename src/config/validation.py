from dataclasses import dataclass, field
from typing import List

from .profiles import RuntimeConfig


@dataclass(frozen=True)
class EnvironmentValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            raise ValueError("; ".join(self.errors))


def validate_runtime_environment(config: RuntimeConfig) -> EnvironmentValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    provider = config.data.provider.lower()
    execution_mode = config.execution.mode.lower()

    if execution_mode not in {"dry-run", "paper"}:
        errors.append("EXECUTION_MODE must be dry-run or paper.")

    if provider == "alpaca" or execution_mode == "paper":
        if not config.alpaca.api_key:
            errors.append("ALPACA_API_KEY is required for Alpaca data or paper execution.")
        if not config.alpaca.secret_key:
            errors.append("ALPACA_SECRET_KEY is required for Alpaca data or paper execution.")

    if execution_mode == "paper":
        if not config.paper_trading:
            errors.append("PAPER_TRADING must be true for paper execution.")
        if not config.execution.allow_live_trading and "paper-api.alpaca.markets" not in config.alpaca.base_url.lower():
            errors.append("ALPACA_BASE_URL must point to the Alpaca paper endpoint for paper execution.")

    if config.execution.allow_live_trading:
        warnings.append("ALLOW_LIVE_TRADING is enabled, but live execution is not implemented.")

    return EnvironmentValidationResult(errors=errors, warnings=warnings)
