from src.config import AlpacaConfig, ExecutionConfig


def validate_execution_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in {"dry-run", "paper"}:
        raise ValueError("Execution mode must be 'dry-run' or 'paper'.")
    return normalized


def validate_alpaca_paper_safety(alpaca: AlpacaConfig, execution: ExecutionConfig, paper_trading: bool) -> None:
    """Prevent accidental non-paper Alpaca order routing."""

    mode = validate_execution_mode(execution.mode)
    if mode != "paper":
        return
    if not paper_trading:
        raise ValueError("Alpaca paper execution requires PAPER_TRADING=true.")
    if execution.allow_live_trading:
        return
    if "paper-api.alpaca.markets" not in alpaca.base_url.lower():
        raise ValueError(
            "Refusing to create an Alpaca broker for a non-paper URL. "
            "Use ALPACA_BASE_URL=https://paper-api.alpaca.markets or set ALLOW_LIVE_TRADING=true after live execution is implemented."
        )
