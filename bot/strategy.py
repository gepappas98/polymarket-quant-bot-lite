"""
Core strategy logic inspired by the bosona / high-volume Up/Down maker style.

1. Complete-set accumulation when UP + DOWN are cheap (instant pair or staggered).
2. Second-side lag: after a one-sided fill, actively work the opposite leg.
3. Residual directional tilt on unmatched inventory + book/spot imbalance.
4. Inventory accounting via bot.inventory (paired / residual / avg set cost).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from .config import cfg
from .feeds import MarketState
from .inventory import InventoryBook, MarketInventory
from .swarm import SwarmConfig, filter_intents
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
    side: Side
    action: str  # "BUY"
    price: float
    size_usd: float
    reason: str
    is_arb_leg: bool = False


# Backward-compatible alias used by market_making / older tests
@dataclass
class Inventory:
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
        return min(self.up_shares, self.down_shares)


def _depth_ok(state: MarketState, side: Side) -> bool:
    """Optional thin-book reject (MIN_BOOK_DEPTH_USD)."""
    min_d = getattr(cfg, "min_book_depth_usd", 0.0) or 0.0
    if min_d <= 0:
        return True
    book = state.up_book if side == Side.UP else state.down_book
    if not book or not book.best_ask:
        return False
    size = getattr(book, "best_ask_size", None)
    if size is None:
        return True
    return (float(size) * float(book.best_ask)) >= min_d


class Strategy:
    def __init__(self) -> None:
        self.book = InventoryBook()
        self.last_signals: Dict[str, dict] = {}
        self.inventories: Dict[str, Inventory] = {}

    def get_inv(self, slug: str) -> Inventory:
        """Legacy Inventory view synced from InventoryBook."""
        mi = self.book.get(slug)
        leg = self.inventories.get(slug)
        if leg is None:
            leg = Inventory()
            self.inventories[slug] = leg
        leg.up_shares = mi.up_shares
        leg.down_shares = mi.down_shares
        leg.up_cost = mi.up_cost
        leg.down_cost = mi.down_cost
        return leg

    def market_inv(self, slug: str) -> MarketInventory:
        return self.book.get(slug)

    def next_set_id(self, slug: str) -> str:
        """Monotonic complete-set id per market for ledger correlation."""
        if not hasattr(self, "_set_seq"):
            self._set_seq = {}
        n = self._set_seq.get(slug, 0) + 1
        self._set_seq[slug] = n
        return f"{slug}:set:{n}"

    def _swarm_filter(self, state: MarketState, intents: List[Intent]) -> List[Intent]:

        """Apply module-swarm consensus; no-op if SWARM_ENABLED=false."""
        if not intents:
            return intents
        if not getattr(cfg, "swarm_enabled", True):
            return intents
        mi = self.market_inv(state.market["slug"])
        scfg = SwarmConfig(
            enabled=True,
            threshold=getattr(cfg, "consensus_threshold", 0.70),
        )
        return filter_intents(intents, state, mi, cfg=scfg)


    def evaluate(self, state: MarketState) -> List[Intent]:
        intents: List[Intent] = []
        slug = state.market["slug"]
        asset = state.market.get("asset", "BTC")
        mi = self.market_inv(slug)
        exposure_cap = cfg.exposure_cap_for(asset)

        if mi.total_cost >= exposure_cap:
            return self._swarm_filter(state, intents)

        up_ask = state.up_ask
        down_ask = state.down_ask
        if up_ask is None or down_ask is None:
            return self._swarm_filter(state, intents)

        sum_asks = up_ask + down_ask
        remaining = exposure_cap - mi.total_cost

        # 0. Second-side lag
        need = mi.needs_second_side(
            max_lag_sec=cfg.second_side_lag_sec,
            max_naked_usd=cfg.max_naked_residual_usd,
        )
        if need is not None:
            side = Side.UP if need == "UP" else Side.DOWN
            ask = up_ask if side == Side.UP else down_ask
            other_avg = mi.avg_down_price if side == Side.UP else mi.avg_up_price
            implied_set = (other_avg + ask) if other_avg is not None else sum_asks
            if implied_set <= cfg.target_set_cost + 0.02 and _depth_ok(state, side):
                size = min(cfg.max_order_usd, remaining, max(mi.residual_shares * ask, 5.0))
                if size >= 5:
                    token_id = (
                        state.market["up_token_id"]
                        if side == Side.UP
                        else state.market["down_token_id"]
                    )
                    price = ask
                    if cfg.prefer_maker:
                        price = max(0.01, round(price - 0.01, 2))
                    intents.append(
                        Intent(
                            market_slug=slug,
                            token_id=token_id,
                            side=side,
                            action="BUY",
                            price=price,
                            size_usd=size,
                            reason=(
                                f"SECOND_SIDE lag={mi.seconds_onesided():.0f}s "
                                f"implied_set={implied_set:.3f} residual={mi.residual_side}"
                            ),
                            is_arb_leg=True,
                        )
                    )
                    log.info(
                        f"[SECOND_SIDE] {slug} buy {side.value} size={size:.1f} "
                        f"implied_set={implied_set:.3f}"
                    )
                    return self._swarm_filter(state, intents)

        # 1. Instant complete-set
        if sum_asks <= cfg.arb_threshold and remaining >= 10:
            size = min(cfg.max_order_usd, remaining / 2)
            if size >= 5 and _depth_ok(state, Side.UP) and _depth_ok(state, Side.DOWN):
                for side, ask, tid in (
                    (Side.UP, up_ask, state.market["up_token_id"]),
                    (Side.DOWN, down_ask, state.market["down_token_id"]),
                ):
                    intents.append(
                        Intent(
                            market_slug=slug,
                            token_id=tid,
                            side=side,
                            action="BUY",
                            price=ask,
                            size_usd=size,
                            reason=f"ARB pair (sum={sum_asks:.4f})",
                            is_arb_leg=True,
                        )
                    )
                log.info(
                    f"[ARB] {slug} sum={sum_asks:.4f} -> buying both @ {size:.1f} USD each"
                )
                return self._swarm_filter(state, intents)

        # 2. Staggered set accumulation
        if sum_asks <= cfg.target_set_cost and remaining >= 5:
            prefer_up = up_ask <= down_ask
            if mi.residual_side == "UP":
                prefer_up = False
            elif mi.residual_side == "DOWN":
                prefer_up = True

            side = Side.UP if prefer_up else Side.DOWN
            ask = up_ask if prefer_up else down_ask
            if _depth_ok(state, side):
                size = min(cfg.max_order_usd * cfg.residual_size_factor, remaining)
                if size >= 5:
                    token_id = (
                        state.market["up_token_id"]
                        if prefer_up
                        else state.market["down_token_id"]
                    )
                    price = ask
                    if cfg.prefer_maker:
                        price = max(0.01, round(price - 0.01, 2))
                    intents.append(
                        Intent(
                            market_slug=slug,
                            token_id=token_id,
                            side=side,
                            action="BUY",
                            price=price,
                            size_usd=size,
                            reason=f"SET_ACCUM sum={sum_asks:.4f} leg={side.value}",
                            is_arb_leg=True,
                        )
                    )
                    log.info(
                        f"[SET_ACCUM] {slug} {side.value} @ {price:.2f} size={size:.1f} "
                        f"sum={sum_asks:.4f}"
                    )
                    return self._swarm_filter(state, intents)

        # 3. Directional residual tilt (book imbalance + optional spot fair)
        up_mid = state.up_book.mid or up_ask
        down_mid = state.down_book.mid or down_ask

        imbalance = 0.0
        if state.up_book.best_bid and state.down_book.best_bid:
            imbalance = state.up_book.best_bid - state.down_book.best_bid

        book_edge_up = 0.5 + imbalance * 0.5 - up_mid
        book_edge_down = 0.5 - imbalance * 0.5 - down_mid

        # Spot window-open fair (PriceFeed): P(UP) vs market mid
        fair_up = state.fair_up_prob  # Optional[float] from MarketState

        if getattr(cfg, "use_spot_fair", True) and fair_up is not None:
            w = getattr(cfg, "spot_fair_weight", 0.7)
            spot_edge_up = fair_up - up_mid
            spot_edge_down = (1.0 - fair_up) - down_mid
            edge_up = (1.0 - w) * book_edge_up + w * spot_edge_up
            edge_down = (1.0 - w) * book_edge_down + w * spot_edge_down
        else:
            edge_up = book_edge_up
            edge_down = book_edge_down

        preferred: Optional[Side] = None
        if edge_up >= cfg.min_directional_edge and edge_up >= edge_down:
            preferred = Side.UP
        elif edge_down >= cfg.min_directional_edge:
            preferred = Side.DOWN

        reason_extra = ""
        if preferred is None:
            if mi.up_shares > mi.down_shares * 1.5 and down_ask < 0.55:
                preferred = Side.DOWN
                reason_extra = "inventory rebalance"
            elif mi.down_shares > mi.up_shares * 1.5 and up_ask < 0.55:
                preferred = Side.UP
                reason_extra = "inventory rebalance"
            else:
                return self._swarm_filter(state, intents)
        else:
            reason_extra = (
                f"directional edge={edge_up if preferred == Side.UP else edge_down:.3f}"
            )

        try:
            allowed = getattr(ledger, "directional_allowed", None)
            if callable(allowed) and not allowed(
                min_win_pct=cfg.min_track_record_win_pct,
                min_samples=cfg.min_track_record_samples,
            ):
                log.info(f"[DIR] {slug} blocked by track-record gate")
                return self._swarm_filter(state, intents)
        except Exception:
            pass

        remaining = exposure_cap - mi.total_cost
        size = min(cfg.max_order_usd * cfg.residual_size_factor, remaining)
        if size < 5 or not _depth_ok(state, preferred):
            return self._swarm_filter(state, intents)

        token_id = (
            state.market["up_token_id"]
            if preferred == Side.UP
            else state.market["down_token_id"]
        )
        price = up_ask if preferred == Side.UP else down_ask
        if cfg.prefer_maker:
            price = max(0.01, round(price - 0.01, 2))

        intents.append(
            Intent(
                market_slug=slug,
                token_id=token_id,
                side=preferred,
                action="BUY",
                price=price,
                size_usd=size,
                reason=reason_extra,
                is_arb_leg=False,
            )
        )
        log.info(
            f"[DIR] {slug} prefer {preferred.value} @ {price:.2f} size={size:.1f} ({reason_extra})"
        )

        self.last_signals[slug] = {
            "edge_up": edge_up,
            "edge_down": edge_down,
            "imbalance": imbalance,
            "preferred": preferred.value if preferred else None,
            "avg_set_cost": mi.avg_set_cost,
            "residual_side": mi.residual_side,
            "ts": time.time(),
        }
        return self._swarm_filter(state, intents)

    def update_inventory(self, slug: str, side: Side, shares: float, cost: float):
        """Apply a fill to both the rich inventory book and legacy mirror."""
        price = (cost / shares) if shares > 0 else 0.0
        self.book.apply_fill(
            slug,
            side.value if isinstance(side, Side) else str(side),
            shares,
            cost,
            price,
            is_arb_leg=False,
        )
        self.get_inv(slug)
        mi = self.market_inv(slug)
        log.info(
            f"Inventory {slug}: UP={mi.up_shares:.1f} (${mi.up_cost:.1f}) "
            f"DOWN={mi.down_shares:.1f} (${mi.down_cost:.1f}) "
            f"paired~={mi.paired_shares:.1f} set_cost={mi.avg_set_cost} "
            f"residual={mi.residual_side}"
        )
