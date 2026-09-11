"""Public Polymarket CLOB market-channel WebSocket book feed.

This module is market-data-only. It never authenticates or submits orders.
The worker can use its books for paper execution and status reporting while
keeping the existing REST book fetch as a soft fallback.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Callable, Dict, Iterable, Optional

from .feeds import OrderBook

log = logging.getLogger(__name__)

DEFAULT_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class ClobWebSocketFeed:
    """Background public CLOB market feed keyed by token ID."""

    def __init__(
        self,
        url: str = DEFAULT_WS_URL,
        reconnect_max_sec: float = 30.0,
        stale_after_sec: float = 45.0,
        websocket_factory: Optional[Callable] = None,
    ) -> None:
        self.url = url
        self.reconnect_max_sec = reconnect_max_sec
        self.stale_after_sec = stale_after_sec
        self._websocket_factory = websocket_factory
        self._books: Dict[str, Dict[str, list]] = {}
        self._last_update: Dict[str, float] = {}
        self._assets: set[str] = set()
        self._lock = threading.RLock()
        self._assets_changed = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.connected = False
        self.last_error: Optional[str] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="polymarket-clob-ws", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        self._assets_changed.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self.connected = False

    def set_assets(self, asset_ids: Iterable[str]) -> None:
        assets = {str(asset_id) for asset_id in asset_ids if asset_id}
        with self._lock:
            changed = assets != self._assets
            self._assets = assets
        if changed:
            self._assets_changed.set()

    def get_book(self, asset_id: str) -> Optional[OrderBook]:
        now = time.time()
        with self._lock:
            book = self._books.get(str(asset_id))
            updated = self._last_update.get(str(asset_id), 0.0)
            if not book or now - updated > self.stale_after_sec:
                return None
            return OrderBook(
                bids=[dict(level) for level in book["bids"]],
                asks=[dict(level) for level in book["asks"]],
            )

    def book_age_ms(self, asset_id: str) -> Optional[float]:
        """Return local age of the latest WS update, or None when unavailable."""
        with self._lock:
            updated = self._last_update.get(str(asset_id))
        if not updated:
            return None
        return max(0.0, (time.time() - updated) * 1000.0)

    def apply_message(self, raw: str | bytes | dict) -> None:
        message = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        event_type = message.get("event_type") or message.get("type")
        if event_type == "book":
            asset_id = str(message.get("asset_id") or message.get("assetId") or "")
            if asset_id:
                self._replace_book(asset_id, message.get("bids") or [], message.get("asks") or [])
        elif event_type == "price_change":
            for change in message.get("price_changes") or message.get("priceChanges") or []:
                self._apply_price_change(change)
        elif event_type == "best_bid_ask":
            asset_id = str(message.get("asset_id") or message.get("assetId") or "")
            if asset_id:
                self._last_update[asset_id] = time.time()
        elif event_type == "error":
            self.last_error = str(message.get("message") or message)
            log.warning("CLOB WebSocket error: %s", self.last_error)

    def _replace_book(self, asset_id: str, bids: list, asks: list) -> None:
        with self._lock:
            self._books[asset_id] = {
                "bids": self._normalise_levels(bids),
                "asks": self._normalise_levels(asks),
            }
            self._last_update[asset_id] = time.time()

    def _apply_price_change(self, change: dict) -> None:
        asset_id = str(change.get("asset_id") or change.get("assetId") or "")
        price = change.get("price")
        side = str(change.get("side") or "").upper()
        if not asset_id or price is None or side not in {"BUY", "SELL"}:
            return
        try:
            price_s = str(price)
            size = float(change.get("size") or 0)
        except (TypeError, ValueError):
            return
        key = "bids" if side == "BUY" else "asks"
        with self._lock:
            book = self._books.setdefault(asset_id, {"bids": [], "asks": []})
            levels = book[key]
            levels[:] = [level for level in levels if str(level["price"]) != price_s]
            if size > 0:
                levels.append({"price": price_s, "size": str(size)})
                levels.sort(key=lambda level: float(level["price"]), reverse=key == "bids")
            self._last_update[asset_id] = time.time()

    @staticmethod
    def _normalise_levels(levels: list) -> list:
        result = []
        for level in levels:
            try:
                price = str(level.get("price"))
                size = str(level.get("size"))
                if float(price) > 0 and float(size) > 0:
                    result.append({"price": price, "size": size})
            except (AttributeError, TypeError, ValueError):
                continue
        return result

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._run_connection()
                backoff = 1.0
            except Exception as exc:  # noqa: BLE001 - reconnect loop must survive network errors
                self.connected = False
                self.last_error = str(exc)
                log.warning("CLOB WebSocket disconnected: %s; retrying in %.1fs", exc, backoff)
                self._stop.wait(backoff)
                backoff = min(self.reconnect_max_sec, backoff * 2)

    def _run_connection(self) -> None:
        factory = self._websocket_factory
        if factory is None:
            import websockets.sync.client
            factory = websockets.sync.client.connect
        with factory(self.url, open_timeout=10, close_timeout=3, ping_interval=None) as websocket:
            self.connected = True
            self.last_error = None
            self._send_subscription(websocket)
            last_ping = time.monotonic()
            while not self._stop.is_set():
                if self._assets_changed.wait(timeout=0.25):
                    self._assets_changed.clear()
                    self._send_subscription(websocket)
                if time.monotonic() - last_ping >= 10:
                    websocket.send("PING")
                    last_ping = time.monotonic()
                try:
                    raw = websocket.recv(timeout=0.25)
                except TimeoutError:
                    continue
                if raw in (None, "PONG", b"PONG"):
                    continue
                self.apply_message(raw)
        self.connected = False

    def _send_subscription(self, websocket) -> None:
        with self._lock:
            assets = sorted(self._assets)
        if not assets:
            return
        websocket.send(json.dumps({
            "assets_ids": assets,
            "type": "market",
            "initial_dump": True,
            "custom_feature_enabled": True,
        }))
        log.info("CLOB WebSocket subscribed to %d asset(s)", len(assets))


__all__ = ["ClobWebSocketFeed", "DEFAULT_WS_URL"]
