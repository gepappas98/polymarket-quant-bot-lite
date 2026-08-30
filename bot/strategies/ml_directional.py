"""
ML-driven directional strategy (Priority 3) — χρησιμοποιεί bot.ml_model.ProbabilityModel
αντί για το heuristic edge_up/edge_down του bot/strategy.py, με Kelly sizing
(bot.kelly, από το Priority 1 patch).

OFF by default (ML_STRATEGY_ENABLED=false). Αν δεν υπάρχει trained model
(bot.ml_model.ProbabilityModel.available == False), το evaluate() επιστρέφει
πάντα [] — ΔΕΝ κάνει silent fallback στο heuristic του Strategy (αυτό θα
έτρεχε ήδη παράλληλα ως ξεχωριστό plugin μέσω arbitrage.py, οπότε δεν
χρειάζεται duplicate λογική εδώ).

Ρητά ΔΕΝ αντικαθιστά bot/strategy.py::Strategy — τρέχει ΠΑΡΑΛΛΗΛΑ σε αυτό
(shared inventory) ως ένα επιπλέον, προαιρετικό, high-confidence-only sizing
path. Αν θες να δεις "τι θα έκανε ΜΟΝΟ το ML μοντέλο", απενεργοποίησε τα
άλλα directional plugins και άσε μόνο αυτό ενεργό.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from ..config import cfg
from ..kelly import kelly_size_usd, KellyInput
from ..ml_model import ProbabilityModel
from ..strategy import Intent, Side, Strategy

log = logging.getLogger(__name__)

STRATEGY_ENABLED_ENV = "ML_STRATEGY_ENABLED"


@dataclass
class MLDirectionalConfig:
    enabled: bool = os.getenv("ML_STRATEGY_ENABLED", "false").lower() == "true"
    # Ελάχιστη distance από 0.5 πριν θεωρηθεί "sinal" (αποφυγή coin-flip noise trades)
    min_confidence_edge: float = float(os.getenv("ML_MIN_CONFIDENCE_EDGE", "0.08"))
    fraction_of_kelly: float = float(os.getenv("ML_KELLY_FRACTION", "0.4"))


class MLDirectionalStrategy:
    name = "ml_directional"

    def __init__(self, shared_strategy: Strategy, config: Optional[MLDirectionalConfig] = None):
        self.shared = shared_strategy
        self.cfg = config or MLDirectionalConfig()
        self.model = ProbabilityModel.load()
        if self.cfg.enabled and not self.model.available:
            log.warning(
                "[ML] ML_STRATEGY_ENABLED=true αλλά δεν υπάρχει trained model "
                f"(ML_MODEL_PATH={os.getenv('ML_MODEL_PATH', 'data/ml_model.json')}) — "
                "θα παράγει 0 intents μέχρι να τρέξεις training (βλ. bot/ml_model.py)"
            )

    def evaluate(self, state) -> List[Intent]:
        if not self.cfg.enabled or not self.model.available:
            return []

        up_ask, down_ask = state.up_ask, state.down_ask
        if up_ask is None or down_ask is None:
            return []

        p_up = self.model.predict_win_prob_up(state)
        if p_up is None:
            return []

        edge_up = p_up - up_ask
        edge_down = (1.0 - p_up) - down_ask

        if edge_up <= self.cfg.min_confidence_edge and edge_down <= self.cfg.min_confidence_edge:
            return []

        slug = state.market["slug"]
        asset = state.market.get("asset", "BTC")
        inv = self.shared.get_inv(slug)
        exposure_cap = cfg.exposure_cap_for(asset)
        remaining = exposure_cap - inv.total_cost
        if remaining < 5:
            return []

        if edge_up > edge_down:
            side, price, win_prob = Side.UP, up_ask, p_up
            token_id = state.market["up_token_id"]
        else:
            side, price, win_prob = Side.DOWN, down_ask, 1.0 - p_up
            token_id = state.market["down_token_id"]

        size = kelly_size_usd(
            KellyInput(win_prob=win_prob, price=price, bankroll_usd=remaining),
            fraction_of_kelly=self.cfg.fraction_of_kelly,
        )
        if size < 5:
            return []

        log.info(f"[ML] {slug} {side.value} p_up={p_up:.3f} edge={max(edge_up, edge_down):.3f} size=${size:.1f}")
        return [Intent(
            market_slug=slug,
            token_id=token_id,
            side=side,
            action="BUY",
            price=price,
            size_usd=size,
            reason=f"ML p_up={p_up:.3f} edge={max(edge_up, edge_down):.3f}",
        )]


def build(shared_strategy):
    return MLDirectionalStrategy(shared_strategy=shared_strategy)
