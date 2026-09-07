# REAL Polymarket CLOB Historical Recorder

The recorder stores historical order-book state from **real public Polymarket CLOB data**. Its primary source is `wss://ws-subscriptions-clob.polymarket.com/ws/market`; the public `GET https://clob.polymarket.com/book?token_id=...` endpoint supplies initial snapshots and reconciliation after reconnects or stale periods. It has no Binance, random-price, synthetic-liquidity, generated-candle, or demo fallback.

Run it with real token metadata:

```bash
POLYMARKET_RECORDER_TOKENS='[{"token_id":"<real-token-id>","market_id":"<market-id>","condition_id":"<condition-id>","outcome":"Yes"}]' \
python -m bot.record_history
```

`POLYMARKET_RECORDER_DB` defaults to `data/polymarket_l2.db`. `POLYMARKET_RECORDER_RETENTION_DAYS=0` disables deletion; a positive value enables pruning. `POLYMARKET_RECORDER_STALE_SECONDS` defaults to 45, and `POLYMARKET_RECORDER_RECONNECT_MAX_SECONDS` defaults to 30. The process subscribes to all configured tokens, sends the required ten-second `PING`, reconnects with exponential backoff, and reconciles every token through REST before consuming deltas again.

## Schema and migration

The canonical migration is [`migrations/001_l2_book_snapshots.sql`](../migrations/001_l2_book_snapshots.sql). The `l2_book_snapshots` table contains `recorded_at_ms` (local persistence time), `timestamp_ms` (record time), `event_timestamp_ms` (Polymarket event time when supplied), `market_id`, optional `condition_id`, `token_id`, optional `outcome`, best bid/ask, mid, spread, aggregate bid/ask depth, complete `bids_json` and `asks_json` arrays, optional `sequence_id`, and `event_type`. Prices and sizes are strings to avoid floating-point loss and to preserve the exchange representation. Every row is constrained to `source='polymarket_clob'` and `data_source='REAL'`.

Rows are append-only snapshots after each accepted book or price-change event. The unique key `(token_id, sequence_id, event_type)` prevents replayed identified events from being recorded twice. Events without an exchange identifier are not assigned a fabricated identifier; they are processed as received. The local book applies `size=0` as a delete and replaces an existing price level for partial depth updates.

## Metrics

`RecorderMetrics` exposes `events_received`, `events_persisted`, `dropped_events`, `reconnects`, `stale_periods`, `rest_reconciliations`, and `recorder_lag_ms`. Missing timestamps remain `NULL`; no timestamp, price, or liquidity is invented.
