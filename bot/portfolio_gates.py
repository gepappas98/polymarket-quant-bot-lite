"""
Portfolio-level protections — ROADMAP: "Max drawdown + low-profit pair locks
(Nexus-style portfolio protections)".

Both gates read from the outcome ledger that bot/resolver.py populates once a
window settles, so they only start affecting decisions once real outcomes
exist (before that, session_pnl() is 0 and no pair has enough history).

This also fixes a pre-existing bug: PaperExecutor.check_kill_switch() read
self.daily_pnl, which was initialized to 0.0 and never updated anywhere —
the kill switch could never actually fire. max_drawdown_gate() below reads
real settled PnL from the ledger instead.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .config import cfg
from .gates import GateResult
from .ledger import ledger

log = logging.getLogger(__name__)


def session_pnl() -> float:
    """Sum of all recorded outcome PnL since this process started."""
    return sum(e.pnl_usd or 0.0 for e in ledger._entries if e.kind == "outcome")


def max_drawdown_gate() -> GateResult:
    """
    Fail-closed portfolio kill switch: once cumulative session PnL breaches
    daily_loss_limit_usd (a negative number, e.g. -200), block ALL new
    intents for the rest of the process's life.
    """
    pnl = session_pnl()
    if pnl <= cfg.daily_loss_limit_usd:
        return GateResult(
            allowed=False,
            reason=f"max drawdown hit: session PnL ${pnl:.2f} <= limit ${cfg.daily_loss_limit_usd:.2f}",
        )
    return GateResult(allowed=True)


@dataclass
class PairLock:
    until: float
    reason: str


class LowProfitPairLock:
    """
    Nexus-style: if a specific market slug has lost money across its last
    N settled outcomes, lock it out for a cooldown window that's longer and
    performance-driven — distinct from CooldownLock in gates.py, which just
    rate-limits admission frequency regardless of results.
    """

    def __init__(self, lookback: int = 5, loss_threshold_usd: float = 0.0, lock_minutes: float = 30.0):
        self.lookback = lookback
        self.loss_threshold_usd = loss_threshold_usd
        self.lock_minutes = lock_minutes
        self._locks: Dict[str, PairLock] = {}

    def _recent_pnl(self, slug: str) -> Optional[float]:
        outcomes = [e for e in ledger._entries if e.kind == "outcome" and e.market_slug == slug]
        if len(outcomes) < self.lookback:
            return None
        recent = outcomes[-self.lookback:]
        return sum(e.pnl_usd or 0.0 for e in recent)

    def refresh(self, slug: str) -> None:
        """Call right after a new outcome is recorded for `slug`."""
        pnl = self._recent_pnl(slug)
        if pnl is not None and pnl <= self.loss_threshold_usd:
            reason = f"last {self.lookback} outcomes PnL=${pnl:.2f}"
            self._locks[slug] = PairLock(until=time.time() + self.lock_minutes * 60, reason=reason)
            log.warning(f"[PORTFOLIO] {slug} locked for {self.lock_minutes:.0f}min — {reason}")

    def check(self, slug: str) -> GateResult:
        lock = self._locks.get(slug)
        if lock is None:
            return GateResult(allowed=True)
        if lock.until <= time.time():
            del self._locks[slug]
            return GateResult(allowed=True)
        return GateResult(allowed=False, reason=f"low-profit pair lock: {lock.reason}")

    def status(self) -> Dict[str, str]:
        now = time.time()
        return {slug: lock.reason for slug, lock in self._locks.items() if lock.until > now}


pair_lock = LowProfitPairLock(
    lookback=int(os.getenv("PAIR_LOCK_LOOKBACK", "5")),
    loss_threshold_usd=float(os.getenv("PAIR_LOCK_LOSS_THRESHOLD_USD", "0")),
    lock_minutes=float(os.getenv("PAIR_LOCK_MINUTES", "30")),
)
