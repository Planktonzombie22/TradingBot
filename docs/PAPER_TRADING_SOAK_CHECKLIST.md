# Paper Trading Soak Checklist

Before unattended Alpaca paper trading is considered ready:

1. Run several regular market sessions.
2. Confirm there are no unreconciled local/broker orders.
3. Restart during and after sessions and confirm state recovers cleanly.
4. Confirm logs contain no unhandled exceptions.
5. Confirm cash, positions, PnL, fills, and open orders match Alpaca paper statements.
6. Confirm kill switch, cancel-all, flatten, and disable-new-orders controls behave as expected.
7. Confirm alerts fire for startup, shutdown, orders, fills, rejects, halts, stale data, and exceptions.
