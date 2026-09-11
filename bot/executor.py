"""
Execution layer: paper simulator + live skeleton.
Integrates Nexus-style gates (fail-closed) and trade ledger.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple
from dataclasses import dataclass

from .config import cfg
from .strategy import Intent, Strategy
from .gates import cooldown, gate_intent, is_live_trading_allowed
from .ledger import ledger, LedgerEntry
from .portfolio_gates import consecutive_loss_gate, max_drawdown_gate, pair_lock
from .daily_limit import check as daily_limit_check
from . import metrics
from .execution import Order as ExecutionOrder, OrderBook as ExecutionBook, PaperFillEngine

log = logging.getLogger(__name__)


def _execution_book(book: Any) -> ExecutionBook:
    """Normalize feed-shaped or execution-shaped books for paper fills."""
    def levels(name: str, fallback: str) -> List[dict]:
        raw = getattr(book, name, None)
        if raw is None:
            raw = getattr(book, fallback, [])
        normalized: List[dict] = []
        for level in raw or []:
            if isinstance(level, Mapping):
                price = level.get("price")
                shares = level.get("shares", level.get("size"))
            else:
                price = getattr(level, "price", None)
                shares = getattr(level, "shares", getattr(level, "size", None))
            try:
                normalized.append({"price": float(price), "shares": float(shares)})
            except (TypeError, ValueError):
                continue
        return normalized

    return ExecutionBook.from_levels(levels("bids", "_bids"), levels("asks", "_asks"))


def _pre_trade_gate(intent: Intent) -> Optional[Tuple[str, str]]:
    """Run the identical admission pipeline for paper, live, and shadow.

    The order is deliberately stable: persistent daily limit, consecutive-loss
    pause, session drawdown, per-market pair lock, then intent sizing/gates.
    Callers decide how to record the blocked result for their execution mode.
    """
    checks = (
        ("daily_kill", daily_limit_check),
        ("consecutive_losses", consecutive_loss_gate),
        ("drawdown", max_drawdown_gate),
        ("pair_lock", lambda: pair_lock.check(intent.market_slug)),
        ("gate", lambda: gate_intent(intent.market_slug, intent.size_usd, is_arb=intent.is_arb_leg)),
    )
    for stage, check in checks:
        result = check()
        if not result.allowed:
            return stage, result.reason or stage
    return None


def _record_blocked(intent: Intent, *, dry_run: bool, stage: str, reason: str) -> None:
    ledger.record_intent(intent, dry_run=dry_run, blocked=True, block_reason=reason)
    metrics.record_blocked(stage)


class OrderState(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"


@dataclass
class Fill:
    intent: Intent
    shares: float
    avg_price: float
    cost: float
    ts: float
    order_id: str
    simulated: bool


class PaperExecutor:
    """Executes paper intents only against the latest observed L2 book."""

    def __init__(self, strategy: Strategy):
        self.strategy = strategy
        self._books = {}
        self.fills: List[Fill] = []
        self.realized_pnl = 0.0
        self.daily_pnl = 0.0
        self.fill_engine = PaperFillEngine(cfg.paper_fee_bps, cfg.paper_slippage_bps)

    def observe(self, state, intents: List[Intent]) -> List[Fill]:
        self._books[state.market.get("slug", "")] = state
        return self.execute(intents)

    def execute(self, intents: List[Intent]) -> List[Fill]:
        results: List[Fill] = []

        for intent in intents:
            blocked = _pre_trade_gate(intent)
            if blocked:
                stage, reason = blocked
                log.warning(f"[GATE BLOCK:{stage}] {intent.market_slug}: {reason}")
                _record_blocked(intent, dry_run=True, stage=stage, reason=reason)
                continue

            ledger.record_intent(intent, dry_run=True)
            metrics.record_intent(side=intent.side.value)

            execution_order = ExecutionOrder(
                market=intent.market_slug,
                side=intent.side.value,
                action=getattr(intent, "action", "BUY").upper(),
                requested_usd=intent.size_usd,
                limit_price=intent.price,
            )
            observed = self._books.get(intent.market_slug)
            if observed is None:
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason="no observed L2 book")
                continue
            raw_book = observed.up_book if intent.side.value == "UP" else observed.down_book
            execution_book = _execution_book(raw_book)
            report = self.fill_engine.execute(execution_order, execution_book)
            if not report.fills:
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason="no paper liquidity")
                continue
            shares = sum(item.shares for item in report.fills)
            cost = report.filled_usd
            fill = Fill(
                intent=intent,
                shares=shares,
                avg_price=report.vwap or intent.price,
                cost=cost,
                ts=time.time(),
                order_id=f"paper-{execution_order.order_id[:10]}",
                simulated=True,
            )
            results.append(fill)
            self.fills.append(fill)
            self.strategy.update_inventory(
                    intent.market_slug,
                    intent.side,
                    shares,
                    cost,
                    is_arb_leg=intent.is_arb_leg,
                    set_id=intent.set_id,
                )
            ledger.record_fill(intent, shares, cost, fill.order_id, dry_run=True)
            metrics.record_fill(side=intent.side.value, size_usd=cost, dry_run=True)
            cooldown.commit_cooldown(
                intent.market_slug,
                minutes=1.0 if intent.is_arb_leg else cooldown.minutes,
            )
            log.info(
                f"[PAPER FILL] {intent.side.value} {shares:.2f} shares @ {intent.price:.3f} "
                f"(${cost:.2f}) | {intent.reason}"
            )
        _record_pair_states(intents, results, dry_run=True)
        return results

    def check_kill_switch(self) -> bool:
        """
        NOTE: this used to check self.daily_pnl, which was initialized to 0.0
        and never updated anywhere — the switch could never fire. It now
        delegates to portfolio_gates.max_drawdown_gate(), which reads real
        settled PnL from the ledger (populated by bot/resolver.py), PLUS
        bot.daily_limit.check(), which persists across restarts within the
        same UTC day (max_drawdown_gate alone resets on every process restart).
        """
        daily = daily_limit_check()
        if not daily.allowed:
            log.error(f"KILL SWITCH (daily, persisted): {daily.reason}")
            ledger.append(LedgerEntry(
                ts=time.time(),
                kind="kill",
                market_slug="*",
                reason=daily.reason,
                dry_run=True,
                status="killed",
            ))
            metrics.set_kill_switch_active(True)
            return True

        loss_pause = consecutive_loss_gate()
        if not loss_pause.allowed:
            log.error(f"PAUSE: {loss_pause.reason}")
            metrics.set_kill_switch_active(False)
            return True

        drawdown = max_drawdown_gate()
        if not drawdown.allowed:
            log.error(f"KILL SWITCH: {drawdown.reason}")
            ledger.append(LedgerEntry(
                ts=time.time(),
                kind="kill",
                market_slug="*",
                reason=drawdown.reason,
                dry_run=True,
                status="killed",
            ))
            metrics.set_kill_switch_active(True)
            return True
        metrics.set_kill_switch_active(False)
        return False


def _record_pair_states(intents: List[Intent], fills: List[Fill], *, dry_run: bool) -> None:
    """Record pair lifecycle without pretending a submitted leg filled."""
    grouped = defaultdict(list)
    for intent in intents:
        if intent.is_arb_leg and intent.set_id:
            grouped[intent.set_id].append(intent)
    for set_id, pair_intents in grouped.items():
        filled = sum(1 for intent in pair_intents if any(fill.intent is intent for fill in fills))
        state = "PAIR_COMPLETE" if filled == len(pair_intents) else ("PAIR_PARTIAL" if filled else "PAIR_FAILED")
        ledger.append(LedgerEntry(
            ts=time.time(), kind="pair", market_slug=pair_intents[0].market_slug,
            reason=state, status=state.lower(), dry_run=dry_run,
            meta={"set_id": set_id, "legs": len(pair_intents), "confirmed_fills": filled},
        ))


class ShadowExecutor:
    """Observe live CLOB data and strategy decisions without submitting orders."""

    def __init__(self, strategy: Strategy):
        self.strategy = strategy
        self.would_be_fills: List[Fill] = []
        self.observations = 0
        self.last_cycle_summary = {
            "arb_intents": 0,
            "gated": 0,
            "would_fill": 0,
            "skipped_no_depth": 0,
        }

    def begin_cycle(self, *, arb_intents: int = 0) -> None:
        self.last_cycle_summary = {
            "arb_intents": int(arb_intents),
            "gated": 0,
            "would_fill": 0,
            "skipped_no_depth": 0,
        }

    @staticmethod
    def _estimate(intent: Intent, state) -> Optional[Fill]:
        book = state.up_book if intent.side.value == "UP" else state.down_book
        levels = getattr(book, "_asks", [])
        remaining = intent.size_usd
        shares = 0.0
        cost = 0.0
        for level in sorted(levels, key=lambda item: float(item.get("price", 9))):
            price = float(level.get("price", 0))
            available = float(level.get("size", 0))
            if price <= 0 or available <= 0 or remaining <= 0:
                continue
            clip = min(remaining, price * available)
            shares += clip / price
            cost += clip
            remaining -= clip
        if shares <= 0:
            return None
        return Fill(intent, shares, cost / shares, cost, time.time(), f"shadow-{uuid.uuid4().hex[:10]}", True)

    def observe(self, state, intents: List[Intent]) -> List[Fill]:
        self.observations += 1
        cycle = self.last_cycle_summary
        for intent in intents:
            blocked = _pre_trade_gate(intent)
            if blocked:
                cycle["gated"] += 1
                stage, reason = blocked
                _record_blocked(intent, dry_run=True, stage=stage, reason=reason)
                ledger.append(LedgerEntry(
                    ts=time.time(), kind="shadow_block", market_slug=intent.market_slug,
                    side=intent.side.value, reason=reason, status="blocked", dry_run=True,
                    meta={"shadow": True, "blocked_by": stage},
                ))
                continue
            ledger.record_intent(intent, dry_run=True)
            estimate = self._estimate(intent, state)
            if estimate:
                cycle["would_fill"] += 1
                self.would_be_fills.append(estimate)
                ledger.append(LedgerEntry(
                    ts=time.time(), kind="fill", market_slug=intent.market_slug,
                    side=intent.side.value, price=estimate.avg_price,
                    size_usd=estimate.cost, reason="SHADOW_WOULD_FILL",
                    status="shadow", dry_run=True, order_id=estimate.order_id,
                    meta={"shadow": True, "shares": estimate.shares,
                          "signal_reason": intent.reason},
                ))
            else:
                cycle["skipped_no_depth"] += 1
        ledger.append(LedgerEntry(
            ts=time.time(), kind="shadow_observation", market_slug=state.market.get("slug", "?"),
            status="observed", dry_run=True,
            meta={"up_ask": state.up_ask, "down_ask": state.down_ask,
                  "sum_asks": state.sum_asks, "arb_available": state.arb_available,
                          "external_price": state.external_price, "intent_count": len(intents)},
        ))
        return [fill for fill in self.would_be_fills if fill.intent in intents]

    def execute(self, intents: List[Intent]) -> List[Fill]:
        raise RuntimeError("ShadowExecutor requires observe(state, intents); it never submits orders")

    def check_kill_switch(self) -> bool:
        return False


class LiveExecutor:
    """
    Live execution with the same gates + ledger as paper.
    Requires double opt-in (MODE=live + LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISK).
    """

    def __init__(self, strategy: Strategy):
        self.strategy = strategy
        self.client = None
        live = is_live_trading_allowed()
        if not live.allowed:
            raise RuntimeError(f"Live trading not allowed: {live.reason}")
        self._init_client()

    def _init_client(self):
        try:
            from py_clob_client_v2 import ClobClient
            temp = ClobClient(
                host=cfg.clob_host,
                chain_id=cfg.chain_id,
                key=cfg.private_key,
            )
            creds = temp.create_or_derive_api_key()
            self.client = ClobClient(
                host=cfg.clob_host,
                chain_id=cfg.chain_id,
                key=cfg.private_key,
                creds=creds,
            )
            log.info("Live CLOB client initialized (double opt-in passed)")
        except Exception as e:
            log.error(f"Failed to init live client: {e}")
            raise

    @staticmethod
    def _verified_average(order: Dict[str, Any]) -> float:
        direct = order.get("avg_price") or order.get("average_price")
        if direct is not None:
            try:
                value = float(direct)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
        fills = order.get("fills") or order.get("matches") or []
        weighted = 0.0
        quantity = 0.0
        for item in fills:
            try:
                price = float(item.get("price"))
                size = float(item.get("size") or item.get("quantity") or item.get("matched_size"))
            except (TypeError, ValueError):
                continue
            if price > 0 and size > 0:
                weighted += price * size
                quantity += size
        return weighted / quantity if quantity else 0.0

    def _reconcile_order(self, order_id: str) -> Tuple[str, float, float]:
        """Poll, cancel any remainder, then confirm the final cumulative fill."""
        deadline = time.monotonic() + max(cfg.live_order_timeout_sec, 0.0)
        last: Dict[str, Any] = {}
        cancel_requested = False
        while True:
            try:
                last = self.client.get_order(order_id) or {}
            except Exception as exc:
                log.warning("Order reconciliation failed for %s: %s", order_id, exc)
            status = str(last.get("status") or last.get("state") or "").upper()
            filled = float(last.get("size_matched") or last.get("filled_size") or last.get("filled") or 0.0)
            average = self._verified_average(last)
            terminal = {"FILLED", "MATCHED", "CANCELLED", "CANCELED", "REJECTED", "EXPIRED"}
            if status in terminal:
                return status, filled, average
            if time.monotonic() >= deadline and not cancel_requested:
                try:
                    self.client.cancel(order_id)
                    cancel_requested = True
                    deadline = time.monotonic() + max(cfg.live_order_timeout_sec, 0.0)
                except Exception as exc:
                    log.warning("Failed to cancel timed-out order %s: %s", order_id, exc)
                    return "CANCEL_UNCONFIRMED", filled, average
            elif time.monotonic() >= deadline:
                log.error("Cancel not confirmed for order %s", order_id)
                return "CANCEL_UNCONFIRMED", filled, average
            time.sleep(max(cfg.live_order_poll_sec, 0.0))

    def execute(self, intents: List[Intent]) -> List[Fill]:
        results: List[Fill] = []

        for intent in intents:
            blocked = _pre_trade_gate(intent)
            if blocked:
                stage, reason = blocked
                log.warning(f"[GATE BLOCK LIVE:{stage}] {intent.market_slug}: {reason}")
                _record_blocked(intent, dry_run=False, stage=stage, reason=reason)
                continue

            ledger.record_intent(intent, dry_run=False)
            metrics.record_intent(side=intent.side.value)

            try:
                from py_clob_client_v2 import OrderArgs, OrderType, Side as ClobSide, PartialCreateOrderOptions

                side = ClobSide.BUY if intent.action == "BUY" else ClobSide.SELL
                size = intent.size_usd / intent.price
                order_args = OrderArgs(
                    token_id=intent.token_id,
                    price=intent.price,
                    size=round(size, 2),
                    side=side,
                )
                options = PartialCreateOrderOptions(tick_size="0.01")
                resp = self.client.create_and_post_order(
                    order_args=order_args,
                    options=options,
                    order_type=OrderType.GTC,
                )
                order_id = str(resp.get("orderID") or resp.get("id") or uuid.uuid4())
                status, shares, avg_price = self._reconcile_order(order_id)
                if status not in {"FILLED", "MATCHED", "CANCELLED", "CANCELED", "EXPIRED"} or shares <= 0:
                    log.warning("[LIVE ORDER] %s ended without a confirmed fill: %s", order_id, status)
                    ledger.append(LedgerEntry(
                        ts=time.time(), kind="order", market_slug=intent.market_slug,
                        side=intent.side.value, price=intent.price,
                        size_usd=intent.size_usd, reason=intent.reason,
                        status=status.lower(), dry_run=False, order_id=order_id,
                    ))
                    continue
                if avg_price <= 0:
                    log.error("[LIVE ORDER] %s has fills without a verified execution price", order_id)
                    ledger.append(LedgerEntry(
                        ts=time.time(), kind="order", market_slug=intent.market_slug,
                        side=intent.side.value, price=intent.price,
                        size_usd=intent.size_usd, reason=intent.reason,
                        status="unpriced_fill", dry_run=False, order_id=order_id,
                    ))
                    continue
                cost = shares * avg_price
                fill = Fill(
                    intent=intent,
                    shares=shares,
                    avg_price=avg_price,
                    cost=cost,
                    ts=time.time(),
                    order_id=order_id,
                    simulated=False,
                )
                results.append(fill)
                self.strategy.update_inventory(
                    intent.market_slug,
                    intent.side,
                    shares,
                    cost,
                    is_arb_leg=intent.is_arb_leg,
                    set_id=intent.set_id,
                )
                ledger.record_fill(intent, shares, cost, order_id, dry_run=False)
                metrics.record_fill(side=intent.side.value, size_usd=cost, dry_run=False)
                cooldown.commit_cooldown(
                    intent.market_slug,
                    minutes=1.0 if intent.is_arb_leg else cooldown.minutes,
                )
                log.info(f"[LIVE FILL] {order_id} {intent.side.value} {shares:.2f} @ {avg_price:.3f}")
            except Exception as e:
                log.error(f"Live order failed: {e}")
                ledger.record_intent(
                    intent, dry_run=False, blocked=True, block_reason=f"exec error: {e}"
                )
        _record_pair_states(intents, results, dry_run=False)
        return results


def create_executor(strategy: Strategy):
    if cfg.mode == "shadow":
        log.info("Shadow live mode: observing CLOB only; order submission disabled")
        return ShadowExecutor(strategy)
    live = is_live_trading_allowed()
    if live.allowed:
        log.warning("=== LIVE MODE ENABLED – REAL MONEY (double opt-in passed) ===")
        return LiveExecutor(strategy)
    reason = live.reason if cfg.mode == "live" else "MODE=paper"
    log.info("Paper trading mode (safe) ��� %s", reason)
    return PaperExecutor(strategy)
