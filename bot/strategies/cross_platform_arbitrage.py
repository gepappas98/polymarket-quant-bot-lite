"""
Cross-platform arbitrage — Polymarket ↔ Kalshi (Priority 3, πειραματικό).

ΕΜΒΕΛΕΙΑ ΑΥΤΟΥ ΤΟΥ MODULE — διάβασε πριν το ενεργοποιήσεις:
Αυτό ανιχνεύει arbitrage gap ανάμεσα σε μια Polymarket UP/DOWN αγορά και την
αντίστοιχη Kalshi YES/NO αγορά, και παράγει Intent ΜΟΝΟ για το Polymarket
σκέλος. ΔΕΝ εκτελεί το Kalshi σκέλος — αυτό θα απαιτούσε πλήρη Kalshi order
execution client (auth, order placement, fills, δικό του ledger) που είναι
εκτός scope αυτού του πρώτου περάσματος. Χωρίς να εκτελεστεί ΚΑΙ το Kalshi
σκέλος, αυτό ΔΕΝ είναι πραγματικό risk-free arbitrage — είναι ένα κατευθυντικό
sinal με βάση το πού "συμφωνεί λιγότερο" η Kalshi τιμή, με real directional
risk στο Polymarket leg μέχρι να υλοποιηθεί το ζευγάρι εκτέλεσης.

Πρακτικά: αυτό είναι σήμερα ένα ΚΑΤΕΥΘΥΝΤΙΚΟ σήμα (σαν ένα ακόμα directional
plugin), ενισχυμένο με εξωτερική πληροφορία τιμής, ΟΧΙ arbitrage χωρίς ρίσκο.
Το reason string στο κάθε intent το δηλώνει ρητά ώστε να ξεχωρίζει στο ledger.

Απαιτεί ΧΕΙΡΟΚΙΝΗΤΟ mapping Polymarket slug -> Kalshi ticker (δεν υπάρχει
αξιόπιστο αυτόματο matching ανάμεσα στις δύο πλατφόρμες για crypto up/down
markets σήμερα) μέσω KALSHI_MARKET_MAP (JSON env var ή αρχείο).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..config import cfg
from ..strategy import Intent, Side, Strategy
from ..venues.kalshi_client import KalshiClient

log = logging.getLogger(__name__)

STRATEGY_ENABLED_ENV = "KALSHI_ARB_ENABLED"


def _load_market_map() -> Dict[str, str]:
    """KALSHI_MARKET_MAP: είτε inline JSON (env var) είτε path σε JSON αρχείο.
    Schema: {"<polymarket_slug>": "<kalshi_ticker>"}"""
    raw = os.getenv("KALSHI_MARKET_MAP", "")
    if not raw:
        return {}
    try:
        if raw.strip().startswith("{"):
            return json.loads(raw)
        with open(raw, "r") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"[KALSHI_ARB] failed to load KALSHI_MARKET_MAP ({raw}): {e}")
        return {}


@dataclass
class CrossPlatformArbConfig:
    enabled: bool = os.getenv("KALSHI_ARB_ENABLED", "false").lower() == "true"
    min_gap: float = float(os.getenv("KALSHI_ARB_MIN_GAP", "0.04"))
    quote_size_usd: float = float(os.getenv("KALSHI_ARB_QUOTE_SIZE_USD", "15"))
    poll_interval_sec: float = float(os.getenv("KALSHI_ARB_POLL_INTERVAL_SEC", "10"))


class CrossPlatformArbitrageStrategy:
    name = "cross_platform_arbitrage"

    def __init__(self, shared_strategy: Strategy, config: Optional[CrossPlatformArbConfig] = None):
        self.shared = shared_strategy
        self.cfg = config or CrossPlatformArbConfig()
        self.market_map = _load_market_map()
        self.kalshi = KalshiClient()
        self._last_poll: Dict[str, float] = {}
        if self.cfg.enabled and not self.market_map:
            log.warning(
                "[KALSHI_ARB] KALSHI_ARB_ENABLED=true αλλά KALSHI_MARKET_MAP είναι άδειο — "
                "0 intents μέχρι να ορίσεις τουλάχιστον ένα polymarket_slug -> kalshi_ticker mapping"
            )

    def evaluate(self, state) -> List[Intent]:
        if not self.cfg.enabled:
            return []
        slug = state.market["slug"]
        ticker = self.market_map.get(slug)
        if not ticker:
            return []

        import time
        now = time.time()
        if now - self._last_poll.get(slug, 0.0) < self.cfg.poll_interval_sec:
            return []
        self._last_poll[slug] = now

        book = self.kalshi.get_orderbook(ticker)
        if book is None:
            return []

        up_ask, down_ask = state.up_ask, state.down_ask
        kalshi_yes_ask, kalshi_no_ask = book.yes_ask, book.no_ask
        if up_ask is None or down_ask is None or kalshi_yes_ask is None or kalshi_no_ask is None:
            return []

        # Θετικό gap_up: Kalshi τιμολογεί "YES" (== UP) πιο ακριβό από ό,τι Polymarket
        # τιμολογεί UP -> Polymarket UP φαίνεται "φθηνό" σχετικά.
        gap_up = kalshi_yes_ask - up_ask
        gap_down = kalshi_no_ask - down_ask

        asset = state.market.get("asset", "BTC")
        inv = self.shared.get_inv(slug)
        exposure_cap = cfg.exposure_cap_for(asset)
        remaining = exposure_cap - inv.total_cost
        size = min(self.cfg.quote_size_usd, remaining)
        if size < 5:
            return []

        if gap_up >= self.cfg.min_gap and gap_up > gap_down:
            log.info(f"[KALSHI_ARB] {slug} gap_up={gap_up:.3f} (kalshi_yes={kalshi_yes_ask:.3f} vs poly_up={up_ask:.3f})")
            return [Intent(
                market_slug=slug,
                token_id=state.market["up_token_id"],
                side=Side.UP,
                action="BUY",
                price=up_ask,
                size_usd=size,
                reason=f"cross-platform signal (Kalshi {ticker} YES ask {kalshi_yes_ask:.3f} vs Poly UP {up_ask:.3f}) — DIRECTIONAL, not hedged",
            )]
        if gap_down >= self.cfg.min_gap and gap_down > gap_up:
            log.info(f"[KALSHI_ARB] {slug} gap_down={gap_down:.3f} (kalshi_no={kalshi_no_ask:.3f} vs poly_down={down_ask:.3f})")
            return [Intent(
                market_slug=slug,
                token_id=state.market["down_token_id"],
                side=Side.DOWN,
                action="BUY",
                price=down_ask,
                size_usd=size,
                reason=f"cross-platform signal (Kalshi {ticker} NO ask {kalshi_no_ask:.3f} vs Poly DOWN {down_ask:.3f}) — DIRECTIONAL, not hedged",
            )]
        return []


def build(shared_strategy):
    return CrossPlatformArbitrageStrategy(shared_strategy=shared_strategy)
