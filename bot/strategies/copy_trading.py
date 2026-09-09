"""
Copy-trading strategy — real Polymarket Data API activity only.

Παρακολουθεί συγκεκριμένα "target" wallets (π.χ. από το Polymarket
leaderboard) μέσω του public Data API, και αναπαράγει τα trades τους σε
markets που ήδη παρακολουθεί ο bot (state.market["up_token_id"/"down_token_id"]),
με μέγεθος = size_multiplier * (μέγεθος target trade), capped στα υπάρχοντα
risk limits.

ΠΡΟΣΟΧΗ ΠΡΙΝ ΤΟ ΒΑΛΕΙΣ ΣΕ LIVE:
- Το ακριβές URL/schema του Data API (data-api.polymarket.com) αλλάζει κατά
  καιρούς· επιβεβαίωσε το endpoint/παραμέτρους στα τρέχοντα docs πριν
  εμπιστευτείς την έξοδο parse_activity() 1:1. Το parsing εδώ είναι
  best-effort πάνω στο σχήμα που είναι δημόσια γνωστό (activity feed με
  proxyWallet, side, size, price, asset/conditionId) — γράψε ένα μικρό
  unit test με πραγματικό response πριν το live.
- Eligibility uses separately paginated real history; the last-20 activity
  page is only a new-trade detector. History failure produces zero intents
  and an explicit ``skip_reason``.
- Πάντα μέσω του ΙΔΙΟΥ gate pipeline (gate_intent, max_drawdown_gate,
  pair_lock) — αυτό το module ΔΕΝ παρακάμπτει κανένα risk gate, απλά παράγει
  Intents όπως και οι υπόλοιπες στρατηγικές.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import requests

from ..config import cfg
from ..strategy import Intent, Side

log = logging.getLogger(__name__)

DATA_API_HOST = os.getenv("POLYMARKET_DATA_API_HOST", "https://data-api.polymarket.com")


@dataclass
class CopyTradingConfig:
    enabled: bool = os.getenv("COPY_TRADING_ENABLED", "false").lower() == "true"
    # Comma-separated λίστα wallet addresses να αντιγράφονται
    target_wallets: List[str] = field(
        default_factory=lambda: [
            w.strip().lower() for w in os.getenv("COPY_TRADING_WALLETS", "").split(",") if w.strip()
        ]
    )
    size_multiplier: float = float(os.getenv("COPY_TRADING_SIZE_MULTIPLIER", "0.1"))
    min_target_trade_usd: float = float(os.getenv("COPY_TRADING_MIN_TRADE_USD", "10"))
    min_target_trades: int = int(os.getenv("COPY_TRADING_MIN_TRADES", "100"))
    min_history_days: int = int(os.getenv("COPY_TRADING_MIN_HISTORY_DAYS", "30"))
    max_price_move_after_target: float = float(os.getenv("COPY_TRADING_MAX_PRICE_MOVE_AFTER_TARGET", "0.02"))
    poll_interval_sec: float = float(os.getenv("COPY_TRADING_POLL_INTERVAL_SEC", "15"))
    max_trade_age_sec: float = float(os.getenv("COPY_TRADING_MAX_TRADE_AGE_SEC", "120"))
    http_timeout: float = 6.0


class CopyTradingStrategy:
    name = "copy_trading"

    def __init__(self, config: Optional[CopyTradingConfig] = None):
        self.cfg = config or CopyTradingConfig()
        self._last_poll_ts: float = 0.0
        self._seen_trade_ids: Set[str] = set()
        # token_id -> [ {trade dict} ] φρέσκα (μη-αναπαραγμένα) trades ανά wallet
        self._pending_by_token: Dict[str, List[dict]] = {}
        self.skip_reason: Optional[str] = None

    def _fetch_wallet_activity(self, wallet: str) -> List[dict]:
        """Fetch only the newest page used for detecting new trades."""
        try:
            resp = requests.get(
                f"{DATA_API_HOST}/activity",
                params={"user": wallet, "limit": 20},
                timeout=self.cfg.http_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("data", [])
        except Exception as e:
            log.debug(f"[COPY] activity fetch failed for {wallet}: {e}")
            return []

    def _fetch_wallet_history(self, wallet: str) -> Optional[List[dict]]:
        """Fetch paginated real history used only for eligibility.

        A missing or malformed history response is a hard failure. The
        strategy never infers a track record from the last-20 polling page.
        """
        history: List[dict] = []
        offset = 0
        page_size = max(self.cfg.min_target_trades, 100)
        try:
            while len(history) < self.cfg.min_target_trades or offset == 0:
                resp = requests.get(
                    f"{DATA_API_HOST}/trades",
                    params={"user": wallet, "limit": page_size, "offset": offset},
                    timeout=self.cfg.http_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                page = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else None
                if not isinstance(page, list):
                    raise ValueError("history response is not a list")
                history.extend(item for item in page if isinstance(item, dict))
                if len(page) < page_size:
                    break
                offset += len(page)
                if offset > 100_000:
                    raise ValueError("history pagination exceeded safety bound")
            return history
        except Exception as e:
            log.warning("[COPY] history unavailable for %s; fail closed: %s", wallet, e)
            return None

    def _history_eligible(self, history: List[dict], now: float) -> bool:
        if len(history) < self.cfg.min_target_trades:
            self.skip_reason = f"insufficient_history_trades:{len(history)}<{self.cfg.min_target_trades}"
            return False
        timestamps = [float(item.get("timestamp") or 0) for item in history]
        if not timestamps or now - min(timestamps) < self.cfg.min_history_days * 86400:
            self.skip_reason = f"insufficient_history_days:<{self.cfg.min_history_days}"
            return False
        return True

    def _refresh(self) -> None:
        now = time.time()
        if now - self._last_poll_ts < self.cfg.poll_interval_sec:
            return
        self._last_poll_ts = now
        self._pending_by_token.clear()
        self.skip_reason = None

        for wallet in self.cfg.target_wallets:
            history = self._fetch_wallet_history(wallet)
            if history is None:
                self.skip_reason = f"history_fetch_failed:{wallet}"
                continue
            if not self._history_eligible(history, now):
                continue
            activity = self._fetch_wallet_activity(wallet)
            for trade in activity:
                trade_id = str(trade.get("id") or trade.get("transactionHash") or "")
                if not trade_id or trade_id in self._seen_trade_ids:
                    continue
                ts = float(trade.get("timestamp") or 0)
                if ts and (now - ts) > self.cfg.max_trade_age_sec:
                    continue
                usd_size = float(trade.get("usdcSize") or trade.get("size") or 0)
                if usd_size < self.cfg.min_target_trade_usd:
                    continue
                target_price = float(trade.get("price") or 0)
                current_raw = trade.get("currentPrice") or trade.get("current_price")
                if current_raw is None:
                    continue
                current_price = float(current_raw)
                if abs(current_price - target_price) > self.cfg.max_price_move_after_target:
                    continue
                if str(trade.get("side", "")).upper() != "BUY":
                    continue  # αναπαράγουμε μόνο buys — τα sells/exits τα κρίνει ο δικός μας risk layer
                token_id = str(trade.get("asset") or trade.get("tokenId") or "")
                if not token_id:
                    continue
                self._seen_trade_ids.add(trade_id)
                self._pending_by_token.setdefault(token_id, []).append(trade)

        # Bound μνήμης — κράτα μόνο τα τελευταία N ids
        if len(self._seen_trade_ids) > 5000:
            self._seen_trade_ids = set(list(self._seen_trade_ids)[-2000:])

    def evaluate(self, state) -> List[Intent]:
        if not self.cfg.enabled or not self.cfg.target_wallets:
            return []

        self._refresh()
        if not self._pending_by_token:
            if self.skip_reason is None:
                self.skip_reason = "no_new_eligible_trades"
            return []

        slug = state.market["slug"]
        asset = state.market.get("asset", "BTC")
        up_id = state.market.get("up_token_id")
        down_id = state.market.get("down_token_id")
        exposure_cap = cfg.exposure_cap_for(asset)

        intents: List[Intent] = []
        for token_id, side, ask in (
            (up_id, Side.UP, state.up_ask),
            (down_id, Side.DOWN, state.down_ask),
        ):
            trades = self._pending_by_token.pop(token_id, [])
            if not trades or ask is None:
                continue
            target_usd = sum(float(t.get("usdcSize") or t.get("size") or 0) for t in trades)
            size = min(target_usd * self.cfg.size_multiplier, cfg.max_order_usd, exposure_cap)
            if size < 5:
                continue
            intents.append(Intent(
                market_slug=slug,
                token_id=token_id,
                side=side,
                action="BUY",
                price=ask,
                size_usd=round(size, 2),
                reason=f"copy-trade {len(trades)} target buy(s), ${target_usd:.0f} total",
            ))
            log.info(f"[COPY] {slug} {side.value} replicate ${size:.1f} from {len(trades)} target trade(s)")

        return intents


# --- Dynamic-loader convention (bot/strategies/loader.py) ---
STRATEGY_ENABLED_ENV = "COPY_TRADING_ENABLED"


def build(shared_strategy):
    return CopyTradingStrategy()
