"""
Market-making strategy — ιδέα από warproxxx/poly-maker.

Two-sided quote γύρω από fair value (mid του book) με inventory skew: όσο πιο
ανισόρροπο είναι το inventory σου (πολύ UP έναντι DOWN ή αντίστροφα), τόσο πιο
ασύμμετρο γίνεται το quote σου ώστε να ενθαρρύνεται η επιστροφή σε ισορροπία.

ΣΗΜΑΝΤΙΚΟ — προσαρμογή στο υπάρχον execution model:
Ο υπάρχων PaperExecutor/LiveExecutor εκτελεί Intents ΑΜΕΣΩΣ στην τιμή τους
(δεν κάνει resting-order simulation ενός πραγματικού order book). Άρα αυτό
το module δεν "τοποθετεί" ένα bid+ask ζευγάρι που περιμένει fill· παράγει σε
κάθε κύκλο ΤΟ ΕΝΑ intent (BUY ή SELL) που έχει νόημα εκείνη τη στιγμή βάσει
της απόστασης τιμής-από-fair-value, με τρόπο ισοδύναμο σε αποτέλεσμα. Αν
αργότερα προστεθεί πραγματικό order-book resting (GTC orders + cancel/replace
στο CLOB), αυτό το module είναι το σημείο να το συνδέσεις.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional

from ..config import cfg
from ..strategy import Intent, Side, Strategy

log = logging.getLogger(__name__)


@dataclass
class MarketMakingConfig:
    enabled: bool = os.getenv("MM_ENABLED", "false").lower() == "true"
    # Μισό spread γύρω από fair value, σε τιμή (0.02 = 2 cents each side)
    half_spread: float = float(os.getenv("MM_HALF_SPREAD", "0.02"))
    # Μέγιστη ανοχή inventory imbalance (σε USD cost) πριν το skew γίνει max
    max_skew_inventory_usd: float = float(os.getenv("MM_MAX_SKEW_INVENTORY_USD", "60"))
    # Πόσο μετατοπίζεται το fair value ανά $ imbalance (κλιμακωμένο στο [0,1])
    skew_strength: float = float(os.getenv("MM_SKEW_STRENGTH", "0.05"))
    quote_size_usd: float = float(os.getenv("MM_QUOTE_SIZE_USD", "10"))
    min_quote_size_usd: float = 5.0
    # Ελάχιστο διάστημα ανάμεσα σε quotes για το ίδιο market (sec) — αποφυγή spam
    requote_interval_sec: float = float(os.getenv("MM_REQUOTE_INTERVAL_SEC", "6"))


class MarketMakingStrategy:
    """Δεν αντικαθιστά το arb/directional Strategy — τρέχει παράλληλα σε αυτό
    και μοιράζεται το ΙΔΙΟ inventory object ώστε τα exposure caps να ισχύουν
    σωρευτικά (δεν "τρώει" ξεχωριστό budget)."""

    name = "market_making"

    def __init__(self, shared_strategy: Strategy, config: Optional[MarketMakingConfig] = None):
        self.shared = shared_strategy  # ίδιο Strategy instance με το arb module -> ίδιο inventory
        self.cfg = config or MarketMakingConfig()
        self._last_quote_ts: dict[str, float] = {}

    def _skew(self, inv_up_cost: float, inv_down_cost: float) -> float:
        """Επιστρέφει τιμή στο [-1, 1]: θετικό = πολύ UP inventory (θέλουμε
        να πουλάμε UP / αγοράζουμε λιγότερο UP), αρνητικό = το αντίστροφο."""
        imbalance = inv_up_cost - inv_down_cost
        capped = max(-self.cfg.max_skew_inventory_usd, min(self.cfg.max_skew_inventory_usd, imbalance))
        return capped / self.cfg.max_skew_inventory_usd if self.cfg.max_skew_inventory_usd > 0 else 0.0

    def evaluate(self, state) -> List[Intent]:
        if not self.cfg.enabled:
            return []

        slug = state.market["slug"]
        now = time.time()
        if now - self._last_quote_ts.get(slug, 0.0) < self.cfg.requote_interval_sec:
            return []

        up_ask, down_ask = state.up_ask, state.down_ask
        if up_ask is None or down_ask is None:
            return []

        up_bid = state.up_book.best_bid
        down_bid = state.down_book.best_bid

        inv = self.shared.get_inv(slug)
        asset = state.market.get("asset", "BTC")
        exposure_cap = cfg.exposure_cap_for(asset)
        remaining = exposure_cap - inv.total_cost
        if remaining < self.cfg.min_quote_size_usd:
            return []

        # Fair value proxy: μέσο των δύο mids (up_mid + (1 - down_mid)) / 2
        up_mid = state.up_book.mid or up_ask
        down_mid = state.down_book.mid or down_ask
        fair_up = (up_mid + (1.0 - down_mid)) / 2.0

        skew = self._skew(inv.up_cost, inv.down_cost)  # >0: πολύ UP ήδη
        # Το fair value μετατοπίζεται ΚΑΤΑ της κατεύθυνσης του imbalance:
        # πολύ UP inventory -> θεωρούμε UP "ακριβότερο" εσωτερικά -> λιγότερο
        # πρόθυμοι να ξαναγοράσουμε UP, πιο πρόθυμοι για DOWN.
        skewed_fair_up = fair_up - skew * self.cfg.skew_strength

        our_bid_up = round(max(0.01, skewed_fair_up - self.cfg.half_spread), 2)
        our_bid_down = round(max(0.01, (1.0 - skewed_fair_up) - self.cfg.half_spread), 2)

        size = min(self.cfg.quote_size_usd, remaining)
        if size < self.cfg.min_quote_size_usd:
            return []

        intents: List[Intent] = []

        # Αγόρασε UP μόνο αν το δικό μας bid "νικάει" ή πιάνει το ask (δηλ.
        # έχει νόημα σαν immediate maker/taker fill αντί για κενό resting order)
        if our_bid_up >= up_ask and (up_bid is None or our_bid_up >= up_bid):
            intents.append(Intent(
                market_slug=slug,
                token_id=state.market["up_token_id"],
                side=Side.UP,
                action="BUY",
                price=min(our_bid_up, up_ask),
                size_usd=size,
                reason=f"MM quote fair_up={skewed_fair_up:.3f} skew={skew:.2f}",
            ))
        elif our_bid_down >= down_ask and (down_bid is None or our_bid_down >= down_bid):
            intents.append(Intent(
                market_slug=slug,
                token_id=state.market["down_token_id"],
                side=Side.DOWN,
                action="BUY",
                price=min(our_bid_down, down_ask),
                size_usd=size,
                reason=f"MM quote fair_down={1 - skewed_fair_up:.3f} skew={skew:.2f}",
            ))

        if intents:
            self._last_quote_ts[slug] = now
            log.info(f"[MM] {slug} fair_up={skewed_fair_up:.3f} skew={skew:.2f} -> {len(intents)} intent(s)")

        return intents
