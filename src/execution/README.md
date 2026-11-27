# Execution Package Layout

- `brokers/`: broker interfaces, concrete paper/Alpaca paper broker adapters, and the explicitly locked `LockedAlpacaLiveBroker` boundary for future live work.
- `orders/`: order IDs, broker intents, order capability plans, and replacement policy.
- `lifecycle/`: end-of-day policy and broker reconciliation snapshots/results.
- `safety/`: execution-mode, Alpaca paper-trading guard checks, and live-safety evidence builders for live unlock gates, account allowlists, hard caps, kill-switch drills, no-live-submit checks, secret/redaction checks, audit integrity, read-only reporting, approvals, emergency procedures, compliance awareness, and live-locked CI proof.

Use `from src.execution import ...` for the stable public surface. New internal code should import from these subpackages when the responsibility matters.
