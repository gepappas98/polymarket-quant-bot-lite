"""
Outcome resolution — implements the ROADMAP's "Auto-redeem resolved winning
positions" item.

Once a market's countdown hits zero, its window is closed but the actual
UP/DOWN outcome isn't known until Polymarket settles it on-chain (usually
within seconds to a couple of minutes for these short crypto windows). This
module tracks such markets, polls Gamma until settlement prices appear, then
computes our paper/live PnL from the strategy's own inventory and records it
via ledger.record_outcome() — which is what feeds the dashboard's PnL chart
and the track-record gate (both showed zero/empty before this).

Scope: this settles our own bookkeeping only. Actually redeeming ERC-1155
conditional tokens on-chain for LIVE mode (calling the CTF contract) is a
separate, not-yet-implemented step — still open on the ROADMAP.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .ledger import ledger
from .market_finder import fetch_resolution
from .portfolio_gates import pair_lock
from .strategy import Strategy
from .daily_limit import record_pnl, current_daily_pnl
from . import metrics

log = logging.getLogger(__name__)


@dataclass
class PendingMarket:
    slug: str
    asset: str
    first_seen_closed: float


class Resolver:
    """Tracks markets whose window has ended and polls Gamma for settlement."""

    def __init__(
        self,
        strategy: Strategy,
        poll_interval_sec: float = 20.0,
        give_up_after_sec: float = 3600.0,
    ):
        self.strategy = strategy
        self.pending: Dict[str, PendingMarket] = {}
        self._last_poll: Dict[str, float] = {}
        self.poll_interval_sec = poll_interval_sec
        self.give_up_after_sec = give_up_after_sec

    def mark_closed(self, slug: str, asset: str) -> None:
        """Call once a market's countdown reaches zero (secondsToClose <= 0)."""
        if slug not in self.pending:
            self.pending[slug] = PendingMarket(slug=slug, asset=asset, first_seen_closed=time.time())
            log.info(f"[RESOLVE] {slug} window closed — awaiting settlement")

    def poll(self) -> None:
        """Call once per main loop cycle; records outcomes as soon as they're known."""
        now = time.time()
        for slug in list(self.pending.keys()):
            pm = self.pending[slug]

            if now - pm.first_seen_closed > self.give_up_after_sec:
                log.warning(f"[RESOLVE] {slug} unresolved after {self.give_up_after_sec:.0f}s — giving up")
                del self.pending[slug]
                continue

            if now - self._last_poll.get(slug, 0) < self.poll_interval_sec:
                continue
            self._last_poll[slug] = now

            result = fetch_resolution(slug)
            if not result or not result.get("resolved"):
                continue  # not settled yet, or Gamma fetch failed — try again next poll

            inv = self.strategy.inventories.get(slug)
            if inv is None or inv.total_cost <= 0:
                del self.pending[slug]  # we never held a position here
                continue

            winner = result.get("winner")
            if winner == "UP":
                payout = inv.up_shares
            elif winner == "DOWN":
                payout = inv.down_shares
            else:
                log.warning(f"[RESOLVE] {slug} closed but winner unclear from Gamma — skipping PnL record")
                del self.pending[slug]
                continue

            pnl = round(payout - inv.total_cost, 4)
            ledger.record_outcome(
                market_slug=slug,
                winner=winner,
                pnl_usd=pnl,
                meta={
                    "asset": pm.asset,
                    "up_shares": round(inv.up_shares, 4),
                    "down_shares": round(inv.down_shares, 4),
                    "total_cost": round(inv.total_cost, 4),
                },
            )
            log.info(f"[RESOLVE] {slug} winner={winner} pnl=${pnl:+.2f}")
            record_pnl(pnl)  # persists across restarts — see bot/daily_limit.py
            metrics.record_outcome(winner=winner, pnl_usd=pnl)
            metrics.set_daily_pnl(current_daily_pnl())
            pair_lock.refresh(slug)
            del self.pending[slug]
            self.strategy.inventories.pop(slug, None)
