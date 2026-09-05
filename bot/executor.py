"""
Execution layer: paper simulator + live skeleton.
Integrates Nexus-style gates (fail-closed) and trade ledger.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .config import cfg
from .strategy import Intent, Strategy
from .gates import gate_intent, is_live_trading_allowed
from .ledger import ledger, LedgerEntry
from .portfolio_gates import max_drawdown_gate, pair_lock
from .daily_limit import check as daily_limit_check
from . import metrics

log = logging.getLogger(__name__)


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
    """Simulates fills at the requested price (optimistic)."""

    def __init__(self, strategy: Strategy):
        self.strategy = strategy
        self.fills: List[Fill] = []
        self.realized_pnl = 0.0
        self.daily_pnl = 0.0

    def execute(self, intents: List[Intent]) -> List[Fill]:
        results: List[Fill] = []

        daily = daily_limit_check()
        if not daily.allowed:
            for intent in intents:
                log.warning(f"[DAILY KILL] {intent.market_slug}: {daily.reason}")
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason=daily.reason or "")
                metrics.record_blocked("daily_kill")
            return results

        drawdown = max_drawdown_gate()
        if not drawdown.allowed:
            for intent in intents:
                log.warning(f"[DRAWDOWN BLOCK] {intent.market_slug}: {drawdown.reason}")
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason=drawdown.reason or "")
                metrics.record_blocked("drawdown")
            return results

        for intent in intents:
            pair = pair_lock.check(intent.market_slug)
            if not pair.allowed:
                log.warning(f"[PAIR LOCK] {intent.market_slug}: {pair.reason}")
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason=pair.reason or "")
                metrics.record_blocked("pair_lock")
                continue

            gate = gate_intent(intent.market_slug, intent.size_usd, is_arb=intent.is_arb_leg)
            if not gate.allowed:
                log.warning(f"[GATE BLOCK] {intent.market_slug} {intent.side.value}: {gate.reason}")
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason=gate.reason or "")
                metrics.record_blocked("gate")
                continue

            ledger.record_intent(intent, dry_run=True)
            metrics.record_intent(side=intent.side.value)

            shares = intent.size_usd / intent.price
            cost = intent.size_usd
            fill = Fill(
                intent=intent,
                shares=shares,
                avg_price=intent.price,
                cost=cost,
                ts=time.time(),
                order_id=f"paper-{uuid.uuid4().hex[:10]}",
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
        from py_clob_client_v2 import OrderArgs, OrderType, Side as ClobSide, PartialCreateOrderOptions

        results: List[Fill] = []

        daily = daily_limit_check()
        if not daily.allowed:
            for intent in intents:
                log.warning(f"[DAILY KILL LIVE] {intent.market_slug}: {daily.reason}")
                ledger.record_intent(intent, dry_run=False, blocked=True, block_reason=daily.reason or "")
                metrics.record_blocked("daily_kill")
            return results

        drawdown = max_drawdown_gate()
        if not drawdown.allowed:
            for intent in intents:
                log.warning(f"[DRAWDOWN BLOCK LIVE] {intent.market_slug}: {drawdown.reason}")
                ledger.record_intent(intent, dry_run=False, blocked=True, block_reason=drawdown.reason or "")
                metrics.record_blocked("drawdown")
            return results

        for intent in intents:
            pair = pair_lock.check(intent.market_slug)
            if not pair.allowed:
                log.warning(f"[PAIR LOCK LIVE] {intent.market_slug}: {pair.reason}")
                ledger.record_intent(intent, dry_run=False, blocked=True, block_reason=pair.reason or "")
                metrics.record_blocked("pair_lock")
                continue

            gate = gate_intent(intent.market_slug, intent.size_usd, is_arb=intent.is_arb_leg)
            if not gate.allowed:
                log.warning(f"[GATE BLOCK LIVE] {intent.market_slug}: {gate.reason}")
                ledger.record_intent(intent, dry_run=False, blocked=True, block_reason=gate.reason or "")
                metrics.record_blocked("gate")
                continue

            ledger.record_intent(intent, dry_run=False)
            metrics.record_intent(side=intent.side.value)

            try:
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
                log.info(f"[LIVE FILL] {order_id} {intent.side.value} {shares:.2f} @ {avg_price:.3f}")
            except Exception as e:
                log.error(f"Live order failed: {e}")
                ledger.record_intent(
                    intent, dry_run=False, blocked=True, block_reason=f"exec error: {e}"
                )
        _record_pair_states(intents, results, dry_run=False)
        return results


def create_executor(strategy: Strategy):
    live = is_live_trading_allowed()
    if live.allowed:
        log.warning("=== LIVE MODE ENABLED – REAL MONEY (double opt-in passed) ===")
        return LiveExecutor(strategy)
    reason = live.reason if cfg.mode == "live" else "MODE=paper"
    log.info("Paper trading mode (safe) — %s", reason)
    return PaperExecutor(strategy)
