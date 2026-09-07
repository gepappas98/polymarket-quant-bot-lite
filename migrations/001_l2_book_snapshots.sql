-- P0 REAL Polymarket CLOB historical recorder schema.
-- Source is strictly the public Polymarket CLOB market WebSocket plus /book reconciliation.
CREATE TABLE IF NOT EXISTS l2_book_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recorded_at_ms INTEGER NOT NULL,
  timestamp_ms INTEGER NOT NULL,
  event_timestamp_ms INTEGER,
  market_id TEXT NOT NULL,
  condition_id TEXT,
  token_id TEXT NOT NULL,
  outcome TEXT,
  best_bid TEXT,
  best_ask TEXT,
  mid TEXT,
  spread TEXT,
  bid_depth TEXT NOT NULL,
  ask_depth TEXT NOT NULL,
  bids_json TEXT NOT NULL,
  asks_json TEXT NOT NULL,
  sequence_id TEXT,
  event_type TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source = 'polymarket_clob'),
  data_source TEXT NOT NULL CHECK (data_source = 'REAL'),
  UNIQUE(token_id, sequence_id, event_type)
);
CREATE INDEX IF NOT EXISTS ix_l2_book_snapshots_token_time ON l2_book_snapshots(token_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS ix_l2_book_snapshots_market_time ON l2_book_snapshots(market_id, timestamp_ms);
