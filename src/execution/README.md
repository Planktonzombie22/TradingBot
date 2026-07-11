# Execution Package Layout

- `brokers/`: broker interfaces and concrete paper/Alpaca paper broker adapters.
- `orders/`: order IDs, broker intents, order capability plans, and replacement policy.
- `lifecycle/`: end-of-day policy and broker reconciliation snapshots/results.
- `safety/`: execution-mode and Alpaca paper-trading guard checks.

Use `from src.execution import ...` for the stable public surface. New internal code should import from these subpackages when the responsibility matters.
