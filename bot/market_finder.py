"""
Deterministic discovery of active short-term crypto Up/Down markets.
Uses the common slug patterns observed on Polymarket (btc-updown-5m-{ts}, etc.).
"""

import time
import logging
from typing import Optional, Dict, List
import requests
from datetime import datetime, timezone

from .config import cfg

log = logging.getLogger(__name__)


def current_window_start(window_minutes: int) -> int:
    """Return the UTC unix timestamp of the current window start."""
    now = int(time.time())
    return (now // (window_minutes * 60)) * (window_minutes * 60)


def slug_candidates(asset: str, window_minutes: int, window_ts: int) -> List[str]:
    asset = asset.lower()
    w = window_minutes
    # Most common patterns observed in 2026
    return [
        f"{asset}-updown-{w}m-{window_ts}",
        f"{asset}-up-or-down-{w}-minute-windows-{window_ts}",
        f"{asset}-up-or-down-{w}m-{window_ts}",
        f"{asset}-updown-{w}-{window_ts}",
    ]


def fetch_market_by_slug(slug: str) -> Optional[Dict]:
    try:
        url = f"{cfg.gamma_host}/events"
        resp = requests.get(url, params={"slug": slug}, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        events = data if isinstance(data, list) else data.get("data", data.get("events", []))
        if not events:
            return None
        event = events[0]
        return parse_event(event)
    except Exception as e:
        log.debug(f"Slug fetch failed for {slug}: {e}")
        return None


def parse_event(event: Dict) -> Optional[Dict]:
    markets = event.get("markets") or []
    if not markets:
        return None
    market = markets[0]

    # clobTokenIds is usually a JSON string or list
    token_ids = market.get("clobTokenIds") or market.get("clob_token_ids")
    if isinstance(token_ids, str):
        import json
        try:
            token_ids = json.loads(token_ids)
        except Exception:
            return None

    if not token_ids or len(token_ids) < 2:
        return None

    outcomes = market.get("outcomes")
    if isinstance(outcomes, str):
        import json
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = ["Up", "Down"]

    # Map Up / Down
    up_idx, down_idx = 0, 1
    for i, o in enumerate(outcomes):
        if str(o).lower() in ("up", "yes"):
            up_idx = i
        if str(o).lower() in ("down", "no"):
            down_idx = i

    return {
        "slug": event.get("slug") or market.get("slug"),
        "condition_id": market.get("conditionId") or market.get("condition_id"),
        "question": market.get("question") or event.get("title"),
        "end_date": market.get("endDate") or event.get("endDate"),
        "up_token_id": str(token_ids[up_idx]),
        "down_token_id": str(token_ids[down_idx]),
        "active": market.get("active", True) and not market.get("closed", False),
        "accepting_orders": market.get("acceptingOrders", True),
        "raw": market,
    }


def find_active_market(asset: str, window_minutes: int) -> Optional[Dict]:
    """Find the currently active Up/Down market for the given asset + window."""
    window_ts = current_window_start(window_minutes)
    for slug in slug_candidates(asset, window_minutes, window_ts):
        m = fetch_market_by_slug(slug)
        if m and m.get("active") and m.get("accepting_orders"):
            m["window_minutes"] = window_minutes
            m["window_ts"] = window_ts
            m["asset"] = asset.upper()
            log.info(f"Found market: {m['slug']}  (ends ~{m.get('end_date')})")
            return m
    log.warning(f"No active {asset} {window_minutes}m market found for ts={window_ts}")
    return None


def fetch_resolution(slug: str) -> Optional[Dict]:
    """
    Poll Gamma for a market's settlement status.
    Returns {"resolved": bool, "winner": "UP"|"DOWN"|None}, or None on fetch failure
    (treat None as "try again later", not as "not resolved").
    """
    try:
        url = f"{cfg.gamma_host}/events"
        resp = requests.get(url, params={"slug": slug}, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        events = data if isinstance(data, list) else data.get("data", data.get("events", []))
        if not events:
            return None
        event = events[0]
        markets = event.get("markets") or []
        if not markets:
            return None
        market = markets[0]

        if not market.get("closed", False):
            return {"resolved": False, "winner": None}

        outcomes = market.get("outcomes")
        if isinstance(outcomes, str):
            import json
            try:
                outcomes = json.loads(outcomes)
            except Exception:
                outcomes = ["Up", "Down"]

        prices = market.get("outcomePrices")
        if isinstance(prices, str):
            import json
            try:
                prices = json.loads(prices)
            except Exception:
                prices = None
        if not prices:
            # Closed on-chain but Gamma hasn't published settlement prices yet.
            return {"resolved": True, "winner": None}

        prices = [float(p) for p in prices]
        winner_idx = max(range(len(prices)), key=lambda i: prices[i])
        winner_label = str(outcomes[winner_idx]).upper() if outcomes and winner_idx < len(outcomes) else None
        if winner_label in ("UP", "YES"):
            winner = "UP"
        elif winner_label in ("DOWN", "NO"):
            winner = "DOWN"
        else:
            winner = None
        return {"resolved": True, "winner": winner}
    except Exception as e:
        log.debug(f"Resolution fetch failed for {slug}: {e}")
        return None


def find_all_active() -> List[Dict]:
    results = []
    for asset in cfg.assets:
        for w in cfg.windows:
            m = find_active_market(asset.strip(), w)
            if m:
                results.append(m)
    return results