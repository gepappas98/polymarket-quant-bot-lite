"""
Core strategy logic inspired by the bosona-style system.

1. Complete-set / inventory pairing when UP + DOWN asks sum below threshold.
2. Directional tilt: use external price momentum + book imbalance to prefer one side.
3. Gradual building + ability to add the opposite side later (inventory management).
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

from .config import cfg
from .feeds import MarketState
from .ledger import ledger

log = logging.getLogger(__name__)


class Side(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass
class Intent:
    """A desired trade action."""
    market_slug: str
    token_id: str
    side: Side          # which outcome
    action: str         # "BUY"
    price: float
    size_usd: float
    reason: str
    is_arb_leg: bool = False


@dataclass
class Inventory:
    """Tracks our position in one market."""
    up_shares: float = 0.0
    down_shares: float = 0.0
    up_cost: float = 0.0
    down_cost: float = 0.0

    @property
    def net_exposure_usd(self) -> float:
        return abs(self.up_cost - self.down_cost)

    @property
    def total_cost(self) -> float:
        return self.up_cost + self.down_cost

    @property
    def paired(self) -> float:
        """How many complete sets we effectively hold."""
        return min(self.up_shares, self.down_shares)


class Strategy:
    def __init__(self):
        self.inventories: Dict[str, Inventory] = {}
        self.last_signals: Dict[str, dict] = {}

    def get_inv(self, slug: str) -> Inventory:
        if slug not in self.inventories:
            self.inventories[slug] = Inventory()
        return self.inventories[slug]

    def evaluate(self, state: MarketState) -> List[Intent]:
        """
        Main decision function.
        Returns a list of trade intents (may be empty).
        """
        intents: List[Intent] = []
        slug = state.market["slug"]
        asset = state.market.get("asset", "BTC")
        inv = self.get_inv(slug)
        exposure_cap = cfg.exposure_cap_for(asset)

        # Hard exposure limit (per-asset if configured, else the global default)
        if inv.total_cost >= exposure_cap:
            return intents

        up_ask = state.up_ask
        down_ask = state.down_ask
        if up_ask is None or down_ask is None:
            return intents

        # -------------------------------------------------
        # 1. Complete-set arbitrage / inventory pairing
        # -------------------------------------------------
        if state.arb_available:
            # Buy equal USD amounts of both sides (or remaining room)
            remaining = exposure_cap - inv.total_cost
            size = min(cfg.max_order_usd, remaining / 2)
            if size >= 5:  # minimum sensible size
                intents.append(Intent(
                    market_slug=slug,
                    token_id=state.market["up_token_id"],
                    side=Side.UP,
                    action="BUY",
                    price=up_ask,
                    size_usd=size,
                    reason=f"ARB pair (sum={state.sum_asks:.4f})",
                    is_arb_leg=True,
                ))
                intents.append(Intent(
                    market_slug=slug,
                    token_id=state.market["down_token_id"],
                    side=Side.DOWN,
                    action="BUY",
                    price=down_ask,
                    size_usd=size,
                    reason=f"ARB pair (sum={state.sum_asks:.4f})",
                    is_arb_leg=True,
                ))
                log.info(f"[ARB] {slug} sum={state.sum_asks:.4f} → buying both @ {size:.1f} USD each")
                return intents  # prioritize pure arb this cycle

        # -------------------------------------------------
        # 2. Directional tilt + inventory management
        # -------------------------------------------------
        # Simple momentum proxy: compare current Binance price movement
        # (In production you would track open price of the window + short-term delta)
        # Here we use a lightweight imbalance signal from the book + mid.

        up_mid = state.up_book.mid or up_ask
        down_mid = state.down_book.mid or down_ask

        # Book imbalance: more aggressive bids on one side → mild directional signal
        # (This is a placeholder; replace with real window-open delta + order-flow)
        imbalance = 0.0
        if state.up_book.best_bid and state.down_book.best_bid:
            imbalance = (state.up_book.best_bid - state.down_book.best_bid)

        # Fair-value heuristic: if one side is "cheap" relative to 0.5 after imbalance
        edge_up = 0.5 + imbalance * 0.5 - up_mid
        edge_down = 0.5 - imbalance * 0.5 - down_mid

        # Prefer the side with positive edge above threshold
        preferred: Optional[Side] = None
        if edge_up > cfg.min_directional_edge and edge_up > edge_down:
            preferred = Side.UP
        elif edge_down > cfg.min_directional_edge and edge_down > edge_up:
            preferred = Side.DOWN

        # Nexus-style track-record gate for directional (not pure arb)
        # Only apply when we have enough of our own outcome history.
        if preferred is not None:
            asset = (state.market.get("asset") or "btc").lower()
            wr = ledger.win_rate(asset_prefix=asset, min_samples=cfg.min_track_record_samples)
            if wr is not None and wr["win_rate_pct"] < cfg.min_track_record_win_pct:
                log.info(
                    f"[GATE] directional blocked for {slug}: track-record "
                    f"{wr['win_rate_pct']}% < {cfg.min_track_record_win_pct}% "
                    f"(n={int(wr['sample_size'])})"
                )
                preferred = None

        if preferred is None:
            # Still allow adding the under-represented side for inventory balancing
            if inv.up_shares > inv.down_shares * 1.5 and down_ask < 0.55:
                preferred = Side.DOWN
                reason_extra = "inventory rebalance"
            elif inv.down_shares > inv.up_shares * 1.5 and up_ask < 0.55:
                preferred = Side.UP
                reason_extra = "inventory rebalance"
            else:
                return intents
        else:
            reason_extra = f"directional edge={edge_up if preferred==Side.UP else edge_down:.3f}"

        # Size: smaller for pure directional, allow adding opposite later
        remaining = exposure_cap - inv.total_cost
        size = min(cfg.max_order_usd * 0.6, remaining)
        if size < 5:
            return intents

        token_id = (
            state.market["up_token_id"] if preferred == Side.UP
            else state.market["down_token_id"]
        )
        price = up_ask if preferred == Side.UP else down_ask

        # Prefer slightly aggressive limit (maker-ish) if configured
        if cfg.prefer_maker:
            price = max(0.01, price - 0.01)  # one tick better for maker

        intents.append(Intent(
            market_slug=slug,
            token_id=token_id,
            side=preferred,
            action="BUY",
            price=round(price, 2),
            size_usd=size,
            reason=reason_extra,
            is_arb_leg=False,
        ))
        log.info(f"[DIR] {slug} prefer {preferred.value} @ {price:.2f} size={size:.1f} ({reason_extra})")

        self.last_signals[slug] = {
            "edge_up": edge_up,
            "edge_down": edge_down,
            "imbalance": imbalance,
            "preferred": preferred.value if preferred else None,
            "ts": time.time(),
        }
        return intents

    def update_inventory(self, slug: str, side: Side, shares: float, cost: float):
        inv = self.get_inv(slug)
        if side == Side.UP:
            inv.up_shares += shares
            inv.up_cost += cost
        else:
            inv.down_shares += shares
            inv.down_cost += cost
        log.info(
            f"Inventory {slug}: UP={inv.up_shares:.1f} (${inv.up_cost:.1f}) "
            f"DOWN={inv.down_shares:.1f} (${inv.down_cost:.1f}) "
            f"paired≈{inv.paired:.1f}"
        )