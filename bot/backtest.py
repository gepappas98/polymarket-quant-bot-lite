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
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .config import cfg
from .feeds import OrderBook
from .strategy import Intent, Side, Strategy
from .strategies.loader import load_all
from .execution import Order as PaperOrder, OrderBook as PaperOrderBook, PaperFillEngine
from .historical_data import HistoricalDataUnavailable, HistoricalMarketData, HistoricalL2Snapshot, REAL_HISTORICAL_SOURCE

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
    fill_price: Optional[float] = None
    modeled_slippage_usd: float = 0.0

    @property
    def net_pnl_usd(self) -> float:
        return -(self.fee_usd + self.slippage_usd)


@dataclass
class PairRecord:
    """P0-8: net-after-execution outcome for one paired complete-set buy
    attempt (ARB branch: both legs submitted together under one set_id).

    SET_ACCUM / SECOND_SIDE legs build a set gradually over several
    snapshots and are not "pairs" in this sense — they are not recorded
    here, matching bot/executor.py's _record_pair_states convention.

    gross_edge / net_edge are only ever populated for PAIR_COMPLETE: a
    partial or failed pair is naked directional exposure until the other
    leg fills, never a profitable arb.
    """

    set_id: str
    market_slug: str
    ts: float
    legs: int
    filled_legs: int
    state: str  # "PAIR_COMPLETE" | "PAIR_PARTIAL" | "PAIR_FAILED"
    exec_up: Optional[float] = None
    exec_down: Optional[float] = None
    fees_usd: float = 0.0
    slippage_usd: float = 0.0
    requested_usd: float = 0.0
    filled_usd: float = 0.0
    gross_edge: Optional[float] = None
    net_edge: Optional[float] = None
    data_source: str = "LEGACY_SNAPSHOT_INPUT"
    execution_mode: str = "PAPER_SIMULATION"

    @property
    def fill_ratio(self) -> float:
        return self.filled_usd / self.requested_usd if self.requested_usd else 0.0

    @property
    def residual_usd(self) -> float:
        return max(0.0, self.requested_usd - self.filled_usd)


def _build_pair_records(
    intents: List[Intent],
    intent_fills: Dict[int, Any],
    *,
    ts: float,
    data_source: str,
) -> List[PairRecord]:
    """Group same-snapshot ARB legs by set_id (P0-8).

    `intent_fills` maps id(intent) -> an object with .price/.size_usd/
    .fee_usd/.slippage_usd for legs that actually filled (BacktestFill
    satisfies this). A leg with no entry did not fill.
    """
    grouped: Dict[str, List[Intent]] = defaultdict(list)
    for intent in intents:
        if intent.is_arb_leg and intent.set_id:
            grouped[intent.set_id].append(intent)

    records: List[PairRecord] = []
    for set_id, pair_intents in grouped.items():
        leg_fills = [(intent, intent_fills.get(id(intent))) for intent in pair_intents]
        filled_legs = sum(1 for _, f in leg_fills if f is not None)
        if filled_legs == len(pair_intents):
            state = "PAIR_COMPLETE"
        elif filled_legs:
            state = "PAIR_PARTIAL"
        else:
            state = "PAIR_FAILED"

        exec_up = next((f.price for i, f in leg_fills if f is not None and i.side == Side.UP), None)
        exec_down = next((f.price for i, f in leg_fills if f is not None and i.side == Side.DOWN), None)
        fees_usd = sum(f.fee_usd for _, f in leg_fills if f is not None)
        slippage_usd = sum(f.slippage_usd for _, f in leg_fills if f is not None)
        requested_usd = sum(intent.size_usd for intent in pair_intents)
        filled_usd = sum(f.size_usd for _, f in leg_fills if f is not None)

        gross_edge: Optional[float] = None
        net_edge: Optional[float] = None
        if state == "PAIR_COMPLETE" and exec_up is not None and exec_down is not None:
            gross_edge = 1.0 - exec_up - exec_down
            # Normalize $ costs into the same price-space fraction as
            # gross_edge (net after execution — roadmap P0-4/P0-8).
            net_edge = gross_edge - ((fees_usd + slippage_usd) / filled_usd if filled_usd else 0.0)

        records.append(PairRecord(
            set_id=set_id,
            market_slug=pair_intents[0].market_slug,
            ts=ts,
            legs=len(pair_intents),
            filled_legs=filled_legs,
            state=state,
            exec_up=exec_up,
            exec_down=exec_down,
            fees_usd=round(fees_usd, 6),
            slippage_usd=round(slippage_usd, 6),
            requested_usd=round(requested_usd, 6),
            filled_usd=round(filled_usd, 6),
            gross_edge=gross_edge,
            net_edge=net_edge,
            data_source=data_source,
        ))
    return records


@dataclass
class BacktestResult:
    fills: List[BacktestFill]
    realized_pnl_usd: float
    outcomes: int
    wins: int
    gross_pnl_usd: float = 0.0
    pairs: List[PairRecord] = field(default_factory=list)
    data_source: str = "LEGACY_SNAPSHOT_INPUT"
    execution_mode: str = "PAPER_SIMULATION"
    data_coverage: Dict[str, Any] = field(default_factory=dict)
    data_quality_warnings: List[str] = field(default_factory=list)
    peak_exposure_usd: float = 0.0
    turnover_usd: float = 0.0
    requested_usd: float = 0.0

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
        pair_states = Counter(p.state for p in self.pairs)
        pair_note = (
            f" pairs={len(self.pairs)} "
            f"(complete={pair_states.get('PAIR_COMPLETE', 0)} "
            f"partial={pair_states.get('PAIR_PARTIAL', 0)} "
            f"failed={pair_states.get('PAIR_FAILED', 0)})"
            if self.pairs else ""
        )
        return (
            "SIMULATED — not live expectancy. "
            f"Historical market data is {'real' if self.data_source == REAL_HISTORICAL_SOURCE else 'legacy/mock'}; executions are simulated. | "
            f"fills={len(self.fills)}{pair_note} outcomes={self.outcomes} "
            f"win_rate={self.win_rate_pct}% gross_pnl=${self.gross_pnl_usd:+.2f} "
            f"fees=${self.fees_usd:.4f} slippage=${self.slippage_usd:.4f} "
            f"net_pnl=${self.net_pnl_usd:+.2f}"
        )

    @property
    def fill_ratio(self) -> float:
        return self.filled_usd / self.requested_usd if self.requested_usd else 0.0

    @property
    def filled_usd(self) -> float:
        return sum(fill.size_usd for fill in self.fills)

    @property
    def drawdown_usd(self) -> float:
        return max(0.0, -self.net_pnl_usd)

    @property
    def trades(self) -> List[BacktestFill]:
        return self.fills

    @property
    def partial_fills(self) -> List[BacktestFill]:
        return [fill for fill in self.fills if fill.size_usd + 1e-9 < fill.requested_usd]


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
        key = (snap.ts, intent.side.value, "ask", price)
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
    book_depth = max(sum(float(level.get("size", 0.0)) * float(level.get("price", 0.0)) for level in levels), 1e-9)
    side_sign = 1 if intent.action == "BUY" else -1
    fill_price = max(0.0, min(1.0, intent.price + (0.005 + 0.01 * intent.size_usd / book_depth) * side_sign))
    # Keep the public price as the observed VWAP for compatibility; the modeled
    # fill price is reflected in slippage cost and therefore net P&L.
    modeled_slippage_usd = abs(fill_price - intent.price) * shares
    fee = consumed_usd * max(0.0, cfg.paper_fee_bps) / 10_000
    return BacktestFill(
        ts=snap.ts, market_slug=intent.market_slug,
        side=intent.side.value, price=avg, size_usd=consumed_usd,
        reason="SIMULATED_FILL", requested_usd=intent.size_usd,
        fee_usd=fee, slippage_usd=slippage, fill_price=fill_price,
        modeled_slippage_usd=modeled_slippage_usd,
    )


def _simulate_maker(
    intent: Intent,
    snap: Snapshot,
    rng: random.Random,
    consumed: Optional[Dict[tuple, float]] = None,
) -> Optional[BacktestFill]:
    """P0-8: deplete the touched bid level via `consumed`, shared with
    _simulate_taker, so two intents in the same snapshot cannot each claim
    the full displayed queue at the same touch."""
    if consumed is None:
        consumed = {}
    probability = max(0.0, min(1.0, cfg.maker_fill_probability))
    if rng.random() > probability:
        return None
    levels = snap.up_bids if intent.side == Side.UP else snap.down_bids
    touch = next((level for level in levels if abs(float(level.get("price", 0.0)) - intent.price) < 1e-9), None)
    if touch is None:
        return None
    price = float(touch.get("price", 0.0))
    key = (snap.ts, intent.side.value, "bid", price)
    already_consumed = consumed.get(key, 0.0)
    available = max(0.0, float(touch.get("size", 0.0)) - cfg.maker_queue_ahead - already_consumed)
    filled_usd = min(intent.size_usd, available * intent.price)
    if filled_usd <= 0:
        return None
    fee = filled_usd * max(0.0, cfg.paper_fee_bps) / 10_000
    consumed[key] = already_consumed + (filled_usd / intent.price if intent.price else 0.0)
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
    pairs: List[PairRecord] = []
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

        snap_intents = registry.evaluate_all(state)
        intent_fills: Dict[int, BacktestFill] = {}
        for intent in snap_intents:
            if not _simple_exposure_gate(strategy, intent):
                continue
            fill = _simulate_maker(intent, snap, rng, consumed) if cfg.prefer_maker else _simulate_taker(intent, snap, consumed)
            if fill is None and cfg.prefer_maker:
                fill = _simulate_taker(intent, snap, consumed)
            if fill is None:
                continue
            shares = fill.size_usd / fill.price
            strategy.update_inventory(intent.market_slug, intent.side, shares, fill.size_usd)
            fills.append(fill)
            intent_fills[id(intent)] = fill
        pairs.extend(_build_pair_records(
            snap_intents, intent_fills, ts=snap.ts, data_source="LEGACY_SNAPSHOT_INPUT",
        ))

    return BacktestResult(
        fills=fills,
        pairs=pairs,
        realized_pnl_usd=round(realized_pnl, 2),
        outcomes=outcomes,
        wins=wins,
        gross_pnl_usd=round(realized_pnl, 2),
    )


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Backtest bot strategies over historical snapshots")
    parser.add_argument("snapshots_path", nargs="?", help="Legacy JSONL fixture path; use --real-db for REAL recorder data")
    parser.add_argument("--real-db", help="SQLite database created by the REAL Polymarket recorder")
    parser.add_argument("--start-ms", type=int)
    parser.add_argument("--end-ms", type=int)
    parser.add_argument("--market-id")
    parser.add_argument("--token-id")
    args = parser.parse_args()

    if args.real_db:
        source = __import__("bot.historical_data", fromlist=["PolymarketHistoricalL2DataSource"]).PolymarketHistoricalL2DataSource(args.real_db)
        result = run_real_backtest(source, start_ms=args.start_ms, end_ms=args.end_ms, market_id=args.market_id, token_id=args.token_id)
    else:
        if not args.snapshots_path:
            parser.error("provide snapshots_path for legacy fixtures or --real-db for REAL Polymarket history")
        snapshots = load_snapshots(args.snapshots_path)
        if not snapshots:
            raise SystemExit("No snapshots loaded — check the file path/format.")
        result = run_backtest(snapshots)
    print(result.summary())
    print(f"data_source={result.data_source} execution_mode={result.execution_mode} fill_ratio={result.fill_ratio:.4f} turnover=${result.turnover_usd:.2f} peak_exposure=${result.peak_exposure_usd:.2f}")
    if result.data_quality_warnings:
        print("data_quality_warnings=" + "; ".join(result.data_quality_warnings))
    for p in result.pairs:
        edge_str = f"net_edge={p.net_edge:+.4f}" if p.net_edge is not None else "net_edge=n/a"
        print(
            f"  [{p.state}] {p.market_slug} set={p.set_id} legs={p.filled_legs}/{p.legs} "
            f"exec_up={p.exec_up} exec_down={p.exec_down} {edge_str} "
            f"fill_ratio={p.fill_ratio:.2f} residual=${p.residual_usd:.2f}"
        )
    for f in result.fills[:20]:
        print(f"  {f.side:5s} {f.market_slug:30s} @ {f.price:.3f}  ${f.size_usd:.1f}  {f.reason}")
    if len(result.fills) > 20:
        print(f"  ... and {len(result.fills) - 20} more fills")


if __name__ == "__main__":
    main()


# --- REAL Polymarket recorder replay --------------------------------------
def _real_snapshots(source: HistoricalMarketData, *, start_ms: int | None = None, end_ms: int | None = None, market_id: str | None = None, token_id: str | None = None) -> list[Snapshot]:
    """Convert recorder rows into strategy-compatible states without inventing levels."""
    rows = source.require_snapshots(start_ms=start_ms, end_ms=end_ms, market_id=market_id, token_id=token_id)
    latest: dict[str, dict[str, Any]] = {}
    snapshots: list[Snapshot] = []
    for row in rows:
        item = latest.setdefault(row.market_id, {"slug": row.market_id, "market_id": row.market_id, "condition_id": row.condition_id, "token_ids": {}})
        outcome = (row.outcome or "").upper()
        side = "up" if outcome in {"UP", "YES"} else "down" if outcome in {"DOWN", "NO"} else ("up" if row.token_id not in item["token_ids" ] and not any(item["token_ids"].values()) else "down")
        item["token_ids"][side] = row.token_id
        item[f"{side}_bids"] = list(row.bids)
        item[f"{side}_asks"] = list(row.asks)
        item[f"{side}_token_id"] = row.token_id
        snapshots.append(Snapshot(
            ts=row.timestamp,
            market=item,
            up_bids=item.get("up_bids", []), up_asks=item.get("up_asks", []),
            down_bids=item.get("down_bids", []), down_asks=item.get("down_asks", []),
        ))
    return snapshots


def _real_paper_fill(
    intent: Intent,
    snap: Snapshot,
    engine: PaperFillEngine,
    consumed: Dict[tuple, float],
) -> list[BacktestFill]:
    """Fill against the observed book, depleting shared per-touch liquidity
    (`consumed`, reset once per snapshot by the caller) so that multiple
    intents evaluated against the same snapshot cannot each drain the same
    displayed size — P0-4/P0-8: one fill per book level per snapshot."""
    is_buy = intent.action.upper() == "BUY"
    raw_bids = snap.up_bids if intent.side == Side.UP else snap.down_bids
    raw_asks = snap.up_asks if intent.side == Side.UP else snap.down_asks
    tag = "ask" if is_buy else "bid"

    def _levels(levels) -> list[dict]:
        return [{"price": float(level["price"]), "shares": float(level["size"])} for level in levels]

    def _deplete(levels) -> list[dict]:
        out: list[dict] = []
        for level in levels:
            price = float(level["price"])
            size = float(level["size"])
            key = (intent.side.value, tag, price)
            avail = max(0.0, size - consumed.get(key, 0.0))
            if avail > 0:
                out.append({"price": price, "shares": avail})
        return out

    book = PaperOrderBook.from_levels(
        _deplete(raw_bids) if not is_buy else _levels(raw_bids),
        _deplete(raw_asks) if is_buy else _levels(raw_asks),
    )
    order = PaperOrder(intent.market_slug, intent.side.value, intent.action, intent.size_usd, intent.price)
    report = engine.execute(order, book)
    for fill in report.fills:
        key = (intent.side.value, tag, fill.price)
        consumed[key] = consumed.get(key, 0.0) + fill.shares
    return [BacktestFill(
        ts=fill.ts, market_slug=intent.market_slug, side=intent.side.value,
        price=fill.price, size_usd=fill.shares * fill.price, reason="SIMULATED_FILL",
        requested_usd=intent.size_usd, fee_usd=fill.fee_usd,
        slippage_usd=fill.shares * abs(fill.price - intent.price) + fill.shares * fill.price * engine.slippage_bps / 10_000,
        fill_price=fill.price,
    ) for fill in report.fills]


def run_real_backtest(
    data_source: HistoricalMarketData,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
    market_id: str | None = None,
    token_id: str | None = None,
    strategy: Strategy | None = None,
) -> BacktestResult:
    """Replay REAL recorder snapshots chronologically through the paper fill engine.

    This function is intentionally separate from ``run_backtest``: legacy fixture
    snapshots remain valid for unit tests, while REAL mode has no synthetic fallback.
    """
    snapshots = _real_snapshots(data_source, start_ms=start_ms, end_ms=end_ms, market_id=market_id, token_id=token_id)
    strategy = strategy or Strategy()
    registry = load_all(strategy)
    engine = PaperFillEngine(cfg.paper_fee_bps, cfg.paper_slippage_bps)
    fills: list[BacktestFill] = []
    pairs: list[PairRecord] = []
    requested_usd = 0.0
    turnover_usd = 0.0
    peak_exposure = 0.0
    for snap in snapshots:
        state = BacktestMarketState(snap)
        snap_intents = registry.evaluate_all(state)
        intent_fills: Dict[int, BacktestFill] = {}
        consumed: Dict[tuple, float] = {}
        for intent in snap_intents:
            if not _simple_exposure_gate(strategy, intent):
                continue
            requested_usd += intent.size_usd
            new_fills = _real_paper_fill(intent, snap, engine, consumed)
            fills.extend(new_fills)
            turnover_usd += sum(fill.size_usd for fill in new_fills)
            if new_fills:
                total_shares = sum(f.size_usd / f.price for f in new_fills if f.price)
                total_usd = sum(f.size_usd for f in new_fills)
                # Per-intent VWAP representative for pair grouping only — not
                # added to `fills`, so fees_usd/slippage_usd totals on the
                # result are not double-counted.
                intent_fills[id(intent)] = BacktestFill(
                    ts=new_fills[-1].ts, market_slug=intent.market_slug, side=intent.side.value,
                    price=(total_usd / total_shares) if total_shares else intent.price,
                    size_usd=total_usd, reason="SIMULATED_FILL", requested_usd=intent.size_usd,
                    fee_usd=sum(f.fee_usd for f in new_fills),
                    slippage_usd=sum(f.slippage_usd for f in new_fills),
                )
            for fill in new_fills:
                strategy.update_inventory(intent.market_slug, intent.side, fill.size_usd / fill.price, fill.size_usd)
            inv = strategy.get_inv(intent.market_slug)
            peak_exposure = max(peak_exposure, inv.total_cost)
        pairs.extend(_build_pair_records(
            snap_intents, intent_fills, ts=snap.ts, data_source=REAL_HISTORICAL_SOURCE,
        ))
    coverage = data_source.coverage(start_ms=start_ms, end_ms=end_ms, market_id=market_id, token_id=token_id)  # type: ignore[attr-defined]
    return BacktestResult(
        fills=fills, pairs=pairs, realized_pnl_usd=0.0, outcomes=0, wins=0, gross_pnl_usd=0.0,
        data_source=REAL_HISTORICAL_SOURCE, execution_mode="PAPER_SIMULATION",
        data_coverage=coverage, data_quality_warnings=coverage["quality_warnings"],
        peak_exposure_usd=peak_exposure, turnover_usd=turnover_usd, requested_usd=requested_usd,
    )
