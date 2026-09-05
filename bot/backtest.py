"""
Backtesting framework (Priority 2) — replay ιστορικά order-book snapshots
μέσα από το ΙΔΙΟ StrategyRegistry/Strategy που τρέχει live, χωρίς δίκτυο.

ΣΗΜΑΝΤΙΚΟΣ ΠΕΡΙΟΡΙΣΜΟΣ (διάβασε πριν εμπιστευτείς τα αποτελέσματα):
Τα process-local gates στο bot/gates.py (CooldownLock) και
bot/portfolio_gates.py (max_drawdown_gate, LowProfitPairLock) βασίζονται σε
`time.time()` (real wall clock), όχι σε injectable/ιστορικό ρολόι. Σε ένα
backtest όπου παίζεις ιστορικά δεδομένα πολύ πιο γρήγορα από ό,τι συνέβησαν
πραγματικά, τα cooldowns/kill-switch ΔΕΝ θα συμπεριφερθούν όπως θα
συμπεριφέρονταν live — θα δεις είτε πολύ λιγότερα blocks (αν τρέξεις γρήγορα
μέσα σε λίγα δευτερόλεπτα wall-clock) είτε καθόλου διαφορά.

Αυτό το module ΔΕΝ προσπαθεί να λύσει αυτό το πρόβλημα (θα απαιτούσε να
κάνεις όλα τα gates injectable-clock, μια πιο μεγάλη αλλαγή) — αντ' αυτού
τρέχει ένα ΞΕΧΩΡΙΣΤΟ, απλοποιημένο risk model (μόνο exposure cap + hard
per-order size cap, ίδιο μαθηματικό μοντέλο με bot/strategy.py) που είναι
time-independent και άρα αναπαράγεται ντετερμινιστικά. Θεώρησέ το ως πρώτο
πέρασμα ελέγχου του strategy edge, όχι ως πιστή αναπαραγωγή του production
risk pipeline.

Snapshot format (JSONL, μία γραμμή ανά μεταβολή):
    {
      "ts": 1735500000.0,
      "market": {"slug": "btc-updown-5m-...", "asset": "BTC",
                 "up_token_id": "...", "down_token_id": "..."},
      "up_bids": [{"price": "0.48", "size": "10"}],
      "up_asks": [{"price": "0.50", "size": "10"}],
      "down_bids": [{"price": "0.49", "size": "10"}],
      "down_asks": [{"price": "0.51", "size": "10"}],
      "resolved": false,          # true όταν το window κλείνει
      "winner": null              # "UP" | "DOWN", μόνο όταν resolved=true
    }
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .config import cfg
from .feeds import OrderBook
from .strategy import Intent, Side, Strategy
from .strategies.loader import load_all

log = logging.getLogger(__name__)


@dataclass
class Snapshot:
    ts: float
    market: Dict[str, Any]
    up_bids: List[dict] = field(default_factory=list)
    up_asks: List[dict] = field(default_factory=list)
    down_bids: List[dict] = field(default_factory=list)
    down_asks: List[dict] = field(default_factory=list)
    resolved: bool = False
    winner: Optional[str] = None


class BacktestMarketState:
    """Ίδιο public interface με bot.feeds.MarketState, αλλά τα books
    προέρχονται από το snapshot αντί για network fetch — καθόλου requests."""

    def __init__(self, snapshot: Snapshot):
        self.market = snapshot.market
        self.up_book = OrderBook(bids=snapshot.up_bids, asks=snapshot.up_asks)
        self.down_book = OrderBook(bids=snapshot.down_bids, asks=snapshot.down_asks)

    def refresh(self) -> None:
        pass  # no-op: τα books ήρθαν ήδη έτοιμα από το snapshot

    @property
    def up_ask(self) -> Optional[float]:
        return self.up_book.best_ask

    @property
    def down_ask(self) -> Optional[float]:
        return self.down_book.best_ask

    @property
    def sum_asks(self) -> Optional[float]:
        if self.up_ask is not None and self.down_ask is not None:
            return self.up_ask + self.down_ask
        return None

    @property
    def arb_available(self) -> bool:
        s = self.sum_asks
        return s is not None and s <= cfg.arb_threshold


def load_snapshots(path: str) -> List[Snapshot]:
    snapshots: List[Snapshot] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            snapshots.append(Snapshot(
                ts=float(raw["ts"]),
                market=raw["market"],
                up_bids=raw.get("up_bids", []),
                up_asks=raw.get("up_asks", []),
                down_bids=raw.get("down_bids", []),
                down_asks=raw.get("down_asks", []),
                resolved=bool(raw.get("resolved", False)),
                winner=raw.get("winner"),
            ))
    snapshots.sort(key=lambda s: s.ts)
    return snapshots


@dataclass
class BacktestFill:
    ts: float
    market_slug: str
    side: str
    price: float
    size_usd: float
    reason: str
    requested_usd: float = 0.0
    fee_usd: float = 0.0
    slippage_usd: float = 0.0
    fill_probability: float = 1.0
    queue_ahead: float = 0.0
    latency_sec: float = 0.0
    simulated: bool = True

    @property
    def net_pnl_usd(self) -> float:
        return -(self.fee_usd + self.slippage_usd)


@dataclass
class BacktestResult:
    fills: List[BacktestFill]
    realized_pnl_usd: float
    outcomes: int
    wins: int
    gross_pnl_usd: float = 0.0

    @property
    def fees_usd(self) -> float:
        return sum(fill.fee_usd for fill in self.fills)

    @property
    def slippage_usd(self) -> float:
        return sum(fill.slippage_usd for fill in self.fills)

    @property
    def net_pnl_usd(self) -> float:
        return self.gross_pnl_usd - self.fees_usd - self.slippage_usd

    @property
    def win_rate_pct(self) -> float:
        return round(100.0 * self.wins / self.outcomes, 2) if self.outcomes else 0.0

    def summary(self) -> str:
        return (
            "SIMULATED — not live expectancy | "
            f"fills={len(self.fills)} outcomes={self.outcomes} "
            f"win_rate={self.win_rate_pct}% gross_pnl=${self.gross_pnl_usd:+.2f} "
            f"fees=${self.fees_usd:.4f} slippage=${self.slippage_usd:.4f} "
            f"net_pnl=${self.net_pnl_usd:+.2f}"
        )


def _simple_exposure_gate(strategy: Strategy, intent: Intent) -> bool:
    """Time-independent στιγμιότυπο του risk model (βλ. docstring πάνω στο αρχείο):
    μόνο max_order_usd + exposure_cap_for(asset). ΔΕΝ αναπαράγει cooldown/kill-switch."""
    if intent.size_usd <= 0 or intent.size_usd > cfg.max_order_usd * 1.01:
        return False
    inv = strategy.get_inv(intent.market_slug)
    asset = intent.market_slug.split("-")[0].upper()
    cap = cfg.exposure_cap_for(asset)
    return inv.total_cost + intent.size_usd <= cap + 1e-6


def _simulate_taker(intent: Intent, snap: Snapshot, consumed: Dict[tuple, float]) -> Optional[BacktestFill]:
    levels = snap.up_asks if intent.side == Side.UP else snap.down_asks
    remaining_usd = intent.size_usd
    consumed_usd = 0.0
    shares = 0.0
    slippage = 0.0
    for level in levels:
        price = float(level.get("price", 0.0))
        available = float(level.get("size", 0.0))
        key = (snap.ts, intent.side.value, price)
        available = max(0.0, available - consumed.get(key, 0.0))
        if price <= 0 or available <= 0 or remaining_usd <= 0:
            continue
        clip_usd = min(remaining_usd, available * price)
        clip_shares = clip_usd / price
        consumed[key] = consumed.get(key, 0.0) + clip_shares
        shares += clip_shares
        consumed_usd += clip_usd
        slippage += clip_shares * max(0.0, price - intent.price)
        remaining_usd -= clip_usd
    if shares <= 0:
        return None
    avg = consumed_usd / shares
    fee = consumed_usd * max(0.0, cfg.paper_fee_bps) / 10_000
    return BacktestFill(
        ts=snap.ts, market_slug=intent.market_slug,
        side=intent.side.value, price=avg, size_usd=consumed_usd,
        reason="SIMULATED_FILL", requested_usd=intent.size_usd,
        fee_usd=fee, slippage_usd=slippage,
    )


def _simulate_maker(intent: Intent, snap: Snapshot, rng: random.Random) -> Optional[BacktestFill]:
    probability = max(0.0, min(1.0, cfg.maker_fill_probability))
    if rng.random() > probability:
        return None
    levels = snap.up_bids if intent.side == Side.UP else snap.down_bids
    touch = next((level for level in levels if abs(float(level.get("price", 0.0)) - intent.price) < 1e-9), None)
    if touch is None:
        return None
    available = max(0.0, float(touch.get("size", 0.0)) - cfg.maker_queue_ahead)
    filled_usd = min(intent.size_usd, available * intent.price)
    if filled_usd <= 0:
        return None
    fee = filled_usd * max(0.0, cfg.paper_fee_bps) / 10_000
    return BacktestFill(
        ts=snap.ts + max(0.0, cfg.maker_latency_sec), market_slug=intent.market_slug,
        side=intent.side.value, price=intent.price, size_usd=filled_usd,
        reason="SIMULATED_MAKER_FILL", requested_usd=intent.size_usd,
        fee_usd=fee, fill_probability=probability,
        queue_ahead=cfg.maker_queue_ahead, latency_sec=cfg.maker_latency_sec,
    )


def run_backtest(snapshots: Iterable[Snapshot]) -> BacktestResult:
    """
    Τρέχει το ΠΛΗΡΕΣ strategy stack (arb/directional + όποιο άλλο plugin
    είναι ενεργό μέσω bot/strategies/*.py env vars) πάνω στα snapshots,
    με simplified time-independent risk gating (βλ. πάνω).
    """
    strategy = Strategy()
    registry = load_all(strategy)

    fills: List[BacktestFill] = []
    realized_pnl = 0.0
    outcomes = 0
    wins = 0
    gross_pnl = 0.0
    consumed: Dict[tuple, float] = {}
    rng = random.Random(0)

    for snap in snapshots:
        state = BacktestMarketState(snap)

        if snap.resolved:
            inv = strategy.inventories.get(snap.market["slug"])
            if inv and inv.total_cost > 0:
                if snap.winner == "UP":
                    payout = inv.up_shares
                elif snap.winner == "DOWN":
                    payout = inv.down_shares
                else:
                    payout = 0.0
                pnl = payout - inv.total_cost
                realized_pnl += pnl
                outcomes += 1
                if pnl > 0:
                    wins += 1
                log.info(f"[BACKTEST] {snap.market['slug']} winner={snap.winner} pnl={pnl:+.2f}")
                strategy.inventories.pop(snap.market["slug"], None)
            continue

        for intent in registry.evaluate_all(state):
            if not _simple_exposure_gate(strategy, intent):
                continue
            fill = _simulate_maker(intent, snap, rng) if cfg.prefer_maker else _simulate_taker(intent, snap, consumed)
            if fill is None and cfg.prefer_maker:
                fill = _simulate_taker(intent, snap, consumed)
            if fill is None:
                continue
            shares = fill.size_usd / fill.price
            strategy.update_inventory(intent.market_slug, intent.side, shares, fill.size_usd)
            fills.append(fill)

    return BacktestResult(
        fills=fills,
        realized_pnl_usd=round(realized_pnl, 2),
        outcomes=outcomes,
        wins=wins,
        gross_pnl_usd=round(realized_pnl, 2),
    )


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Backtest bot strategies over historical snapshots")
    parser.add_argument("snapshots_path", help="Path to a JSONL snapshot file (see bot/backtest.py docstring)")
    args = parser.parse_args()

    snapshots = load_snapshots(args.snapshots_path)
    if not snapshots:
        print("No snapshots loaded — check the file path/format.")
        return
    result = run_backtest(snapshots)
    print(result.summary())
    for f in result.fills[:20]:
        print(f"  {f.side:5s} {f.market_slug:30s} @ {f.price:.3f}  ${f.size_usd:.1f}  {f.reason}")
    if len(result.fills) > 20:
        print(f"  ... and {len(result.fills) - 20} more fills")


if __name__ == "__main__":
    main()
