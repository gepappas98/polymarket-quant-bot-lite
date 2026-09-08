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
from .execution import Order as PaperOrder, OrderBook as PaperOrderBook, PaperFillEngine
from .historical_data import HistoricalDataUnavailable, HistoricalMarketData, HistoricalL2Snapshot, REAL_HISTORICAL_SOURCE
from .execution_calibration import calibrate_real_l2

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
    data_source: str = "LEGACY_SNAPSHOT_INPUT"
    label_source: Optional[str] = None


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
                data_source=str(raw.get("data_source", "LEGACY_SNAPSHOT_INPUT")),
                label_source=raw.get("label_source"),
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
class BacktestResult:
    fills: List[BacktestFill]
    realized_pnl_usd: float
    outcomes: int
    wins: int
    gross_pnl_usd: float = 0.0
    data_source: str = "LEGACY_SNAPSHOT_INPUT"
    execution_mode: str = "PAPER_SIMULATION"
    data_coverage: Dict[str, Any] = field(default_factory=dict)
    data_quality_warnings: List[str] = field(default_factory=list)
    peak_exposure_usd: float = 0.0
    turnover_usd: float = 0.0
    requested_usd: float = 0.0
    calibration: Dict[str, Any] = field(default_factory=dict)

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
            f"Historical market data is {'real' if self.data_source == REAL_HISTORICAL_SOURCE else 'legacy/mock'}; executions are simulated. | "
            f"fills={len(self.fills)} outcomes={self.outcomes} "
            f"win_rate={self.win_rate_pct}% gross_pnl=${self.gross_pnl_usd:+.2f} "
            f"fees=${self.fees_usd:.4f} slippage=${self.slippage_usd:.4f} "
            f"net_pnl=${self.net_pnl_usd:+.2f} "
            f"fill_model_version={self.calibration.get('fill_model_version', 'UNSPECIFIED')} "
            f"calibration_dataset={self.calibration.get('calibration_dataset', 'UNSPECIFIED')}"
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
    *,
    probability: Optional[float] = None,
    queue_ahead: Optional[float] = None,
    latency_sec: Optional[float] = None,
) -> Optional[BacktestFill]:
    probability = max(0.0, min(1.0, cfg.maker_fill_probability if probability is None else probability))
    queue_ahead = cfg.maker_queue_ahead if queue_ahead is None else max(0.0, queue_ahead)
    latency_sec = cfg.maker_latency_sec if latency_sec is None else max(0.0, latency_sec)
    if rng.random() > probability:
        return None
    levels = snap.up_bids if intent.side == Side.UP else snap.down_bids
    touch = next((level for level in levels if abs(float(level.get("price", 0.0)) - intent.price) < 1e-9), None)
    if touch is None:
        return None
    available = max(0.0, float(touch.get("size", 0.0)) - queue_ahead)
    filled_usd = min(intent.size_usd, available * intent.price)
    if filled_usd <= 0:
        return None
    fee = filled_usd * max(0.0, cfg.paper_fee_bps) / 10_000
    return BacktestFill(
        ts=snap.ts + latency_sec, market_slug=intent.market_slug,
        side=intent.side.value, price=intent.price, size_usd=filled_usd,
        reason="SIMULATED_MAKER_FILL", requested_usd=intent.size_usd,
        fee_usd=fee, fill_probability=probability,
        queue_ahead=queue_ahead, latency_sec=latency_sec,
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
        calibration={
            "fill_model_version": "legacy-config-v1",
            "calibration_dataset": "LEGACY_SNAPSHOT_INPUT",
            "assumptions": ["Legacy fixture path is not an empirical REAL calibration."],
            "maker_fill_assumption": cfg.maker_fill_probability,
            "latency_assumption": cfg.maker_latency_sec,
            "fee_model": f"configured_paper_fee_bps:{cfg.paper_fee_bps:g}",
            "slippage_model": f"configured_paper_slippage_bps:{cfg.paper_slippage_bps:g}",
        },
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
    print("calibration=" + json.dumps(result.calibration, sort_keys=True))
    if result.data_quality_warnings:
        print("data_quality_warnings=" + "; ".join(result.data_quality_warnings))
    for f in result.fills[:20]:
        print(f"  {f.side:5s} {f.market_slug:30s} @ {f.price:.3f}  ${f.size_usd:.1f}  {f.reason}")
    if len(result.fills) > 20:
        print(f"  ... and {len(result.fills) - 20} more fills")


if __name__ == "__main__":
    main()


# --- REAL Polymarket recorder replay --------------------------------------
def _real_snapshots_from_rows(rows: list[HistoricalL2Snapshot]) -> list[Snapshot]:
    """Convert REAL recorder rows into strategy-compatible states without inventing levels."""
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


def _real_snapshots(source: HistoricalMarketData, *, start_ms: int | None = None, end_ms: int | None = None, market_id: str | None = None, token_id: str | None = None) -> list[Snapshot]:
    rows = source.require_snapshots(start_ms=start_ms, end_ms=end_ms, market_id=market_id, token_id=token_id)
    return _real_snapshots_from_rows(rows)


def _real_paper_fill(intent: Intent, snap: Snapshot, engine: PaperFillEngine) -> list[BacktestFill]:
    levels_bid = snap.up_bids if intent.side == Side.UP else snap.down_bids
    levels_ask = snap.up_asks if intent.side == Side.UP else snap.down_asks
    book = PaperOrderBook.from_levels(
        [{"price": float(level["price"]), "shares": float(level["size"])} for level in levels_bid],
        [{"price": float(level["price"]), "shares": float(level["size"])} for level in levels_ask],
    )
    order = PaperOrder(intent.market_slug, intent.side.value, intent.action, intent.size_usd, intent.price)
    report = engine.execute(order, book)
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
    rows = data_source.require_snapshots(start_ms=start_ms, end_ms=end_ms, market_id=market_id, token_id=token_id)
    snapshots = _real_snapshots_from_rows(rows)
    calibration = calibrate_real_l2(
        rows,
        fee_bps=cfg.paper_fee_bps,
        slippage_bps=cfg.paper_slippage_bps,
    ).as_dict()
    strategy = strategy or Strategy()
    registry = load_all(strategy)
    engine = PaperFillEngine(cfg.paper_fee_bps, cfg.paper_slippage_bps)
    fills: list[BacktestFill] = []
    requested_usd = 0.0
    turnover_usd = 0.0
    peak_exposure = 0.0
    rng = random.Random(0)
    for snap in snapshots:
        state = BacktestMarketState(snap)
        for intent in registry.evaluate_all(state):
            if not _simple_exposure_gate(strategy, intent):
                continue
            requested_usd += intent.size_usd
            calibrated_maker = (
                _simulate_maker(
                    intent,
                    snap,
                    rng,
                    probability=float(calibration["maker_fill_assumption"]),
                    queue_ahead=0.0,
                    latency_sec=float(calibration["latency_assumption"]),
                )
                if cfg.prefer_maker
                else None
            )
            new_fills = [calibrated_maker] if calibrated_maker is not None else _real_paper_fill(intent, snap, engine)
            fills.extend(new_fills)
            turnover_usd += sum(fill.size_usd for fill in new_fills)
            for fill in new_fills:
                strategy.update_inventory(intent.market_slug, intent.side, fill.size_usd / fill.price, fill.size_usd)
            inv = strategy.get_inv(intent.market_slug)
            peak_exposure = max(peak_exposure, inv.total_cost)
    coverage = data_source.coverage(start_ms=start_ms, end_ms=end_ms, market_id=market_id, token_id=token_id)  # type: ignore[attr-defined]
    return BacktestResult(
        fills=fills, realized_pnl_usd=0.0, outcomes=0, wins=0, gross_pnl_usd=0.0,
        data_source=REAL_HISTORICAL_SOURCE, execution_mode="PAPER_SIMULATION",
        data_coverage=coverage, data_quality_warnings=coverage["quality_warnings"],
        peak_exposure_usd=peak_exposure, turnover_usd=turnover_usd, requested_usd=requested_usd,
        calibration=calibration,
    )
