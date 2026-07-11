from dataclasses import dataclass
from importlib import metadata


@dataclass(frozen=True)
class DependencyCapability:
    package: str
    capability: str
    tier: str
    installed: bool
    version: str | None = None
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "capability": self.capability,
            "tier": self.tier,
            "installed": self.installed,
            "version": self.version,
            "recommendation": self.recommendation,
        }


DEPENDENCY_CAPABILITIES: tuple[tuple[str, str, str, str], ...] = (
    ("alpaca-py", "official_alpaca_trading_and_data_sdk", "broker", "Use for durable Alpaca paper/live API integration."),
    ("ccxt", "crypto_exchange_connectivity", "broker", "Use when crypto exchange execution becomes a first-class goal."),
    ("scipy", "scientific_statistics_and_optimization", "research", "Use for robust statistical tests and numeric routines."),
    ("statsmodels", "regression_cointegration_and_factor_tests", "research", "Use for pairs/stat-arb validation and factor analysis."),
    ("pyarrow", "parquet_columnar_storage", "research", "Use for fast historical data and artifact storage."),
    ("duckdb", "local_analytical_query_engine", "research", "Use for querying large backtest and market-data datasets."),
    ("optuna", "efficient_hyperparameter_optimization", "research", "Use after grid search becomes too slow or too blunt."),
    ("plotly", "interactive_reports_and_dashboards", "reporting", "Use for richer inspection dashboards."),
    ("rich", "structured_cli_progress", "reporting", "Use for readable long-running CLI research output."),
    ("numba", "compiled_indicator_and_backtest_hot_loops", "acceleration", "Add only after profiling identifies Python loops as a bottleneck."),
    ("polars", "fast_lazy_dataframe_research", "acceleration", "Add only if pandas becomes a data-processing bottleneck."),
)


def dependency_capability_report() -> list[DependencyCapability]:
    return [
        DependencyCapability(
            package=package,
            capability=capability,
            tier=tier,
            installed=version is not None,
            version=version,
            recommendation=recommendation,
        )
        for package, capability, tier, recommendation in DEPENDENCY_CAPABILITIES
        for version in (_version(package),)
    ]


def dependency_summary() -> dict:
    report = dependency_capability_report()
    return {
        "installed": [item.package for item in report if item.installed],
        "missing": [item.package for item in report if not item.installed],
        "by_tier": _by_tier(report),
        "capabilities": [item.to_dict() for item in report],
    }


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _by_tier(report: list[DependencyCapability]) -> dict[str, dict[str, list[str]]]:
    tiers: dict[str, dict[str, list[str]]] = {}
    for item in report:
        bucket = tiers.setdefault(item.tier, {"installed": [], "missing": []})
        bucket["installed" if item.installed else "missing"].append(item.package)
    return tiers
