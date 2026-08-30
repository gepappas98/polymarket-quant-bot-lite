"""
Prometheus metrics (Priority 3) — thin layer πάνω από τα ίδια σημεία που ήδη
γράφουν στο bot/ledger.py, ώστε /metrics να είναι πάντα σύμφωνο με το ledger
χωρίς duplicate λογική υπολογισμού.

Χρήση: κάλεσε `start_metrics_server()` μία φορά στο bot/main.py (μετά το
configure_logging(), πριν το main loop), και κάλεσε τα `record_*` functions
στα ΙΔΙΑ σημεία που ήδη καλείς `ledger.record_*` (bot/executor.py,
bot/resolver.py) — βλ. INTEGRATION-priority3.md για τα ακριβή patch points.

Lazy import του prometheus_client — αν λείπει, όλες οι record_*/start_metrics_server
γίνονται no-op (δεν σπάει ποτέ το trading loop).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

_enabled = False
_intents_total = None
_blocked_total = None
_fills_total = None
_fill_usd_total = None
_outcomes_total = None
_pnl_total = None
_daily_pnl_gauge = None
_kill_switch_gauge = None

try:
    from prometheus_client import Counter, Gauge, start_http_server

    _intents_total = Counter("bot_intents_total", "Total trade intents produced", ["side"])
    _blocked_total = Counter("bot_intents_blocked_total", "Intents blocked by a risk gate", ["reason_kind"])
    _fills_total = Counter("bot_fills_total", "Total fills", ["side", "dry_run"])
    _fill_usd_total = Counter("bot_fill_usd_total", "Total USD notional filled", ["dry_run"])
    _outcomes_total = Counter("bot_outcomes_total", "Total settled market outcomes", ["winner"])
    _pnl_total = Counter("bot_realized_pnl_usd_total", "Cumulative realized PnL in USD (monotonic counter of gains; see bot_daily_pnl_usd for net)")
    _daily_pnl_gauge = Gauge("bot_daily_pnl_usd", "Current UTC-day cumulative PnL (bot.daily_limit)")
    _kill_switch_gauge = Gauge("bot_kill_switch_active", "1 if any kill switch (drawdown or daily) is currently blocking trading")
    _available = True
except ImportError:
    log.warning("prometheus_client δεν είναι εγκατεστημένο — /metrics disabled (pip install prometheus-client)")
    _available = False


def start_metrics_server(port: Optional[int] = None) -> None:
    global _enabled
    if not _available:
        return
    port = port or int(os.getenv("PROMETHEUS_PORT", "9108"))
    try:
        start_http_server(port)
        _enabled = True
        log.info(f"[METRICS] Prometheus /metrics exposed on :{port}")
    except Exception as e:
        log.error(f"[METRICS] failed to start Prometheus HTTP server on :{port}: {e}")


def record_intent(side: str) -> None:
    if _enabled:
        _intents_total.labels(side=side).inc()


def record_blocked(reason_kind: str) -> None:
    """reason_kind: κοντό, low-cardinality label — π.χ. 'daily_kill', 'drawdown', 'cooldown', 'exposure'.
    ΠΟΤΕ μην περάσεις εδώ το πλήρες free-text reason string (θα εκραγεί η cardinality)."""
    if _enabled:
        _blocked_total.labels(reason_kind=reason_kind).inc()


def record_fill(side: str, size_usd: float, dry_run: bool) -> None:
    if _enabled:
        dr = "true" if dry_run else "false"
        _fills_total.labels(side=side, dry_run=dr).inc()
        _fill_usd_total.labels(dry_run=dr).inc(size_usd)


def record_outcome(winner: Optional[str], pnl_usd: float) -> None:
    if _enabled:
        _outcomes_total.labels(winner=winner or "none").inc()
        if pnl_usd > 0:
            _pnl_total.inc(pnl_usd)


def set_daily_pnl(pnl_usd: float) -> None:
    if _enabled:
        _daily_pnl_gauge.set(pnl_usd)


def set_kill_switch_active(active: bool) -> None:
    if _enabled:
        _kill_switch_gauge.set(1 if active else 0)
