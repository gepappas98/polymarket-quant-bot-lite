"""
Execution layer: paper simulator + live skeleton.
Integrates Nexus-style gates (fail-closed) and trade ledger.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import List
from dataclasses import dataclass

from .config import cfg
from .strategy import Intent, Strategy
from .gates import gate_intent, is_live_trading_allowed
from .ledger import ledger, LedgerEntry
from .portfolio_gates import max_drawdown_gate, pair_lock
from .daily_limit import check as daily_limit_check

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
            return results

        drawdown = max_drawdown_gate()
        if not drawdown.allowed:
            for intent in intents:
                log.warning(f"[DRAWDOWN BLOCK] {intent.market_slug}: {drawdown.reason}")
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason=drawdown.reason or "")
            return results

        for intent in intents:
            pair = pair_lock.check(intent.market_slug)
            if not pair.allowed:
                log.warning(f"[PAIR LOCK] {intent.market_slug}: {pair.reason}")
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason=pair.reason or "")
                continue

            gate = gate_intent(intent.market_slug, intent.size_usd, is_arb=intent.is_arb_leg)
            if not gate.allowed:
                log.warning(f"[GATE BLOCK] {intent.market_slug} {intent.side.value}: {gate.reason}")
                ledger.record_intent(intent, dry_run=True, blocked=True, block_reason=gate.reason or "")
                continue

            ledger.record_intent(intent, dry_run=True)

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
            self.strategy.update_inventory(intent.market_slug, intent.side, shares, cost)
            ledger.record_fill(intent, shares, cost, fill.order_id, dry_run=True)
            log.info(
                f"[PAPER FILL] {intent.side.value} {shares:.2f} shares @ {intent.price:.3f} "
                f"(${cost:.2f}) | {intent.reason}"
            )
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
            return True
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

    def execute(self, intents: List[Intent]) -> List[Fill]:
        from py_clob_client_v2 import OrderArgs, OrderType, Side as ClobSide, PartialCreateOrderOptions

        results: List[Fill] = []

        daily = daily_limit_check()
        if not daily.allowed:
            for intent in intents:
                log.warning(f"[DAILY KILL LIVE] {intent.market_slug}: {daily.reason}")
                ledger.record_intent(intent, dry_run=False, blocked=True, block_reason=daily.reason or "")
            return results

        drawdown = max_drawdown_gate()
        if not drawdown.allowed:
            for intent in intents:
                log.warning(f"[DRAWDOWN BLOCK LIVE] {intent.market_slug}: {drawdown.reason}")
                ledger.record_intent(intent, dry_run=False, blocked=True, block_reason=drawdown.reason or "")
            return results

        for intent in intents:
            pair = pair_lock.check(intent.market_slug)
            if not pair.allowed:
                log.warning(f"[PAIR LOCK LIVE] {intent.market_slug}: {pair.reason}")
                ledger.record_intent(intent, dry_run=False, blocked=True, block_reason=pair.reason or "")
                continue

            gate = gate_intent(intent.market_slug, intent.size_usd, is_arb=intent.is_arb_leg)
            if not gate.allowed:
                log.warning(f"[GATE BLOCK LIVE] {intent.market_slug}: {gate.reason}")
                ledger.record_intent(intent, dry_run=False, blocked=True, block_reason=gate.reason or "")
                continue

            ledger.record_intent(intent, dry_run=False)

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
                shares = size
                cost = intent.size_usd
                fill = Fill(
                    intent=intent,
                    shares=shares,
                    avg_price=intent.price,
                    cost=cost,
                    ts=time.time(),
                    order_id=order_id,
                    simulated=False,
                )
                results.append(fill)
                self.strategy.update_inventory(intent.market_slug, intent.side, shares, cost)
                ledger.record_fill(intent, shares, cost, order_id, dry_run=False)
                log.info(f"[LIVE ORDER] {order_id} {intent.side.value} @ {intent.price}")
            except Exception as e:
                log.error(f"Live order failed: {e}")
                ledger.record_intent(
                    intent, dry_run=False, blocked=True, block_reason=f"exec error: {e}"
                )
        return results


def create_executor(strategy: Strategy):
    live = is_live_trading_allowed()
    if live.allowed:
        log.warning("=== LIVE MODE ENABLED – REAL MONEY (double opt-in passed) ===")
        return LiveExecutor(strategy)
    reason = live.reason if cfg.mode == "live" else "MODE=paper"
    log.info("Paper trading mode (safe) — %s", reason)
    return PaperExecutor(strategy)