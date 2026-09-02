"""
Per-market inventory accounting for complete-set / residual strategies (v0.5).

Inspired by public high-volume Up/Down makers that:
  - accumulate UP and DOWN over multiple fills (not only same-cycle pairs)
  - treat min(up, down) as paired complete sets with an average set cost
  - keep residual directional exposure on the unmatched leg
  - work the second side after a one-sided fill (second-side lag)

This module is pure state + math — strategies and the executor call into it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class FillRecord:
    side: str  # "UP" | "DOWN"
    shares: float
    cost_usd: float
    price: float
    ts: float
    is_arb_leg: bool = False


@dataclass
class MarketInventory:
    """Tracks position and set economics for one market slug."""

    up_shares: float = 0.0
    down_shares: float = 0.0
    up_cost: float = 0.0
    down_cost: float = 0.0
    fills: List[FillRecord] = field(default_factory=list)

    # Second-side lag: when we last went one-sided and which side is naked
    last_onesided_ts: Optional[float] = None
    onesided_side: Optional[str] = None  # side that has MORE shares (the residual side)

    @property
    def paired_shares(self) -> float:
        """How many complete sets we effectively hold."""
        return min(self.up_shares, self.down_shares)

    @property
    def residual_shares(self) -> float:
        """Unmatched directional leg size (shares)."""
        return abs(self.up_shares - self.down_shares)

    @property
    def residual_side(self) -> Optional[str]:
        if self.up_shares > self.down_shares:
            return "UP"
        if self.down_shares > self.up_shares:
            return "DOWN"
        return None

    @property
    def total_cost(self) -> float:
        return self.up_cost + self.down_cost

    @property
    def net_exposure_usd(self) -> float:
        """Rough directional exposure: unmatched cost on the heavy side."""
        if self.up_shares == self.down_shares:
            return 0.0
        if self.up_shares > self.down_shares:
            # cost attributable to residual UP
            if self.up_shares <= 0:
                return 0.0
            avg_up = self.up_cost / self.up_shares
            return (self.up_shares - self.down_shares) * avg_up
        if self.down_shares <= 0:
            return 0.0
        avg_down = self.down_cost / self.down_shares
        return (self.down_shares - self.up_shares) * avg_down

    @property
    def avg_up_price(self) -> Optional[float]:
        if self.up_shares <= 0:
            return None
        return self.up_cost / self.up_shares

    @property
    def avg_down_price(self) -> Optional[float]:
        if self.down_shares <= 0:
            return None
        return self.down_cost / self.down_shares

    @property
    def avg_set_cost(self) -> Optional[float]:
        """
        Average complete-set cost ≈ avg_up + avg_down when both sides exist.
        Edge per set ≈ 1.0 - avg_set_cost (before fees).
        """
        au, ad = self.avg_up_price, self.avg_down_price
        if au is None or ad is None:
            return None
        return au + ad

    @property
    def edge_per_set(self) -> Optional[float]:
        c = self.avg_set_cost
        if c is None:
            return None
        return 1.0 - c

    def apply_fill(
        self,
        side: str,
        shares: float,
        cost_usd: float,
        price: float,
        *,
        is_arb_leg: bool = False,
        ts: Optional[float] = None,
    ) -> None:
        side = side.upper()
        ts = ts if ts is not None else time.time()
        if side == "UP":
            self.up_shares += shares
            self.up_cost += cost_usd
        elif side == "DOWN":
            self.down_shares += shares
            self.down_cost += cost_usd
        else:
            raise ValueError(f"side must be UP or DOWN, got {side!r}")

        self.fills.append(
            FillRecord(
                side=side,
                shares=shares,
                cost_usd=cost_usd,
                price=price,
                ts=ts,
                is_arb_leg=is_arb_leg,
            )
        )
        self._refresh_onesided(ts)

    def _refresh_onesided(self, ts: float) -> None:
        residual = self.residual_side
        if residual is None:
            self.last_onesided_ts = None
            self.onesided_side = None
        else:
            # Only reset timer when residual side changes or first becomes onesided
            if self.onesided_side != residual:
                self.last_onesided_ts = ts
                self.onesided_side = residual

    def seconds_onesided(self, now: Optional[float] = None) -> float:
        if self.last_onesided_ts is None:
            return 0.0
        now = now if now is not None else time.time()
        return max(0.0, now - self.last_onesided_ts)

    def needs_second_side(
        self,
        *,
        max_lag_sec: float,
        max_naked_usd: float,
        now: Optional[float] = None,
    ) -> Optional[str]:
        """
        If we are onesided past lag or naked residual USD, return the side
        we should BUY to pair (opposite of residual).
        """
        residual = self.residual_side
        if residual is None:
            return None
        naked = self.net_exposure_usd
        lag = self.seconds_onesided(now)
        if lag >= max_lag_sec or naked >= max_naked_usd:
            return "DOWN" if residual == "UP" else "UP"
        return None

    def snapshot(self) -> dict:
        return {
            "up_shares": round(self.up_shares, 4),
            "down_shares": round(self.down_shares, 4),
            "up_cost": round(self.up_cost, 4),
            "down_cost": round(self.down_cost, 4),
            "paired_shares": round(self.paired_shares, 4),
            "residual_shares": round(self.residual_shares, 4),
            "residual_side": self.residual_side,
            "total_cost": round(self.total_cost, 4),
            "net_exposure_usd": round(self.net_exposure_usd, 4),
            "avg_set_cost": None if self.avg_set_cost is None else round(self.avg_set_cost, 4),
            "edge_per_set": None if self.edge_per_set is None else round(self.edge_per_set, 4),
            "seconds_onesided": round(self.seconds_onesided(), 1),
            "n_fills": len(self.fills),
        }


class InventoryBook:
    """Slug → MarketInventory."""

    def __init__(self) -> None:
        self._markets: Dict[str, MarketInventory] = {}

    def get(self, slug: str) -> MarketInventory:
        if slug not in self._markets:
            self._markets[slug] = MarketInventory()
        return self._markets[slug]

    def apply_fill(
        self,
        slug: str,
        side: str,
        shares: float,
        cost_usd: float,
        price: float,
        *,
        is_arb_leg: bool = False,
    ) -> MarketInventory:
        inv = self.get(slug)
        inv.apply_fill(side, shares, cost_usd, price, is_arb_leg=is_arb_leg)
        return inv

    def summary(self) -> Dict[str, dict]:
        return {slug: inv.snapshot() for slug, inv in self._markets.items()}
