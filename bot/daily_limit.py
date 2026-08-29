"""
Daily-loss kill switch που επιβιώνει σε restart — ιδέα από poly-maker.

Το υπάρχον bot/portfolio_gates.py::max_drawdown_gate() μετράει session PnL
(μόνο ό,τι έγινε ΑΠΟ ΤΗΝ ΕΚΚΙΝΗΣΗ ΤΟΥ PROCESS). Αν ο bot κάνει restart (crash,
deploy, redeploy) μέσα στην ίδια ημέρα, το "session" μηδενίζεται και ο kill
switch ξεχνάει τις ζημιές πριν το restart — αυτό είναι το gap που καλύπτει
αυτό το module: κρατάει daily PnL σε ένα μικρό JSON file στο δίσκο, keyed by
ημερομηνία UTC, ώστε να μην "καθαρίζει" η ζημιά με ένα restart.

Χρήση: κάλεσε record_pnl(usd) κάθε φορά που ο resolver καταγράφει outcome
(ίδιο σημείο με το ledger.record_outcome), και check() πριν από κάθε evaluate
cycle -- ίδιο pattern με το max_drawdown_gate().
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import cfg
from .gates import GateResult

log = logging.getLogger(__name__)

_STATE_PATH = Path(os.getenv("DAILY_LIMIT_STATE_PATH", "data/daily_pnl.json"))
_lock = threading.Lock()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class DailyState:
    day: str
    pnl_usd: float = 0.0


def _load() -> DailyState:
    today = _today_key()
    try:
        raw = json.loads(_STATE_PATH.read_text())
        if raw.get("day") == today:
            return DailyState(day=today, pnl_usd=float(raw.get("pnl_usd", 0.0)))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning(f"[DAILY_LIMIT] failed to read state, starting fresh: {e}")
    return DailyState(day=today)  # νέα μέρα ή κανένα state -> reset στο 0


def _save(state: DailyState) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps({"day": state.day, "pnl_usd": state.pnl_usd}))
    except Exception as e:
        log.warning(f"[DAILY_LIMIT] failed to persist state: {e}")


def record_pnl(delta_usd: float) -> float:
    """Κάλεσέ το με το PnL ενός νέου settled outcome. Επιστρέφει το νέο daily total."""
    with _lock:
        state = _load()
        state.pnl_usd += delta_usd
        _save(state)
        return state.pnl_usd


def current_daily_pnl() -> float:
    with _lock:
        return _load().pnl_usd


def check() -> GateResult:
    """Fail-closed: αν η σημερινή σωρευτική ζημιά ξεπερνά το daily_loss_limit_usd,
    μπλόκαρε ΟΛΑ τα νέα intents μέχρι να αλλάξει η ημερομηνία UTC."""
    pnl = current_daily_pnl()
    if pnl <= cfg.daily_loss_limit_usd:
        return GateResult(
            allowed=False,
            reason=f"DAILY kill switch: today's PnL ${pnl:.2f} <= limit ${cfg.daily_loss_limit_usd:.2f}",
        )
    return GateResult(allowed=True)
