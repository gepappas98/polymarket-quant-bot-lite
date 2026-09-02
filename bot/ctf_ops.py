"""
CTF inventory operations (split / merge / redeem) — v0.5 skeleton.

Live path is intentionally incomplete until wired to the Polymarket relayer
client. Paper mode records intents only. All mutating live calls require
MODE=live + double opt-in via gates.is_live_trading_allowed().

Official concepts:
  - split  pUSD -> equal YES + NO outcome tokens (inventory for two-sided quotes)
  - merge  equal YES + NO -> pUSD (free collateral)
  - redeem winning tokens after resolution -> pUSD
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .config import cfg
from .gates import is_live_trading_allowed

log = logging.getLogger(__name__)


@dataclass
class CtfResult:
    ok: bool
    op: str
    detail: str
    dry_run: bool = True
    tx_hash: Optional[str] = None


def _live_allowed() -> bool:
    try:
        return bool(is_live_trading_allowed().allowed)
    except Exception:
        return False


def split_complete_set(condition_id: str, amount_usd: float) -> CtfResult:
    """Split `amount_usd` pUSD into equal UP+DOWN tokens for condition_id."""
    if amount_usd <= 0:
        return CtfResult(False, "split", "amount must be positive")
    if cfg.mode != "live" or not _live_allowed():
        log.info(f"[CTF paper] split condition={condition_id[:16]}… amount={amount_usd:.2f}")
        return CtfResult(True, "split", f"paper split {amount_usd:.2f}", dry_run=True)
    # Live: integrate builder-relayer / CTF contract here
    log.warning(
        "[CTF] live split not implemented — refusing rather than sending unsigned txs "
        f"(condition={condition_id[:16]}… amount={amount_usd:.2f})"
    )
    return CtfResult(False, "split", "live split not implemented", dry_run=False)


def merge_complete_set(condition_id: str, amount_shares: float) -> CtfResult:
    """Merge equal UP+DOWN shares back to pUSD."""
    if amount_shares <= 0:
        return CtfResult(False, "merge", "amount must be positive")
    if cfg.mode != "live" or not _live_allowed():
        log.info(f"[CTF paper] merge condition={condition_id[:16]}… shares={amount_shares:.4f}")
        return CtfResult(True, "merge", f"paper merge {amount_shares:.4f}", dry_run=True)
    log.warning("[CTF] live merge not implemented — refusing")
    return CtfResult(False, "merge", "live merge not implemented", dry_run=False)


def redeem_positions(condition_id: str) -> CtfResult:
    """Redeem resolved winning tokens for condition_id."""
    if cfg.mode != "live" or not _live_allowed():
        log.info(f"[CTF paper] redeem condition={condition_id[:16]}…")
        return CtfResult(True, "redeem", "paper redeem", dry_run=True)
    log.warning("[CTF] live redeem not implemented — refusing")
    return CtfResult(False, "redeem", "live redeem not implemented", dry_run=False)


def maybe_merge_excess(condition_id: str, paired_shares: float, keep_shares: float = 0.0) -> CtfResult:
    """
    Helper: merge paired inventory above `keep_shares` to free collateral.
    No-op if nothing to merge.
    """
    excess = max(0.0, paired_shares - keep_shares)
    if excess < 1e-6:
        return CtfResult(True, "merge", "nothing to merge", dry_run=True)
    return merge_complete_set(condition_id, excess)
