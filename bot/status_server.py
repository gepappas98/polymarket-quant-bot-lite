"""
Lightweight HTTP status server exposing the bot's live state as JSON,
matching the BotStatus shape the dashboard expects
(src/lib/bot-types.ts in the polymarket-quant-bot-lite frontend repo).

Enable by setting STATUS_PORT (e.g. STATUS_PORT=8080) — main.py starts this
automatically in a background thread when the env var is present.

Point the dashboard at it by setting, on the dashboard's host (Vercel/Lovable):
  BOT_STATUS_URL=https://<your-worker-host>/status

Note: pnlSeries / trackRecord stay at zero until outcome resolution is wired
up (recording a window's win/loss via ledger.record_outcome) — that isn't
implemented yet in this lite version; see ROADMAP.md.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

from .config import cfg
from .gates import cooldown, is_live_trading_allowed
from .ledger import ledger

log = logging.getLogger(__name__)

_start_time = time.time()
_lock = threading.Lock()
_state: Dict[str, Any] = {
    "markets": [],  # list of MarketRow-shaped dicts, set each cycle by update_markets()
}


def update_markets(rows: List[Dict[str, Any]]) -> None:
    """Called from the main loop each cycle with current market snapshots."""
    with _lock:
        _state["markets"] = rows


def _config_dict() -> Dict[str, Any]:
    return {
        "mode": cfg.mode,
        "assets": cfg.assets,
        "windows": cfg.windows,
        "maxOrderUsd": cfg.max_order_usd,
        "maxMarketExposureUsd": cfg.max_market_exposure_usd,
        "arbThreshold": cfg.arb_threshold,
        "minDirectionalEdge": cfg.min_directional_edge,
        "dailyLossLimitUsd": cfg.daily_loss_limit_usd,
        "cooldownMinutes": cfg.cooldown_minutes,
        "minTrackRecordWinPct": cfg.min_track_record_win_pct,
        "minTrackRecordSamples": cfg.min_track_record_samples,
        "preferMaker": cfg.prefer_maker,
    }


def _gates_list() -> List[Dict[str, Any]]:
    live = is_live_trading_allowed()
    wr = ledger.win_rate(min_samples=cfg.min_track_record_samples)
    return [
        {
            "name": "Live trading double opt-in",
            "allowed": live.allowed,
            "reason": live.reason or "double opt-in OK",
        },
        {
            "name": "Daily loss kill-switch",
            "allowed": True,
            "reason": f"limit {cfg.daily_loss_limit_usd} USD",
        },
        {
            "name": "Order size limit",
            "allowed": True,
            "reason": f"max {cfg.max_order_usd} USD per order",
        },
        {
            "name": "Market exposure cap",
            "allowed": True,
            "reason": f"max {cfg.max_market_exposure_usd} USD per market",
        },
        {
            "name": "Track-record gate (directional)",
            "allowed": wr is None or wr["win_rate_pct"] >= cfg.min_track_record_win_pct,
            "reason": (
                f"win-rate {wr['win_rate_pct']}% (n={int(wr['sample_size'])})"
                if wr is not None
                else f"sample size below {cfg.min_track_record_samples} outcomes — fail closed"
            ),
        },
        {
            "name": "Per-market cooldown",
            "allowed": True,
            "reason": f"{cfg.cooldown_minutes} min lock after each admitted intent",
        },
    ]


def _ledger_rows(limit: int = 50) -> List[Dict[str, Any]]:
    rows = []
    for e in ledger._entries[-limit:]:
        rows.append({
            "ts": int(e.ts * 1000),
            "kind": e.kind,
            "marketSlug": e.market_slug,
            "side": e.side,
            "price": e.price,
            "sizeUsd": e.size_usd,
            "reason": e.reason,
            "status": e.status,
            "dryRun": e.dry_run,
            "pnlUsd": e.pnl_usd,
        })
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows


def build_status() -> Dict[str, Any]:
    with _lock:
        markets = list(_state["markets"])

    summary = ledger.session_summary()
    wr = ledger.win_rate(min_samples=cfg.min_track_record_samples)
    live = is_live_trading_allowed()

    outcomes_pnl = [
        e.pnl_usd for e in ledger._entries if e.kind == "outcome" and e.pnl_usd is not None
    ]
    cum = 0.0
    pnl_series = []
    for e in sorted(
        (e for e in ledger._entries if e.kind == "outcome"), key=lambda e: e.ts
    ):
        cum += e.pnl_usd or 0.0
        pnl_series.append({"ts": int(e.ts * 1000), "cumulativePnl": round(cum, 2)})

    return {
        "source": "worker",
        "generatedAt": int(time.time() * 1000),
        "uptimeSeconds": int(time.time() - _start_time),
        "liveTradingAllowed": live.allowed,
        "config": _config_dict(),
        "session": {
            "intents": summary["intents"],
            "blocked": summary["blocked"],
            "fills": summary["fills"],
            "totalUsd": round(summary["total_usd"], 2),
            "dryRunFills": summary["dry_run_fills"],
            "liveFills": summary["live_fills"],
        },
        "trackRecord": {
            "winRatePct": wr["win_rate_pct"] if wr else 0,
            "sampleSize": int(wr["sample_size"]) if wr else 0,
            "avgPnl": round(wr["avg_pnl"], 2) if wr else 0,
        },
        "pnlSeries": pnl_series,
        "markets": markets,
        "gates": _gates_list(),
        "ledger": _ledger_rows(),
    }


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/status", "/health", "/healthz"):
            try:
                body = json.dumps(build_status()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                log.exception(f"status_server error: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        return  # quiet — main.py already logs cycle activity


def start_status_server(port: Optional[int] = None) -> Optional[ThreadingHTTPServer]:
    """
    Starts the status HTTP server in a background daemon thread.
    Returns the server instance, or None if no port is configured (disabled by default).
    """
    port = port if port is not None else int(os.getenv("STATUS_PORT", "0") or 0)
    if not port:
        return None
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info(f"Status server listening on :{port} (GET /status)")
    return server
