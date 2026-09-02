import logging
import os
import random
from statistics import mean, median, stdev
from typing import Dict, List, Tuple

import httpx
from sqlalchemy import select

from app.ledger.reader import trade_history
from app.models.leader import Leader

log = logging.getLogger(__name__)


def hampel_filter(values: List[float], threshold=3.5) -> Tuple[List[float], List[int]]:
    if not values:
        return [], []
    med = median(values)
    mad = median([abs(v - med) for v in values])
    scaled = mad * 1.4826
    if scaled == 0:
        return list(values), []
    result, outliers = list(values), []
    for i, value in enumerate(values):
        if abs(value - med) / scaled > threshold:
            result[i] = med
            outliers.append(i)
    return result, outliers


def _norm(values):
    if not values or max(values) == min(values):
        return [50.0] * len(values)
    lo, hi = min(values), max(values)
    return [100.0 * (v - lo) / (hi - lo) for v in values]


def compute_leader_scores(trader_history: Dict[str, List[dict]]) -> List[dict]:
    raw = []
    for address, trades in trader_history.items():
        pnls = [float(t.get("pnl", 0)) for t in trades]
        sizes = [float(t.get("size", 0) or 0) for t in trades]
        returns = [p / s for p, s in zip(pnls, sizes) if s]
        avg = mean(returns) if returns else 0.0
        deviation = stdev(returns) if len(returns) >= 2 else 0.0
        sharpe = avg / deviation if len(returns) >= 2 and deviation else 0.0
        total_size = sum(sizes)
        roi = sum(pnls) / total_size * 100 if total_size else 0.0
        peak = 0.0
        cumulative = 0.0
        max_dd = 0.0
        for pnl in pnls:
            cumulative += pnl
            peak = max(peak, cumulative)
            if peak > 0:
                max_dd = max(max_dd, (peak - cumulative) / max(peak, 1) * 100)
        stability = 100 * (1 - deviation / (abs(avg) + deviation + 1e-9)) if returns else 0.0
        raw.append({"address": address, "trade_count": len(trades), "win_rate": 100 * sum(p > 0 for p in pnls) / len(pnls) if pnls else 0.0, "sharpe_ratio": sharpe, "roi": roi, "max_drawdown": max_dd, "stability_score": max(0.0, min(100.0, stability))})
    sharpe, _ = hampel_filter([r["sharpe_ratio"] for r in raw])
    roi, _ = hampel_filter([r["roi"] for r in raw])
    ns, nr = _norm(sharpe), _norm(roi)
    for i, row in enumerate(raw):
        row["sharpe_ratio"], row["roi"] = sharpe[i], roi[i]
        row["composite_score"] = round(0.30 * ns[i] + 0.25 * nr[i] + 0.20 * row["win_rate"] + 0.15 * (100 - min(row["max_drawdown"], 100)) + 0.10 * row["stability_score"], 4)
        for key in ("win_rate", "sharpe_ratio", "roi", "max_drawdown", "stability_score"):
            row[key] = round(row[key], 4)
    return sorted(raw, key=lambda r: r["composite_score"], reverse=True)


def fetch_trader_history() -> Dict[str, List[dict]]:
    url = os.getenv("LEADERBOARD_SOURCE_URL")
    if url:
        try:
            response = httpx.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                return data
        except Exception as exc:
            log.warning("leaderboard fetch failed: %s", exc)
    history = {}
    own = trade_history(status="closed")
    if own:
        history["self"] = [{"pnl": r.get("pnl_usd", 0), "size": r.get("size_usd", 1), "ts": r.get("ts")} for r in own]
    rng = random.Random(42)
    for i in range(6):
        address = f"0xMOCK{i:02d}"
        quality = 0.65 - i * 0.06
        history[address] = [{"pnl": (rng.uniform(2, 10) if rng.random() < quality else -rng.uniform(1, 8)), "size": rng.uniform(10, 100), "ts": j} for j in range(30)]
    return history


def refresh_leaderboard(db, source=None):
    scores = compute_leader_scores(source or fetch_trader_history())
    addresses = {row["address"] for row in scores}
    for row in scores:
        leader = db.scalar(select(Leader).where(Leader.address == row["address"]))
        if leader is None:
            leader = Leader(address=row["address"])
            db.add(leader)
        for key, value in row.items():
            if key != "address":
                setattr(leader, key, value)
        leader.last_updated = __import__("datetime").datetime.utcnow()
    for leader in db.scalars(select(Leader)).all():
        if leader.address not in addresses:
            db.delete(leader)
    db.commit()
    return db.scalars(select(Leader).order_by(Leader.composite_score.desc())).all()


def get_leaders(db, limit=50):
    return db.scalars(select(Leader).order_by(Leader.composite_score.desc()).limit(limit)).all()
