"""
Market data layer.

- OrderBook: one CLOB order book snapshot for a single outcome token.
  Interface matches tests/test_strategy.py::FakeBook exactly (best_bid,
  best_ask, mid) — that fake was written to stand in for this class.
- fetch_order_book(): pulls a book from the Polymarket CLOB REST API,
  with the same retry/timeout knobs (cfg.http_retries/http_timeout) the
  rest of the codebase already uses (see bot/market_finder.py).
- PriceFeed: optional external spot price via ccxt (Binance by default).
  NOT currently consumed by bot/strategy.py's directional tilt (which
  uses Polymarket book imbalance only, per the comment in strategy.py) —
  this is the hook point for the ROADMAP's still-open "window open-price
  delta" item. It fails soft: if ccxt or the network is unavailable,
  get_price() just returns None instead of raising.
- MarketState: wraps one active market (dict shape from
  bot/market_finder.py::parse_event) with its live UP/DOWN order books.
  Interface matches tests/test_strategy.py::FakeState exactly (.market,
  .up_book, .down_book, .up_ask, .down_ask, .sum_asks, .arb_available).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from .config import cfg

log = logging.getLogger(__name__)


class OrderBook:
    """CLOB order book snapshot for a single outcome token."""

    def __init__(self, bids: Optional[List[dict]] = None, asks: Optional[List[dict]] = None):
        self._bids = bids or []
        self._asks = asks or []

    @property
    def best_bid(self) -> Optional[float]:
        """Highest price someone is willing to buy at."""
        if not self._bids:
            return None
        try:
            return max(float(b["price"]) for b in self._bids)
        except (KeyError, ValueError, TypeError):
            return None

    @property
    def best_ask(self) -> Optional[float]:
        """Lowest price someone is willing to sell at (what we'd pay to BUY)."""
        if not self._asks:
            return None
        try:
            return min(float(a["price"]) for a in self._asks)
        except (KeyError, ValueError, TypeError):
            return None

    @property
    def mid(self) -> Optional[float]:
        bid, ask = self.best_bid, self.best_ask
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        return ask if ask is not None else bid

    @classmethod
    def empty(cls) -> "OrderBook":
        return cls([], [])


def fetch_order_book(token_id: str) -> OrderBook:
    """
    GET {cfg.clob_host}/book?token_id=...
    Expected CLOB response shape: {"bids": [{"price": "0.48", "size": "..."}],
                                    "asks": [{"price": "0.49", "size": "..."}]}
    Retries cfg.http_retries times with a short linear backoff; on total
    failure returns an empty book (fail soft — bot/strategy.py already treats
    up_ask/down_ask is None as "skip this market this cycle", it never crashes
    on a missing book).
    """
    url = f"{cfg.clob_host}/book"
    last_err: Optional[Exception] = None
    for attempt in range(max(cfg.http_retries, 1)):
        try:
            resp = requests.get(url, params={"token_id": token_id}, timeout=cfg.http_timeout)
            resp.raise_for_status()
            data = resp.json()
            return OrderBook(bids=data.get("bids") or [], asks=data.get("asks") or [])
        except Exception as e:  # noqa: BLE001 - deliberately broad, this is a best-effort network call
            last_err = e
            time.sleep(0.25 * (attempt + 1))
    log.debug(f"order book fetch failed for token {token_id} after {cfg.http_retries} attempt(s): {last_err}")
    return OrderBook.empty()


class PriceFeed:
    """
    Lightweight external spot-price feed via ccxt (Binance by default).
    Constructed once in bot/main.py and passed into every MarketState.

    Safe to construct even without ccxt installed or without network access —
    falls back to returning None from get_price() rather than raising, so it
    never blocks the paper-trading loop.
    """

    def __init__(self, exchange_id: str = "binance", cache_ttl_sec: float = 2.0):
        self._exchange = None
        self._cache: Dict[str, tuple] = {}  # symbol -> (price, fetched_at)
        self._cache_ttl_sec = cache_ttl_sec
        try:
            import ccxt  # local import: keep ccxt optional at module import time
            exchange_cls = getattr(ccxt, exchange_id)
            self._exchange = exchange_cls({"enableRateLimit": True})
        except Exception as e:
            log.warning(
                f"PriceFeed: ccxt exchange '{exchange_id}' unavailable ({e}) — "
                "external price feed disabled, strategy falls back to book-only signals"
            )

    def get_price(self, asset: str) -> Optional[float]:
        """Latest spot price for `asset` (e.g. 'BTC') in USD, or None if unavailable."""
        if self._exchange is None:
            return None
        symbol = f"{asset.upper()}/USDT"
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and (now - cached[1]) < self._cache_ttl_sec:
            return cached[0]
        try:
            ticker = self._exchange.fetch_ticker(symbol)
            price = float(ticker["last"])
            self._cache[symbol] = (price, now)
            return price
        except Exception as e:
            log.debug(f"PriceFeed.get_price({asset}) failed: {e}")
            return None

    def anchor_window(self, market_key: str, asset: str) -> Optional[float]:
        """
        Capture (once) the spot price at first observation of this market window.
        Returns the open/anchor price, or None if spot unavailable.
        """
        if not hasattr(self, "_window_open"):
            self._window_open = {}
        if market_key in self._window_open:
            return self._window_open[market_key]
        px = self.get_price(asset)
        if px is not None:
            self._window_open[market_key] = px
            log.info(f"PriceFeed: anchored {market_key} open_spot={px:.4f}")
        return px

    def window_delta_pct(self, market_key: str, asset: str) -> Optional[float]:
        """
        (spot_now / spot_open - 1). Positive => asset up since window open.
        """
        open_px = self.anchor_window(market_key, asset)
        if open_px is None or open_px <= 0:
            return None
        now_px = self.get_price(asset)
        if now_px is None:
            return None
        return (now_px / open_px) - 1.0


@dataclass
class MarketState:
    """
    One active Up/Down market (dict shape from market_finder.parse_event)
    plus its live CLOB order books. Constructed fresh each cycle in
    bot/main.py: `MarketState(m, feed)` then `.refresh()`.
    """

    market: Dict[str, Any]
    feed: Optional[PriceFeed] = None
    up_book: OrderBook = field(default_factory=OrderBook.empty)
    down_book: OrderBook = field(default_factory=OrderBook.empty)

    def refresh(self) -> None:
        """Pull fresh order books for both outcome tokens. Call once per cycle."""
        up_id = self.market.get("up_token_id")
        down_id = self.market.get("down_token_id")
        self.up_book = fetch_order_book(up_id) if up_id else OrderBook.empty()
        self.down_book = fetch_order_book(down_id) if down_id else OrderBook.empty()

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

    @property
    def external_price(self) -> Optional[float]:
        """Latest external spot price for this market's asset, if a feed is attached."""
        if self.feed is None:
            return None
        return self.feed.get_price(self.market.get("asset", "BTC"))

    @property
    def market_key(self) -> str:
        return str(self.market.get("slug") or self.market.get("condition_id") or "unknown")

    @property
    def window_delta_pct(self) -> Optional[float]:
        """Spot move since window open (fraction). None if no feed/anchor."""
        if self.feed is None:
            return None
        asset = self.market.get("asset", "BTC")
        return self.feed.window_delta_pct(self.market_key, asset)

    @property
    def fair_up_prob(self) -> Optional[float]:
        """
        Heuristic P(UP) from window open-price delta.
        Maps small moves into (0.05, 0.95); None if no spot signal.
        """
        d = self.window_delta_pct
        if d is None:
            return None
        # ~50 bps move -> strong directional lean; clamp
        # fair = 0.5 + k * delta, k chosen so +1% spot ~= +0.35 prob
        fair = 0.5 + (d * 35.0)
        return max(0.05, min(0.95, fair))
