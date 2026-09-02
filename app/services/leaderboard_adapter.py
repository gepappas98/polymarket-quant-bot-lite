"""Public Polymarket Data API adapter for trader leaderboard snapshots."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

DEFAULT_URL = "https://data-api.polymarket.com/v1/leaderboard"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _address(entry: dict) -> str:
    return str(entry.get("proxyWallet") or entry.get("wallet") or entry.get("address") or "").strip()


def fetch_polymarket_leaderboard(
    *,
    category: str = "OVERALL",
    time_period: str = "ALL",
    order_by: str = "PNL",
    limit: int = 50,
    offset: int = 0,
    url: str | None = None,
    client: httpx.Client | None = None,
) -> Dict[str, List[dict]]:
    """Fetch aggregate public leaderboard rows and normalize them for scoring.

    The scoring layer expects a mapping of trader address to trade-like rows.
    The public leaderboard exposes aggregate PnL and volume, so each row is
    represented as one normalized observation. Numeric strings and either
    ``proxyWallet`` or ``wallet`` are accepted for API compatibility.
    """
    params = {
        "category": category.upper(),
        "timePeriod": time_period.upper(),
        "orderBy": order_by.upper(),
        "limit": max(1, min(int(limit), 50)),
        "offset": max(0, min(int(offset), 1000)),
    }
    endpoint = url or os.getenv("POLYMARKET_LEADERBOARD_URL", DEFAULT_URL)
    owns_client = client is None
    http = client or httpx.Client(timeout=float(os.getenv("LEADERBOARD_TIMEOUT", "10")))
    try:
        response = http.get(endpoint, params=params)
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            http.close()

    if not isinstance(payload, list):
        raise ValueError("Polymarket leaderboard response must be a JSON list")

    history: Dict[str, List[dict]] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        address = _address(entry)
        if not address:
            continue
        pnl = _number(entry.get("pnl"))
        volume = max(_number(entry.get("vol", entry.get("volume"))), 0.0)
        history[address] = [{
            "pnl": pnl,
            "size": volume,
            "ts": entry.get("rank"),
            "rank": entry.get("rank"),
            "user_name": entry.get("userName"),
            "verified_badge": bool(entry.get("verifiedBadge", False)),
        }]
    return history
