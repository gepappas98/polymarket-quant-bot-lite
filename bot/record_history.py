"""Run the REAL Polymarket CLOB historical recorder.

Usage:
  POLYMARKET_RECORDER_TOKENS='[{"token_id":"...","market_id":"...","outcome":"Yes"}]' \
  python -m bot.record_history
"""
from __future__ import annotations

import json
import logging
import os
import signal

from .historical_recorder import HistoricalRecorder, HttpRestBookClient, SnapshotStore, TokenMetadata
from .recorder_service import RecorderService


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    raw = os.environ.get("POLYMARKET_RECORDER_TOKENS")
    if not raw:
        raise SystemExit("POLYMARKET_RECORDER_TOKENS is required; provide real CLOB token metadata JSON")
    try:
        entries = json.loads(raw)
        tokens = [TokenMetadata(str(item["token_id"]), str(item["market_id"]), item.get("condition_id"), item.get("outcome")) for item in entries]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SystemExit(f"invalid POLYMARKET_RECORDER_TOKENS: {exc}") from exc
    if not tokens:
        raise SystemExit("at least one real Polymarket token is required")
    store = SnapshotStore(os.getenv("POLYMARKET_RECORDER_DB", "data/polymarket_l2.db"), int(os.getenv("POLYMARKET_RECORDER_RETENTION_DAYS", "0")) or None)
    recorder = HistoricalRecorder(
        tokens, store, HttpRestBookClient(os.getenv("POLYMARKET_CLOB_HOST", "https://clob.polymarket.com")), float(os.getenv("POLYMARKET_RECORDER_STALE_SECONDS", "45"))
    )
    service = RecorderService(recorder, os.getenv("POLYMARKET_CLOB_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/market"), float(os.getenv("POLYMARKET_RECORDER_RECONNECT_MAX_SECONDS", "30")))
    signal.signal(signal.SIGTERM, lambda *_: service.stop())
    signal.signal(signal.SIGINT, lambda *_: service.stop())
    service.run_forever()
    store.close()


if __name__ == "__main__":
    main()
