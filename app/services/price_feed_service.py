"""CLOB market-price adapter for persisted app-side open positions."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.trade import Trade
from app.services.trading_service import process_price_update
from bot.config import cfg

log = logging.getLogger(__name__)

DEFAULT_MIDPOINT_PATH = "/midpoint"


@dataclass
class PriceFeedUpdate:
    trade_id: int
    token_id: str
    price: float
    status: str


def _price_from_payload(payload: Any) -> Optional[float]:
    if not isinstance(payload, dict):
        return None
    for key in ("mid", "midpoint", "price"):
        try:
            price = float(payload[key])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < price < 1:
            return price
    return None


def fetch_clob_midpoint(
    token_id: str,
    *,
    client: httpx.Client | None = None,
    endpoint: str | None = None,
) -> Optional[float]:
    """Fetch a token midpoint from the public CLOB API, failing soft on errors."""
    token = str(token_id or "").strip()
    if not token:
        return None
    owns_client = client is None
    http = client or httpx.Client(timeout=cfg.http_timeout)
    try:
        response = http.get(
            endpoint or f"{cfg.clob_host.rstrip('/')}{DEFAULT_MIDPOINT_PATH}",
            params={"token_id": token},
        )
        response.raise_for_status()
        return _price_from_payload(response.json())
    except Exception as exc:  # noqa: BLE001 - market data is best effort
        log.debug("CLOB midpoint fetch failed for %s: %s", token, exc)
        return None
    finally:
        if owns_client:
            http.close()


def update_open_trade_prices(*, db, client: httpx.Client | None = None, executor=None) -> list[PriceFeedUpdate]:
    """Fetch prices and route them through ``process_price_update``.

    The existing service owns persistence, trailing-stop evaluation and paper/live
    execution. This adapter only supplies prices, so it cannot bypass the safety
    gates or alter the execution boundary.
    """
    trades = db.scalars(
        select(Trade).where(Trade.status == "open", Trade.token_id.is_not(None))
    ).all()
    updates: list[PriceFeedUpdate] = []
    for trade in trades:
        price = fetch_clob_midpoint(str(trade.token_id), client=client)
        if price is None:
            continue
        try:
            result = process_price_update(trade.id, price, db=db, executor=executor)
        except Exception as exc:  # noqa: BLE001 - one stale position must not stop the feed
            log.warning("price update failed for trade %s: %s", trade.id, exc)
            continue
        updates.append(PriceFeedUpdate(trade.id, str(trade.token_id), price, result.status))
    return updates


class CLOBPriceFeed:
    """Optional background poller for the FastAPI sidecar.

    Disabled by default. Enable with ``CLOB_PRICE_FEED_ENABLED=true``. A new
    SQLAlchemy session is created for every cycle and the loop is cancellable,
    which keeps the API process safe during shutdown and avoids sharing sessions
    across asynchronous iterations.
    """

    def __init__(self, interval_seconds: float | None = None):
        self.interval_seconds = interval_seconds or float(os.getenv("CLOB_PRICE_FEED_INTERVAL_SECONDS", "4"))
        self.interval_seconds = max(1.0, self.interval_seconds)

    async def run(self) -> None:
        import asyncio

        while True:
            try:
                await asyncio.to_thread(self.poll_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("CLOB price-feed cycle failed")
            await asyncio.sleep(self.interval_seconds)

    def poll_once(self) -> list[PriceFeedUpdate]:
        with SessionLocal() as db:
            return update_open_trade_prices(db=db)
