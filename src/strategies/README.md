# Strategies Package Layout

- `core/`: strategy base class, parameter schemas, registry, and scheduling.
- `systems/`: concrete trading systems, including buy-and-hold, published replications, Tuff, and research systems.

The registry remains the main integration point. Use `from src.strategies import get_strategy, validate_strategy_params` from outside the package, and use `src.strategies.core` / `src.strategies.systems` internally when the distinction is useful.
