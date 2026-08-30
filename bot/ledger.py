"""
Append-only trade ledger — JSONL on disk (data/trades.jsonl by default) +
in-memory list for the current process (bot/portfolio_gates.py, bot/status_server.py
and bot/strategy.py's track-record gate all read ledger._entries directly).

Design mirrors what the rest of the codebase already assumes (see
tests/test_strategy.py, tests/test_portfolio_gates.py):
- `ledger.path` is a plain, monkeypatch-able attribute (not a property).
- `ledger._entries` is a plain list you can `.clear()` / `.append()` in tests.
- Every entry is a flat dataclass — no nested objects except the free-form
  `meta` dict, so it round-trips through JSON cleanly.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class LedgerEntry:
    ts: float
    kind: str                       # "intent" | "fill" | "outcome" | "kill"
    market_slug: str
    side: Optional[str] = None      # "UP" | "DOWN" | winner label for outcomes
    price: Optional[float] = None
    size_usd: Optional[float] = None
    reason: Optional[str] = None
    status: str = "open"            # "open" | "blocked" | "filled" | "closed" | "killed"
    dry_run: bool = True
    pnl_usd: Optional[float] = None
    order_id: Optional[str] = None
    meta: Optional[Dict[str, Any]] = field(default=None)


class Ledger:
    def __init__(self, path: Optional[Path] = None):
        self.path: Path = Path(path or os.getenv("LEDGER_PATH", "data/trades.jsonl"))
        self._entries: List[LedgerEntry] = []
        self._lock = threading.Lock()

    # -- low-level -----------------------------------------------------

    def append(self, entry: LedgerEntry) -> None:
        with self._lock:
            self._entries.append(entry)
        self._write(entry)

    def _write(self, entry: LedgerEntry) -> None:
        """Best-effort disk persistence — a write failure must never break
        trading logic, so this only logs and continues."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        except Exception as e:
            log.warning(f"ledger: failed to persist entry to {self.path}: {e}")

    # -- recording helpers, called from bot/executor.py -----------------

    def record_intent(
        self,
        intent,
        dry_run: bool,
        blocked: bool = False,
        block_reason: str = "",
    ) -> None:
        side = getattr(intent.side, "value", intent.side)
        self.append(LedgerEntry(
            ts=time.time(),
            kind="intent",
            market_slug=intent.market_slug,
            side=side,
            price=intent.price,
            size_usd=intent.size_usd,
            reason=block_reason or intent.reason,
            status="blocked" if blocked else "open",
            dry_run=dry_run,
        ))

    def record_fill(self, intent, shares: float, cost: float, order_id: str, dry_run: bool) -> None:
        side = getattr(intent.side, "value", intent.side)
        self.append(LedgerEntry(
            ts=time.time(),
            kind="fill",
            market_slug=intent.market_slug,
            side=side,
            price=intent.price,
            size_usd=cost,
            reason=intent.reason,
            status="filled",
            dry_run=dry_run,
            order_id=order_id,
            meta={"shares": shares},
        ))

    def record_outcome(
        self,
        market_slug: str,
        winner: Optional[str],
        pnl_usd: float,
        meta: Optional[Dict[str, Any]] = None,
        dry_run: bool = True,
    ) -> None:
        self.append(LedgerEntry(
            ts=time.time(),
            kind="outcome",
            market_slug=market_slug,
            side=winner,
            pnl_usd=pnl_usd,
            status="closed",
            dry_run=dry_run,
            meta=meta,
        ))

    # -- read-side, used by strategy.py / status_server.py / portfolio_gates.py --

    def win_rate(
        self,
        asset_prefix: Optional[str] = None,
        min_samples: int = 1,
    ) -> Optional[Dict[str, float]]:
        """None when there isn't enough history — callers must treat that as
        'don't gate on noise', not as an automatic block (see
        tests/test_strategy.py::TestTrackRecordGate::test_gate_does_not_apply_below_minimum_sample_size)."""
        outcomes = [e for e in self._entries if e.kind == "outcome" and e.pnl_usd is not None]
        if asset_prefix:
            prefix = asset_prefix.lower()
            outcomes = [e for e in outcomes if e.market_slug.lower().startswith(prefix)]
        n = len(outcomes)
        if n < max(min_samples, 1):
            return None
        wins = sum(1 for e in outcomes if e.pnl_usd > 0)
        avg_pnl = sum(e.pnl_usd for e in outcomes) / n
        return {
            "win_rate_pct": round(100.0 * wins / n, 2),
            "sample_size": float(n),
            "avg_pnl": avg_pnl,
        }

    def session_summary(self) -> Dict[str, Any]:
        intents = sum(1 for e in self._entries if e.kind == "intent")
        blocked = sum(1 for e in self._entries if e.status == "blocked")
        fills = [e for e in self._entries if e.kind == "fill"]
        dry_run_fills = sum(1 for e in fills if e.dry_run)
        live_fills = sum(1 for e in fills if not e.dry_run)
        total_usd = sum(e.size_usd or 0.0 for e in fills)
        return {
            "intents": intents,
            "blocked": blocked,
            "fills": len(fills),
            "dry_run_fills": dry_run_fills,
            "live_fills": live_fills,
            "total_usd": total_usd,
        }


def _build_ledger():
    """
    Factory: LEDGER_BACKEND=postgres (+ DATABASE_URL) selects bot.ledger_pg.PostgresLedger,
    anything else (or unset) keeps the default JSONL-backed Ledger.

    Import failures or a missing DATABASE_URL fall back to the JSONL Ledger
    with a loud warning — a bad Postgres config should degrade trading
    safety-wise (you keep a working ledger), not crash bot startup.
    """
    backend = os.getenv("LEDGER_BACKEND", "jsonl").lower()
    if backend != "postgres":
        return Ledger()
    try:
        from .ledger_pg import PostgresLedger
        pg = PostgresLedger()
        pg.load_recent()
        log.info("[LEDGER] using PostgreSQL backend (LEDGER_BACKEND=postgres)")
        return pg
    except Exception as e:
        log.error(f"[LEDGER] LEDGER_BACKEND=postgres failed ({e}) — falling back to JSONL ledger")
        return Ledger()


ledger = _build_ledger()
