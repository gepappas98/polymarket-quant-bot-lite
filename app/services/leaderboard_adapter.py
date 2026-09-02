"""Public Polymarket Data API adapters for leaderboard and closed-position data."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

DEFAULT_URL = "https://data-api.polymarket.com/v1/leaderboard"
DEFAULT_CLOSED_POSITIONS_URL = "https://data-api.polymarket.com/closed-positions"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


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
        "limit": _bounded_int(limit, default=50, minimum=1, maximum=50),
        "offset": _bounded_int(offset, default=0, minimum=0, maximum=1000),
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
            "source": "leaderboard_aggregate",
        }]
    return history


def fetch_polymarket_closed_positions(
    *,
    address: str,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "TIMESTAMP",
    sort_direction: str = "DESC",
    url: str | None = None,
    client: httpx.Client | None = None,
) -> List[dict]:
    """Return normalized realized-PnL observations for one public wallet.

    The public ``/closed-positions`` endpoint contains realized PnL, invested
    notional and timestamps. It is therefore a more suitable scoring source
    than raw fills, which do not directly report realized PnL. Malformed rows
    and rows without a positive invested amount are discarded because they
    cannot contribute a meaningful return observation.
    """
    user = str(address or "").strip()
    if not user:
        return []

    normalized_sort_by = str(sort_by or "TIMESTAMP").upper()
    if normalized_sort_by not in {"REALIZEDPNL", "TITLE", "PRICE", "AVGPRICE", "TIMESTAMP"}:
        normalized_sort_by = "TIMESTAMP"
    normalized_direction = str(sort_direction or "DESC").upper()
    if normalized_direction not in {"ASC", "DESC"}:
        normalized_direction = "DESC"

    params = {
        "user": user,
        "limit": _bounded_int(limit, default=50, minimum=1, maximum=50),
        "offset": _bounded_int(offset, default=0, minimum=0, maximum=100000),
        "sortBy": normalized_sort_by,
        "sortDirection": normalized_direction,
    }
    endpoint = url or os.getenv("POLYMARKET_CLOSED_POSITIONS_URL", DEFAULT_CLOSED_POSITIONS_URL)
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
        raise ValueError("Polymarket closed-positions response must be a JSON list")

    observations: List[dict] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if "realizedPnl" not in entry or "totalBought" not in entry:
            continue
        size = _number(entry.get("totalBought"))
        if size <= 0:
            continue
        observations.append({
            "pnl": _number(entry.get("realizedPnl")),
            "size": size,
            "ts": entry.get("timestamp"),
            "asset": entry.get("asset"),
            "condition_id": entry.get("conditionId"),
            "slug": entry.get("slug"),
            "outcome": entry.get("outcome"),
            "avg_price": _number(entry.get("avgPrice")),
            "source": "closed_position",
        })
    return observations
