"""Long-running REAL Polymarket CLOB recorder process."""
from __future__ import annotations

import json
import logging
import time
from typing import Callable, Iterable

from .historical_recorder import DEFAULT_WS_URL, HistoricalRecorder, TokenMetadata

log = logging.getLogger(__name__)


class RecorderService:
    """Run one public market-channel connection and safely reconnect it.

    The service never submits orders and never falls back to synthetic prices.
    """

    def __init__(self, recorder: HistoricalRecorder, url: str = DEFAULT_WS_URL, reconnect_max_seconds: float = 30.0, websocket_factory: Callable | None = None):
        self.recorder, self.url = recorder, url
        self.reconnect_max_seconds, self.websocket_factory = reconnect_max_seconds, websocket_factory
        self.stop_requested = False

    def subscription(self) -> str:
        return json.dumps({"assets_ids": sorted(self.recorder.tokens), "type": "market", "initial_dump": True, "custom_feature_enabled": True})

    def stop(self) -> None:
        self.stop_requested = True

    def run_forever(self) -> None:
        backoff = 1.0
        while not self.stop_requested:
            try:
                self._run_connection()
                backoff = 1.0
            except Exception as exc:  # network libraries expose several exception types
                self.recorder.metrics.reconnects += 1
                log.warning("Polymarket CLOB recorder disconnected: %s; retrying in %.1fs", exc, backoff)
                time.sleep(backoff)
                backoff = min(self.reconnect_max_seconds, backoff * 2)

    def _run_connection(self) -> None:
        factory = self.websocket_factory
        if factory is None:
            import websockets.sync.client
            factory = websockets.sync.client.connect
        with factory(self.url, open_timeout=10, close_timeout=3, ping_interval=None) as websocket:
            websocket.send(self.subscription())
            for token_id in self.recorder.tokens:
                try:
                    self.recorder.reconcile(token_id)
                except Exception as exc:
                    log.warning("Initial REST snapshot failed for %s: %s", token_id, exc)
            last_ping = time.monotonic()
            while not self.stop_requested:
                if time.monotonic() - last_ping >= 10:
                    websocket.send("PING")
                    last_ping = time.monotonic()
                try:
                    raw = websocket.recv(timeout=0.25)
                except TimeoutError:
                    self.recorder.reconcile_stale()
                    continue
                if raw in (None, "PONG", b"PONG"):
                    continue
                self.recorder.handle_message(raw)
        # A reconnect always gets fresh REST books before applying deltas.
        self.recorder.metrics.reconnects += 1


__all__ = ["RecorderService"]
