import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.utils.categories import category_for_slug

LEDGER_PATH = os.getenv("LEDGER_PATH", "data/trades.jsonl")


def read_entries(path=None) -> List[dict]:
    try:
        from bot.ledger import ledger
        if ledger._entries:
            rows = [asdict(e) if is_dataclass(e) else dict(e) for e in ledger._entries]
            return sorted(rows, key=lambda row: row.get("ts", 0))
    except Exception:
        pass
    target = Path(path or os.getenv("LEDGER_PATH", LEDGER_PATH))
    rows = []
    try:
        with target.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except (json.JSONDecodeError, TypeError):
                    continue
    except OSError:
        return []
    return sorted(rows, key=lambda row: row.get("ts", 0))


def _filter(kind, category=None, since_ts=None, until_ts=None):
    return [
        row for row in read_entries()
        if row.get("kind") == kind
        and (category is None or category_for_slug(row.get("market_slug", "")) == category)
        and (since_ts is None or row.get("ts", 0) >= since_ts)
        and (until_ts is None or row.get("ts", 0) <= until_ts)
    ]


def fills(category=None, since_ts=None, until_ts=None):
    return _filter("fill", category, since_ts, until_ts)


def outcomes(category=None, since_ts=None, until_ts=None):
    return _filter("outcome", category, since_ts, until_ts)


def daily_pnl(day_start_ts=None) -> float:
    if day_start_ts is None:
        now = datetime.now(timezone.utc)
        day_start_ts = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return float(sum(row.get("pnl_usd") or 0.0 for row in outcomes(since_ts=day_start_ts)))


def recent_category_pnls(category, n=20):
    return [float(row.get("pnl_usd") or 0.0) for row in outcomes(category=category)][-n:]


def trade_history(category=None, start_ts=None, end_ts=None, status=None, limit=200):
    rows = {}
    for entry in read_entries():
        if entry.get("kind") not in ("fill", "outcome"):
            continue
        if category and category_for_slug(entry.get("market_slug", "")) != category:
            continue
        ts = entry.get("ts", 0)
        if start_ts is not None and ts < start_ts or end_ts is not None and ts > end_ts:
            continue
        key = (entry.get("market_slug"), entry.get("order_id") or entry.get("side"))
        if entry.get("kind") == "outcome" and not entry.get("order_id"):
            candidates = [candidate for candidate in rows if candidate[0] == entry.get("market_slug")]
            if len(candidates) == 1:
                key = candidates[0]
        row = rows.setdefault(key, {
            "ts": ts, "market_slug": entry.get("market_slug", ""),
            "category": category_for_slug(entry.get("market_slug", "")),
            "side": entry.get("side"), "price": entry.get("price"),
            "size_usd": entry.get("size_usd"), "pnl_usd": None,
            "status": "open", "dry_run": entry.get("dry_run", True),
            "order_id": entry.get("order_id"),
        })
        row["ts"] = min(row["ts"], ts)
        if entry.get("kind") == "fill":
            row.update(price=entry.get("price"), size_usd=entry.get("size_usd"), order_id=entry.get("order_id"), dry_run=entry.get("dry_run", True))
        else:
            row.update(pnl_usd=entry.get("pnl_usd"), status="closed", ts=entry.get("ts", row["ts"]))
    result = list(rows.values())
    if status:
        result = [row for row in result if row["status"] == status]
    return sorted(result, key=lambda row: row.get("ts", 0), reverse=True)[:limit]
