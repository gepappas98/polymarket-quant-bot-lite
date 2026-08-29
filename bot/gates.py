"""
Safety gates inspired by Nexus Bot (nexusBotGates.ts).

Design principles ported:
- Fail CLOSED when a check is unavailable (never silently allow trades).
- Double opt-in for live trading (MODE=live is not enough).
- Per-market cooldown lock (process-local, race-safe for single process).
- Explicit reasons for every block.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .config import cfg

log = logging.getLogger(__name__)

# Nexus-style: live requires BOTH mode=live AND an explicit confirmation string.
LIVE_CONFIRM_PHRASE = "I_UNDERSTAND_THE_RISK"


@dataclass
class GateResult:
    allowed: bool
    reason: Optional[str] = None


class CooldownLock:
    """Per-market admission lock. Single-process atomic via lock + dict."""

    def __init__(self, minutes: float = 5.0):
        self.minutes = minutes
        self._until: Dict[str, float] = {}
        self._lock = threading.Lock()

    def check_and_lock(self, key: str) -> GateResult:
        now = time.time()
        with self._lock:
            until = self._until.get(key, 0.0)
            if until > now:
                return GateResult(
                    allowed=False,
                    reason=f"cooldown active until {time.strftime('%H:%M:%S', time.localtime(until))}",
                )
            self._until[key] = now + self.minutes * 60
            return GateResult(allowed=True)

    def clear(self, key: str) -> None:
        with self._lock:
            self._until.pop(key, None)

    def status(self) -> Dict[str, float]:
        now = time.time()
        with self._lock:
            return {k: v for k, v in self._until.items() if v > now}

    def get_until(self, key: str) -> Optional[float]:
        """Return the unix timestamp a market's cooldown lifts, or None if not locked."""
        now = time.time()
        with self._lock:
            until = self._until.get(key)
            return until if until and until > now else None


# Global cooldown (per market slug)
cooldown = CooldownLock(minutes=float(os.getenv("COOLDOWN_MINUTES", "3")))


def is_live_trading_allowed() -> GateResult:
    """
    Double opt-in (Nexus pattern):
      MODE=live
      LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISK
      + private key present
    Anything else → paper / blocked.
    """
    mode = (os.getenv("MODE") or cfg.mode or "paper").lower()
    confirm = os.getenv("LIVE_TRADING_CONFIRM", "")
    has_key = bool(cfg.private_key or os.getenv("POLYMARKET_PRIVATE_KEY"))

    if mode != "live":
        return GateResult(allowed=False, reason="MODE is not live (paper/safe)")
    if confirm != LIVE_CONFIRM_PHRASE:
        return GateResult(
            allowed=False,
            reason=f"LIVE_TRADING_CONFIRM must be exactly '{LIVE_CONFIRM_PHRASE}'",
        )
    if not has_key:
        return GateResult(allowed=False, reason="POLYMARKET_PRIVATE_KEY missing")
    return GateResult(allowed=True)


def gate_intent(market_slug: str, size_usd: float, is_arb: bool = False) -> GateResult:
    """
    Run all process-local gates before any order is sent.
    Fail closed on any problem.
    """
    # Live gate
    if cfg.mode == "live":
        live = is_live_trading_allowed()
        if not live.allowed:
            return live

    # Size sanity
    if size_usd <= 0 or size_usd > cfg.max_order_usd * 1.01:
        return GateResult(allowed=False, reason=f"size_usd {size_usd} outside limits")

    # Cooldown (lighter for pure arb pairs)
    cd_minutes = 1.0 if is_arb else cooldown.minutes
    # Temporarily adjust for arb
    original = cooldown.minutes
    try:
        if is_arb:
            cooldown.minutes = min(1.0, original)
        result = cooldown.check_and_lock(market_slug)
        if not result.allowed:
            return result
    finally:
        cooldown.minutes = original

    return GateResult(allowed=True)