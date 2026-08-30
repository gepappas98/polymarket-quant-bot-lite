"""
PostgreSQL-backed ledger (Priority 2) — ίδιο public interface με bot.ledger.Ledger
(record_intent, record_fill, record_outcome, win_rate, session_summary), ώστε
να είναι drop-in swap χωρίς να αλλάξει τίποτα σε bot/strategy.py,
bot/portfolio_gates.py, bot/executor.py, bot/status_server.py — όλα κάνουν
`from .ledger import ledger` και συνεχίζουν να δουλεύουν ίδια.

Ενεργοποίηση: LEDGER_BACKEND=postgres στο .env (βλ. bot/ledger.py::get_ledger).

ΔΕΝ έτρεξα αυτό το module κόντρα σε πραγματικό PostgreSQL — το sandbox εδώ
δεν έχει πρόσβαση δικτύου σε database (μόνο σε pypi/npm/github, βλ. allowed
domains). Δοκίμασέ το κόντρα στο δικό σου DB πριν το εμπιστευτείς σε
production· η SQL είναι απλή (ένας πίνακας, χωρίς exotic types) αλλά καλό
είναι να τρέξεις τουλάχιστον ένα record_intent/record_fill/record_outcome
κύκλο χειροκίνητα πρώτα.

Requires: psycopg[binary]>=3.1.0 (lazy import — δεν σπάει τίποτα αν λείπει
και LEDGER_BACKEND δεν είναι "postgres").
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from .ledger import LedgerEntry

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_entries (
    id          BIGSERIAL PRIMARY KEY,
    ts          DOUBLE PRECISION NOT NULL,
    kind        TEXT NOT NULL,
    market_slug TEXT NOT NULL,
    side        TEXT,
    price       DOUBLE PRECISION,
    size_usd    DOUBLE PRECISION,
    reason      TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    dry_run     BOOLEAN NOT NULL DEFAULT TRUE,
    pnl_usd     DOUBLE PRECISION,
    order_id    TEXT,
    meta        JSONB
);
CREATE INDEX IF NOT EXISTS ix_ledger_kind ON ledger_entries (kind);
CREATE INDEX IF NOT EXISTS ix_ledger_market_slug ON ledger_entries (market_slug);
CREATE INDEX IF NOT EXISTS ix_ledger_ts ON ledger_entries (ts);
"""


class PostgresLedger:
    """
    Ίδιο interface με bot.ledger.Ledger. `_entries` παραμένει διαθέσιμο ως
    in-memory cache (mirror του DB) ώστε bot/portfolio_gates.py, που διαβάζει
    `ledger._entries` απευθείας, να συνεχίσει να δουλεύει χωρίς αλλαγή· κάθε
    write ενημερώνει ΚΑΙ το DB ΚΑΙ αυτή τη λίστα.
    """

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("DATABASE_URL", "")
        self._entries: List[LedgerEntry] = []
        self._lock = threading.Lock()
        self._pool = None
        self._connect_and_migrate()

    def _connect_and_migrate(self) -> None:
        try:
            import psycopg
            from psycopg_pool import ConnectionPool
        except ImportError as e:
            raise RuntimeError(
                "LEDGER_BACKEND=postgres requires 'psycopg[binary]' and 'psycopg_pool' "
                "(pip install psycopg[binary] psycopg_pool)"
            ) from e

        if not self.dsn:
            raise RuntimeError("LEDGER_BACKEND=postgres requires DATABASE_URL to be set")

        self._pool = ConnectionPool(self.dsn, min_size=1, max_size=5, open=True)
        with self._pool.connection() as conn:
            conn.execute(_SCHEMA)
            conn.commit()
        log.info("[LEDGER] PostgreSQL backend connected and schema ensured")

    # -- low-level -----------------------------------------------------

    def append(self, entry: LedgerEntry) -> None:
        with self._lock:
            self._entries.append(entry)
        self._insert(entry)

    def _insert(self, entry: LedgerEntry) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO ledger_entries
                        (ts, kind, market_slug, side, price, size_usd, reason,
                         status, dry_run, pnl_usd, order_id, meta)
                    VALUES (%(ts)s, %(kind)s, %(market_slug)s, %(side)s, %(price)s,
                            %(size_usd)s, %(reason)s, %(status)s, %(dry_run)s,
                            %(pnl_usd)s, %(order_id)s, %(meta)s)
                    """,
                    {
                        "ts": entry.ts, "kind": entry.kind, "market_slug": entry.market_slug,
                        "side": entry.side, "price": entry.price, "size_usd": entry.size_usd,
                        "reason": entry.reason, "status": entry.status, "dry_run": entry.dry_run,
                        "pnl_usd": entry.pnl_usd, "order_id": entry.order_id,
                        "meta": _to_jsonb(entry.meta),
                    },
                )
                conn.commit()
        except Exception as e:
            log.error(f"[LEDGER] PostgreSQL insert failed (kept in-memory only): {e}")

    # -- recording helpers — identical signatures/behavior to bot.ledger.Ledger --

    def record_intent(self, intent, dry_run: bool, blocked: bool = False, block_reason: str = "") -> None:
        side = getattr(intent.side, "value", intent.side)
        self.append(LedgerEntry(
            ts=time.time(), kind="intent", market_slug=intent.market_slug, side=side,
            price=intent.price, size_usd=intent.size_usd,
            reason=block_reason or intent.reason,
            status="blocked" if blocked else "open", dry_run=dry_run,
        ))

    def record_fill(self, intent, shares: float, cost: float, order_id: str, dry_run: bool) -> None:
        side = getattr(intent.side, "value", intent.side)
        self.append(LedgerEntry(
            ts=time.time(), kind="fill", market_slug=intent.market_slug, side=side,
            price=intent.price, size_usd=cost, reason=intent.reason,
            status="filled", dry_run=dry_run, order_id=order_id, meta={"shares": shares},
        ))

    def record_outcome(self, market_slug: str, winner: Optional[str], pnl_usd: float,
                        meta: Optional[Dict[str, Any]] = None, dry_run: bool = True) -> None:
        self.append(LedgerEntry(
            ts=time.time(), kind="outcome", market_slug=market_slug, side=winner,
            pnl_usd=pnl_usd, status="closed", dry_run=dry_run, meta=meta,
        ))

    # -- read side -------------------------------------------------------
    # Υλοποιημένο πάνω στο in-memory mirror (ίδια σημασιολογία με το JSONL
    # backend) αντί για SQL aggregate query, ώστε συμπεριφορά/άκρες
    # περιπτώσεων (min_samples, prefix matching) να είναι ΤΑΥΤΟΣΗΜΕΣ με το
    # bot.ledger.Ledger. Αν το ledger μεγαλώσει πολύ (πολλαπλά process
    # restarts, πολύ μεγάλη ιστορία), αντικατέστησε αυτά τα δύο με SQL
    # queries πάνω στον πίνακα — το schema ήδη έχει τα indexes γι' αυτό.

    def win_rate(self, asset_prefix: Optional[str] = None, min_samples: int = 1) -> Optional[Dict[str, float]]:
        outcomes = [e for e in self._entries if e.kind == "outcome" and e.pnl_usd is not None]
        if asset_prefix:
            prefix = asset_prefix.lower()
            outcomes = [e for e in outcomes if e.market_slug.lower().startswith(prefix)]
        n = len(outcomes)
        if n < max(min_samples, 1):
            return None
        wins = sum(1 for e in outcomes if e.pnl_usd > 0)
        avg_pnl = sum(e.pnl_usd for e in outcomes) / n
        return {"win_rate_pct": round(100.0 * wins / n, 2), "sample_size": float(n), "avg_pnl": avg_pnl}

    def session_summary(self) -> Dict[str, Any]:
        intents = sum(1 for e in self._entries if e.kind == "intent")
        blocked = sum(1 for e in self._entries if e.status == "blocked")
        fills = [e for e in self._entries if e.kind == "fill"]
        dry_run_fills = sum(1 for e in fills if e.dry_run)
        live_fills = sum(1 for e in fills if not e.dry_run)
        total_usd = sum(e.size_usd or 0.0 for e in fills)
        return {
            "intents": intents, "blocked": blocked, "fills": len(fills),
            "dry_run_fills": dry_run_fills, "live_fills": live_fills, "total_usd": total_usd,
        }

    def load_recent(self, limit: int = 5000) -> None:
        """Προαιρετικό: φόρτωσε πρόσφατα entries από το DB στο in-memory mirror
        μετά από restart, ώστε win_rate()/session_summary() να έχουν ιστορία
        αμέσως αντί να ξεκινούν άδεια. Κάλεσέ το μία φορά μετά το __init__."""
        try:
            with self._pool.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT ts, kind, market_slug, side, price, size_usd, reason,
                           status, dry_run, pnl_usd, order_id, meta
                    FROM ledger_entries ORDER BY id DESC LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            with self._lock:
                self._entries = [
                    LedgerEntry(
                        ts=r[0], kind=r[1], market_slug=r[2], side=r[3], price=r[4],
                        size_usd=r[5], reason=r[6], status=r[7], dry_run=r[8],
                        pnl_usd=r[9], order_id=r[10], meta=r[11],
                    )
                    for r in reversed(rows)
                ]
            log.info(f"[LEDGER] loaded {len(self._entries)} recent entries from PostgreSQL")
        except Exception as e:
            log.error(f"[LEDGER] failed to load recent entries from PostgreSQL: {e}")


def _to_jsonb(meta: Optional[Dict[str, Any]]):
    if meta is None:
        return None
    import json
    return json.dumps(meta)
