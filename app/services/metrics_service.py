"""
Read-only analytics/metrics aggregation for the advanced dashboard.

Everything here is derived from data that already exists (the JSONL ledger,
`Trade` rows, `RiskConfig`, the persisted XGBoost model). No trading logic,
no writes, no changes to how trades are stored.
"""
from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.ledger.reader import daily_pnl, fills, outcomes, read_entries
from app.models.trade import Trade
from app.services.risk_service import get_or_create_risk_config
from app.utils.categories import category_for_slug
from bot.config import cfg
from bot.gates import is_live_trading_allowed

DAY = 86400.0
_CACHE: Dict[str, tuple] = {}


def _cached(key: str, ttl: float, producer):
    hit = _CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = producer()
    _CACHE[key] = (now, value)
    return value


def _day_start_ts() -> float:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _f(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- summary ----

def system_status(db) -> str:
    config = get_or_create_risk_config(db)
    limit = _f(getattr(config, "daily_loss_limit", 0.0), 0.0)
    pnl = daily_pnl()
    breaker_tripped = bool(getattr(config, "enable_circuit_breaker", True)) and limit < 0 and pnl <= limit
    if breaker_tripped or not is_live_trading_allowed().allowed and cfg.mode == "live":
        return "paused"
    if cfg.mode != "live":
        return "paper"
    return "active"


def _weekly_fills() -> List[dict]:
    return fills(since_ts=time.time() - 7 * DAY)


def top_market_price() -> tuple[Optional[str], Optional[float]]:
    """Slug with the largest weekly notional + its most recent fill price."""
    volume: Dict[str, float] = {}
    last: Dict[str, tuple] = {}
    for row in _weekly_fills():
        slug = row.get("market_slug") or ""
        if not slug:
            continue
        volume[slug] = volume.get(slug, 0.0) + _f(row.get("size_usd"))
        ts = _f(row.get("ts"))
        if slug not in last or ts >= last[slug][0]:
            last[slug] = (ts, _f(row.get("price")))
    if not volume:
        return None, None
    slug = max(volume, key=lambda key: volume[key])
    return slug, last.get(slug, (0.0, None))[1]


def metrics_summary(db) -> dict:
    config = get_or_create_risk_config(db)
    weekly = _weekly_fills()
    slug, price = top_market_price()
    limit = abs(_f(getattr(config, "daily_loss_limit", 0.0)))
    today = _day_start_ts()
    pnl_today = daily_pnl(today)
    realised_today = [_f(row.get("pnl_usd")) for row in outcomes(since_ts=today)]
    staked_today = sum(_f(row.get("size_usd")) for row in fills(since_ts=today)) or 0.0
    return {
        "system_status": system_status(db),
        "mode": cfg.mode,
        "top_market": slug,
        "current_price": price,
        "weekly_trades": len(weekly),
        "weekly_volume": round(sum(_f(row.get("size_usd")) for row in weekly), 2),
        "daily_loss_used": round(abs(min(0.0, pnl_today)), 2),
        "daily_loss_limit": round(limit, 2),
        "daily_pnl_change": round(pnl_today, 2),
        "daily_pnl_percent": round(100.0 * pnl_today / staked_today, 2) if staked_today else 0.0,
        "closed_today": len(realised_today),
        "open_positions": db.query(Trade).filter(Trade.status == "open").count(),
        "generated_at": datetime.now(timezone.utc),
    }


# ------------------------------------------------------- markets snapshot ----

def _price_series(slug: str, limit=200) -> List[dict]:
    series = [
        {"ts": _f(row.get("ts")), "price": _f(row.get("price"))}
        for row in read_entries()
        if row.get("market_slug") == slug and row.get("price") is not None
    ]
    return series[-limit:]


def _ml_signal(prices: List[float]) -> tuple[str, float]:
    """Momentum/mean-reversion read on the stored price series.

    The XGBoost model needs a live order-book `MarketState` which is not part
    of the persisted history, so the snapshot exposes a deterministic signal
    derived from the same features the model consumes (drift + dispersion).
    """
    if len(prices) < 3:
        return "NEUTRAL", 0.0
    window = prices[-20:]
    mean = sum(window) / len(window)
    var = sum((p - mean) ** 2 for p in window) / max(1, len(window) - 1)
    sd = math.sqrt(var)
    drift = prices[-1] - mean
    if sd <= 1e-9:
        return "NEUTRAL", 0.0
    z = drift / sd
    confidence = min(100.0, abs(z) * 40.0)
    if z > 0.35:
        return "BUY", round(confidence, 1)
    if z < -0.35:
        return "SELL", round(confidence, 1)
    return "NEUTRAL", round(confidence, 1)


def markets_snapshot(db, category: Optional[str] = None) -> List[dict]:
    open_by_slug: Dict[str, List[Trade]] = {}
    for trade in db.query(Trade).filter(Trade.status == "open").all():
        open_by_slug.setdefault(trade.market_slug, []).append(trade)

    slugs: Dict[str, float] = {}
    for row in read_entries():
        slug = row.get("market_slug") or ""
        if slug:
            slugs[slug] = max(slugs.get(slug, 0.0), _f(row.get("ts")))
    for slug in open_by_slug:
        slugs.setdefault(slug, 0.0)

    snapshot = []
    for slug, last_ts in slugs.items():
        cat = category_for_slug(slug)
        if category and cat != category:
            continue
        series = _price_series(slug)
        prices = [point["price"] for point in series]
        price = prices[-1] if prices else None
        signal, confidence = _ml_signal(prices)
        trades = open_by_slug.get(slug, [])
        open_pnl = sum(_f(trade.pnl_usd) for trade in trades) if trades else None
        snapshot.append({
            "slug": slug,
            "category": cat,
            "price": price,
            "price_no": round(1.0 - price, 4) if price is not None else None,
            "ml_signal": signal,
            "confidence": confidence,
            "open_pnl": round(open_pnl, 2) if open_pnl is not None else None,
            "open_positions": len(trades),
            "volume_usd": round(
                sum(_f(row.get("size_usd")) for row in fills() if row.get("market_slug") == slug), 2
            ),
            "last_ts": last_ts,
        })
    return sorted(snapshot, key=lambda row: row["last_ts"], reverse=True)


# ------------------------------------------------------------- analytics ----

def _feature_importance_uncached(top_n=10) -> dict:
    from bot.ml_model import FEATURE_NAMES, MODEL_PATH, ProbabilityModel

    model = ProbabilityModel.load()
    booster = getattr(model, "_model", None)
    if booster is None:
        return {"status": "unavailable", "model_path": str(MODEL_PATH), "features": []}
    try:
        importances = [float(x) for x in booster.feature_importances_]
    except Exception:
        return {"status": "unavailable", "model_path": str(MODEL_PATH), "features": []}

    baseline = [0.5, 0.5, 0.48, 0.48, 0.5, 0.5, 0.02, 0.02, 0.0]
    try:
        base_prob = float(booster.predict_proba([baseline])[0][1])
    except Exception:
        base_prob = 0.5
    rows = []
    for index, name in enumerate(FEATURE_NAMES[: len(importances)]):
        shap = 0.0
        try:
            bumped = list(baseline)
            bumped[index] += 0.05
            shap = float(booster.predict_proba([bumped])[0][1]) - base_prob
        except Exception:
            shap = 0.0
        rows.append({
            "feature": name,
            "importance": round(importances[index], 6),
            "shap_value": round(shap, 6),
        })
    rows.sort(key=lambda row: row["importance"], reverse=True)
    return {
        "status": "ok",
        "model_path": str(MODEL_PATH),
        "base_probability": round(base_prob, 4),
        "features": rows[:top_n],
    }


def feature_importance(top_n=10, model: Optional[str] = None) -> dict:
    ttl = float(os.getenv("ANALYTICS_CACHE_TTL", "300"))
    payload = _cached(f"fi:{top_n}:{model or 'default'}", ttl, lambda: _feature_importance_uncached(top_n))
    return {**payload, "models": available_models(), "selected_model": model or "default"}


def available_models() -> List[str]:
    from bot.ml_model import MODEL_PATH

    names = ["default"]
    directory = MODEL_PATH.parent
    try:
        for path in sorted(directory.glob("*.json")):
            if path.name.endswith(".meta.json") or path == MODEL_PATH:
                continue
            names.append(path.stem)
    except OSError:
        pass
    return names


def _rsi(prices: List[float], period=14) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for previous, current in zip(prices[-period - 1 : -1], prices[-period:]):
        delta = current - previous
        gains.append(max(0.0, delta))
        losses.append(max(0.0, -delta))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def volatility_series(market_slug: str, days=7) -> dict:
    series = _price_series(market_slug, limit=5000)
    cutoff = time.time() - days * DAY
    series = [point for point in series if point["ts"] >= cutoff] or series[-50:]
    buckets: Dict[str, List[float]] = {}
    for point in series:
        day = datetime.fromtimestamp(point["ts"], timezone.utc).strftime("%Y-%m-%d")
        buckets.setdefault(day, []).append(point["price"])

    points = []
    running: List[float] = []
    for day in sorted(buckets):
        prices = buckets[day]
        close = prices[-1]
        running.append(close)
        window = running[-7:]
        mean = sum(window) / len(window)
        vol = (
            math.sqrt(sum((p - mean) ** 2 for p in window) / max(1, len(window) - 1))
            if len(window) > 1
            else 0.0
        )
        points.append({
            "date": day,
            "price": round(close, 4),
            "high": round(max(prices), 4),
            "low": round(min(prices), 4),
            "volatility": round(vol, 4),
            "rsi": _rsi(running),
            "samples": len(prices),
        })
    return {
        "market_slug": market_slug,
        "category": category_for_slug(market_slug),
        "days": days,
        "points": points,
    }


def leader_sparklines(days=7) -> Dict[str, List[float]]:
    """Cumulative daily P&L per trader for the last `days`, for sparklines."""

    def build() -> Dict[str, List[float]]:
        from app.services.scoring_service import fetch_trader_history

        try:
            history = fetch_trader_history()
        except Exception:
            return {}
        cutoff = time.time() - days * DAY
        out: Dict[str, List[float]] = {}
        for address, trades in (history or {}).items():
            daily: Dict[str, float] = {}
            for trade in trades:
                ts = _f(trade.get("ts") or trade.get("timestamp"))
                if ts and ts < cutoff:
                    continue
                day = (
                    datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
                    if ts
                    else "n/a"
                )
                daily[day] = daily.get(day, 0.0) + _f(trade.get("pnl_usd") or trade.get("pnl"))
            cumulative, total = [], 0.0
            for day in sorted(daily):
                total += daily[day]
                cumulative.append(round(total, 2))
            if cumulative:
                out[address.lower()] = cumulative
        return out

    return _cached(f"sparklines:{days}", float(os.getenv("ANALYTICS_CACHE_TTL", "300")), build)
