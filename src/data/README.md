# Data Package Layout

- `providers/`: historical data provider adapters such as Alpaca and yfinance.
- `streams/`: live, polling, replay, sample, and event-stream abstractions.
- `quality/`: normalization, caching, corporate-action handling, and data-quality validation.
- `runtime/`: market calendars, data manager orchestration, and universe loading.

Use `from src.data import ...` in application code. Direct legacy paths such as `src.data.alpaca` and `src.data.calendar` are still aliased for compatibility.
