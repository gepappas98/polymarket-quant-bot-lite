"""
Ελαφρύ Kalshi REST client — μόνο ό,τι χρειάζεται το cross-platform arbitrage
module (bot/strategies/cross_platform_arbitrage.py): market lookup + orderbook.

Kalshi's /markets/{ticker}/orderbook endpoint ΔΕΝ είναι πλήρως public — απαιτεί
RSA-PSS signed request headers ακόμα και για read-only πρόσβαση (επιβεβαιωμένο
από τα επίσημα docs: https://docs.kalshi.com/api-reference/market/get-market-orderbook,
401 response χωρίς KALSHI-ACCESS-KEY/SIGNATURE/TIMESTAMP). Αυτό σημαίνει:
- Χρειάζεσαι Kalshi API key (RSA key pair) ακόμα κι αν απλά ΔΙΑΒΑΖΕΙΣ books.
- Το signing χρησιμοποιεί RSA-PSS + SHA256 πάνω σε timestamp+method+path.

Requires: `cryptography` package (lazy import — δεν σπάει τίποτα αν λείπει
και KALSHI_ARB_ENABLED δεν είναι "true").

ΔΕΝ δοκιμάστηκε κόντρα σε πραγματικό Kalshi account (θα χρειαζόταν πραγματικό
API key pair, εκτός scope αυτού του sandbox) — το request-signing τεστάρεται
μονάχα του (η μαθηματική σωστότητα της υπογραφής), όχι το πραγματικό HTTP
round-trip. Δοκίμασέ το με το δικό σου demo account
(https://demo-api.kalshi.co/trade-api/v2) πριν το εμπιστευτείς.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import requests

log = logging.getLogger(__name__)

KALSHI_HOST = os.getenv("KALSHI_API_HOST", "https://api.elections.kalshi.com/trade-api/v2")


def _sign(private_key, timestamp_ms: str, method: str, path: str) -> str:
    """RSA-PSS + SHA256 πάνω σε f'{timestamp_ms}{method}{path}' (path ΧΩΡΙΣ query string,
    ίδιο με τα επίσημα docs)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    message = f"{timestamp_ms}{method}{path}".encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


@dataclass
class KalshiBookLevel:
    price: float   # dollars, 0-1
    size: float


@dataclass
class KalshiOrderBook:
    yes_bids: List[KalshiBookLevel]
    no_bids: List[KalshiBookLevel]

    @property
    def yes_best_bid(self) -> Optional[float]:
        return max((l.price for l in self.yes_bids), default=None)

    @property
    def no_best_bid(self) -> Optional[float]:
        return max((l.price for l in self.no_bids), default=None)

    @property
    def yes_ask(self) -> Optional[float]:
        """Το ask για YES = 1 - best NO bid (standard complementary-market identity,
        ίδιο μοτίβο με το UP/DOWN sum_asks στο bot/feeds.py)."""
        no_bid = self.no_best_bid
        return round(1.0 - no_bid, 4) if no_bid is not None else None

    @property
    def no_ask(self) -> Optional[float]:
        yes_bid = self.yes_best_bid
        return round(1.0 - yes_bid, 4) if yes_bid is not None else None


class KalshiClient:
    def __init__(
        self,
        api_key_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        host: str = KALSHI_HOST,
        timeout: float = 6.0,
    ):
        self.host = host
        self.timeout = timeout
        self.api_key_id = api_key_id or os.getenv("KALSHI_API_KEY_ID", "")
        key_path = private_key_path or os.getenv("KALSHI_PRIVATE_KEY_PATH", "")
        self._private_key = None
        if key_path:
            self._private_key = self._load_private_key(key_path)

    @staticmethod
    def _load_private_key(path: str):
        from cryptography.hazmat.primitives import serialization
        data = Path(path).read_bytes()
        return serialization.load_pem_private_key(data, password=None)

    def _headers(self, method: str, path: str) -> dict:
        if not self._private_key or not self.api_key_id:
            raise RuntimeError(
                "KalshiClient: missing KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY_PATH — "
                "read access to Kalshi's orderbook endpoint requires a signed request "
                "even for market data, see module docstring."
            )
        ts_ms = str(int(time.time() * 1000))
        sig = _sign(self._private_key, ts_ms, method, path)
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        }

    def get_orderbook(self, ticker: str) -> Optional[KalshiOrderBook]:
        # Path σε σωστή μορφή για signing (χωρίς query string) — πρέπει να ταιριάζει
        # ΑΚΡΙΒΩΣ με ό,τι λέει η τεκμηρίωση: /trade-api/v2/markets/{ticker}/orderbook
        sign_path = f"/trade-api/v2/markets/{ticker}/orderbook"
        try:
            headers = self._headers("GET", sign_path)
        except RuntimeError as e:
            log.error(str(e))
            return None
        try:
            resp = requests.get(f"{self.host}/markets/{ticker}/orderbook", headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json().get("orderbook_fp") or resp.json().get("orderbook") or {}
            yes = [KalshiBookLevel(price=float(p), size=float(s)) for p, s in data.get("yes_dollars", data.get("yes", []))]
            no = [KalshiBookLevel(price=float(p), size=float(s)) for p, s in data.get("no_dollars", data.get("no", []))]
            return KalshiOrderBook(yes_bids=yes, no_bids=no)
        except Exception as e:
            log.debug(f"KalshiClient.get_orderbook({ticker}) failed: {e}")
            return None
