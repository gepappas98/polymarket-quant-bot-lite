"""Persistent REAL Polymarket CLOB L2 historical recorder.

The recorder is deliberately separate from execution.  It consumes only the public
Polymarket CLOB market WebSocket and the public CLOB ``/book`` REST endpoint;
there is no synthetic/demo/fallback data path.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

import requests

log = logging.getLogger(__name__)

REAL_SOURCE = "polymarket_clob"
REAL_DATA_SOURCE = "REAL"
DEFAULT_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
DEFAULT_REST_URL = "https://clob.polymarket.com"


class RestBookClient(Protocol):
    def fetch_book(self, token_id: str) -> Mapping[str, Any]: ...


class HttpRestBookClient:
    def __init__(self, base_url: str = DEFAULT_REST_URL, timeout: float = 10.0, session: Any = None):
        self.base_url, self.timeout, self.session = base_url.rstrip("/"), timeout, session or requests.Session()

    def fetch_book(self, token_id: str) -> Mapping[str, Any]:
        response = self.session.get(f"{self.base_url}/book", params={"token_id": token_id}, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("Polymarket /book response must be an object")
        return payload


@dataclass(frozen=True)
class TokenMetadata:
    token_id: str
    market_id: str
    condition_id: str | None = None
    outcome: str | None = None


@dataclass
class BookState:
    token_id: str
    bids: dict[str, Decimal] = field(default_factory=dict)
    asks: dict[str, Decimal] = field(default_factory=dict)
    last_event_timestamp_ms: int | None = None
    last_event_id: str | None = None
    last_update_monotonic: float = field(default_factory=time.monotonic)
    initialized: bool = False

    def replace(self, bids: Iterable[Mapping[str, Any]], asks: Iterable[Mapping[str, Any]], event_ts: int | None, event_id: str | None) -> None:
        self.bids, self.asks = _levels(bids), _levels(asks)
        self.last_event_timestamp_ms, self.last_event_id = event_ts, event_id
        self.last_update_monotonic, self.initialized = time.monotonic(), True

    def change(self, price: Any, size: Any, side: Any, event_ts: int | None, event_id: str | None) -> None:
        p = _decimal(price)
        if p is None or p <= 0 or str(side).upper() not in {"BUY", "SELL"}:
            raise ValueError("invalid price change")
        s = _decimal(size)
        if s is None or s < 0:
            raise ValueError("invalid price-change size")
        levels = self.bids if str(side).upper() == "BUY" else self.asks
        key = _decimal_key(p)
        if s == 0:
            levels.pop(key, None)
        else:
            levels[key] = s
        self.last_event_timestamp_ms, self.last_event_id = event_ts, event_id
        self.last_update_monotonic, self.initialized = time.monotonic(), True

    def stale(self, after_seconds: float) -> bool:
        return not self.initialized or time.monotonic() - self.last_update_monotonic > after_seconds

    def snapshot(self) -> dict[str, Any]:
        bids = [{"price": k, "size": _decimal_string(v)} for k, v in sorted(self.bids.items(), key=lambda x: Decimal(x[0]), reverse=True)]
        asks = [{"price": k, "size": _decimal_string(v)} for k, v in sorted(self.asks.items(), key=lambda x: Decimal(x[0]))]
        bid = Decimal(bids[0]["price"]) if bids else None
        ask = Decimal(asks[0]["price"]) if asks else None
        bid_depth = sum((Decimal(x["size"]) for x in bids), Decimal(0))
        ask_depth = sum((Decimal(x["size"]) for x in asks), Decimal(0))
        mid = (bid + ask) / 2 if bid is not None and ask is not None else None
        spread = ask - bid if bid is not None and ask is not None else None
        return {"best_bid": _decimal_string(bid), "best_ask": _decimal_string(ask), "mid": _decimal_string(mid), "spread": _decimal_string(spread), "bid_depth": _decimal_string(bid_depth), "ask_depth": _decimal_string(ask_depth), "bids": bids, "asks": asks}


def _decimal(value: Any) -> Decimal | None:
    try:
        if value is None or isinstance(value, bool): return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError): return None


def _decimal_key(value: Decimal) -> str:
    return format(value, "f")


def _decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _levels(levels: Iterable[Mapping[str, Any]]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for level in levels or []:
        if not isinstance(level, Mapping): continue
        price, size = _decimal(level.get("price")), _decimal(level.get("size"))
        if price is not None and size is not None and price > 0 and size > 0:
            result[_decimal_key(price)] = size
    return result


def _timestamp_ms(value: Any) -> int | None:
    if value is None: return None
    try:
        n = int(value)
        return n * 1000 if n < 10_000_000_000 else n
    except (TypeError, ValueError): return None


def _event_id(message: Mapping[str, Any], payload: Mapping[str, Any], change: Mapping[str, Any] | None = None) -> str | None:
    for source in (change or {}, payload, message):
        for key in ("event_id", "eventId", "id", "hash", "transaction_hash", "transactionHash"):
            if source.get(key) is not None: return str(source[key])
    return None


SCHEMA = """CREATE TABLE IF NOT EXISTS l2_book_snapshots (
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
CREATE INDEX IF NOT EXISTS ix_l2_snapshots_token_time ON l2_book_snapshots(token_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS ix_l2_snapshots_market_time ON l2_book_snapshots(market_id, timestamp_ms);
"""


class SnapshotStore:
    def __init__(self, path: str | Path, retention_days: int | None = None):
        self.path = str(path)
        self.retention_days = retention_days
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def prune(self, now_ms: int | None = None) -> int:
        """Delete only records older than configured retention; disabled by default."""
        if not self.retention_days or self.retention_days <= 0:
            return 0
        cutoff = (now_ms or int(time.time() * 1000)) - self.retention_days * 86_400_000
        with self._lock:
            cursor = self.conn.execute("DELETE FROM l2_book_snapshots WHERE recorded_at_ms < ?", (cutoff,))
            self.conn.commit()
            return cursor.rowcount

    def persist(self, row: Mapping[str, Any]) -> bool:
        with self._lock:
            try:
                cursor = self.conn.execute("""INSERT OR IGNORE INTO l2_book_snapshots
                (recorded_at_ms,timestamp_ms,event_timestamp_ms,market_id,condition_id,token_id,outcome,best_bid,best_ask,mid,spread,bid_depth,ask_depth,bids_json,asks_json,sequence_id,event_type,source,data_source)
                VALUES (:recorded_at_ms,:timestamp_ms,:event_timestamp_ms,:market_id,:condition_id,:token_id,:outcome,:best_bid,:best_ask,:mid,:spread,:bid_depth,:ask_depth,:bids_json,:asks_json,:sequence_id,:event_type,:source,:data_source)""", row)
                inserted = cursor.rowcount == 1
                self.conn.commit()
                return inserted
            except sqlite3.Error:
                self.conn.rollback()
                raise

    def close(self) -> None: self.conn.close()


@dataclass
class RecorderMetrics:
    events_received: int = 0
    events_persisted: int = 0
    dropped_events: int = 0
    reconnects: int = 0
    stale_periods: int = 0
    rest_reconciliations: int = 0
    recorder_lag_ms: int = 0


class HistoricalRecorder:
    def __init__(self, tokens: Iterable[TokenMetadata], store: SnapshotStore, rest: RestBookClient, stale_after_seconds: float = 45.0, clock: Callable[[], float] = time.time):
        self.tokens = {t.token_id: t for t in tokens}
        self.store, self.rest, self.stale_after_seconds, self.clock = store, rest, stale_after_seconds, clock
        self.books = {token_id: BookState(token_id) for token_id in self.tokens}
        self.metrics = RecorderMetrics()
        self._seen_events: set[tuple[str, str, str]] = set()

    def reconcile(self, token_id: str) -> None:
        metadata = self.tokens[token_id]
        payload = self.rest.fetch_book(token_id)
        book = self.books[token_id]
        book.replace(payload.get("bids") or [], payload.get("asks") or [], _timestamp_ms(payload.get("timestamp")), str(payload.get("hash")) if payload.get("hash") else None)
        self.metrics.rest_reconciliations += 1
        self._persist(metadata, book, "rest_reconciliation", book.last_event_id, book.last_event_timestamp_ms)

    def handle_message(self, raw: str | bytes | Mapping[str, Any]) -> None:
        self.metrics.events_received += 1
        try:
            message = json.loads(raw) if isinstance(raw, (str, bytes)) else dict(raw)
            if isinstance(message, list):
                for item in message:
                    if isinstance(item, Mapping): self.handle_message(item)
                return
            if not isinstance(message, Mapping): raise ValueError("event must be an object")
            event_type = str(message.get("event_type") or message.get("type") or "")
            if event_type == "book": self._handle_book(message)
            elif event_type == "price_change": self._handle_price_change(message)
            else: self.metrics.dropped_events += 1
        except (ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
            self.metrics.dropped_events += 1
            log.warning("Dropping malformed Polymarket CLOB event: %s", exc)

    def _handle_book(self, message: Mapping[str, Any]) -> None:
        token_id = str(message.get("asset_id") or message.get("assetId") or "")
        if token_id not in self.tokens: self.metrics.dropped_events += 1; return
        ts = _timestamp_ms(message.get("timestamp")); eid = _event_id(message, message)
        if self._duplicate(token_id, "book", eid): return
        book = self.books[token_id]; book.replace(message.get("bids") or [], message.get("asks") or [], ts, eid)
        self._persist(self.tokens[token_id], book, "book", eid, ts)

    def _handle_price_change(self, message: Mapping[str, Any]) -> None:
        ts = _timestamp_ms(message.get("timestamp"))
        for change in message.get("price_changes") or message.get("priceChanges") or []:
            if not isinstance(change, Mapping): self.metrics.dropped_events += 1; continue
            token_id = str(change.get("asset_id") or change.get("assetId") or change.get("tokenId") or "")
            if token_id not in self.tokens: self.metrics.dropped_events += 1; continue
            eid = _event_id(message, message, change)
            if self._duplicate(token_id, "price_change", eid): continue
            try: self.books[token_id].change(change.get("price"), change.get("size"), change.get("side"), ts, eid)
            except ValueError: self.metrics.dropped_events += 1; continue
            self._persist(self.tokens[token_id], self.books[token_id], "price_change", eid, ts)

    def _duplicate(self, token_id: str, event_type: str, eid: str | None) -> bool:
        if eid is None: return False
        key = (token_id, event_type, eid)
        if key in self._seen_events: self.metrics.dropped_events += 1; return True
        self._seen_events.add(key)
        return False

    def _persist(self, metadata: TokenMetadata, book: BookState, event_type: str, eid: str | None, event_ts: int | None) -> None:
        snapshot = book.snapshot(); now_ms = int(self.clock() * 1000)
        self.metrics.recorder_lag_ms = max(0, now_ms - event_ts) if event_ts is not None else 0
        row = {"recorded_at_ms": now_ms, "timestamp_ms": now_ms, "event_timestamp_ms": event_ts, "market_id": metadata.market_id, "condition_id": metadata.condition_id, "token_id": metadata.token_id, "outcome": metadata.outcome, **snapshot, "bids_json": json.dumps(snapshot["bids"], separators=(",", ":")), "asks_json": json.dumps(snapshot["asks"], separators=(",", ":")), "sequence_id": eid, "event_type": event_type, "source": REAL_SOURCE, "data_source": REAL_DATA_SOURCE}
        row.pop("bids"); row.pop("asks")
        if self.store.persist(row): self.metrics.events_persisted += 1

    def mark_stale(self) -> list[str]:
        stale = [token_id for token_id, book in self.books.items() if book.stale(self.stale_after_seconds)]
        if stale: self.metrics.stale_periods += len(stale)
        return stale

    def reconcile_stale(self) -> None:
        for token_id in self.mark_stale():
            try: self.reconcile(token_id)
            except Exception as exc: log.warning("REST reconciliation failed for %s: %s", token_id, exc)


__all__ = ["BookState", "HistoricalRecorder", "HttpRestBookClient", "REAL_DATA_SOURCE", "REAL_SOURCE", "RecorderMetrics", "SCHEMA", "SnapshotStore", "TokenMetadata"]
