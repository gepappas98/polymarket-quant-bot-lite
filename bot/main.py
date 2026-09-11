#!/usr/bin/env python3
"""
Polymarket Quant Bot – starter implementation of the bosona-style
high-frequency short-window crypto Up/Down system.

Usage:
    python -m bot.main

Always start in paper mode (MODE=paper in .env).
"""

import logging
import time
import signal
import sys
import os
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

from .config import cfg
from .logging_setup import configure_logging
from .market_finder import find_all_active
from .feeds import PriceFeed, MarketState
from .clob_ws import ClobWebSocketFeed
from .strategy import Strategy
from .executor import create_executor
from .gates import cooldown, is_live_trading_allowed
from . import gates
from .ledger import ledger
from .resolver import Resolver
from .status_server import start_status_server, update_markets, update_cycle_summary
from .strategies.loader import load_all
from . import metrics

console = Console()
configure_logging(cfg.log_level, cfg.log_format)
log = logging.getLogger("main")

running = True


def handle_sig(sig, frame):
    global running
    console.print("\n[yellow]Shutting down gracefully...[/yellow]")
    running = False


signal.signal(signal.SIGINT, handle_sig)
signal.signal(signal.SIGTERM, handle_sig)


def build_status_table(states: list, strategy: Strategy, executor) -> Table:
    table = Table(title="Active Markets & Inventory", show_header=True, header_style="bold cyan")
    table.add_column("Slug", style="dim")
    table.add_column("UP Ask")
    table.add_column("DOWN Ask")
    table.add_column("Sum")
    table.add_column("Inv UP")
    table.add_column("Inv DOWN")
    table.add_column("Paired")
    table.add_column("Cost $")

    for st in states:
        inv = strategy.get_inv(st.market["slug"])
        sum_str = f"{st.sum_asks:.3f}" if st.sum_asks else "—"
        color = "green" if st.arb_available else "white"
        table.add_row(
            st.market.get("slug", "?")[-28:],
            f"{st.up_ask:.3f}" if st.up_ask else "—",
            f"{st.down_ask:.3f}" if st.down_ask else "—",
            f"[{color}]{sum_str}[/{color}]",
            f"{inv.up_shares:.1f}",
            f"{inv.down_shares:.1f}",
            f"{inv.paired:.1f}",
            f"{inv.total_cost:.1f}",
        )
    return table


def market_rows(states: list, strategy: Strategy) -> list:
    """Build MarketRow-shaped dicts (see src/lib/bot-types.ts) for the status server."""
    now = time.time()
    rows = []
    for st in states:
        m = st.market
        inv = strategy.get_inv(m["slug"])
        up_ask = st.up_ask
        down_ask = st.down_ask
        window_end = m.get("window_ts", now) + m.get("window_minutes", 0) * 60
        seconds_to_close = max(0, int(window_end - now))
        edge = (0.5 - up_ask) if up_ask is not None else 0.0
        if st.arb_available:
            signal = "arb"
        elif edge > cfg.min_directional_edge:
            signal = "up"
        elif edge < -cfg.min_directional_edge:
            signal = "down"
        else:
            signal = "flat"
        cooldown_until = cooldown.get_until(m["slug"])
        rows.append({
            "slug": m.get("slug", "?"),
            "asset": m.get("asset", "?"),
            "windowMinutes": m.get("window_minutes", 0),
            "secondsToClose": seconds_to_close,
            "upAsk": up_ask if up_ask is not None else 0.0,
            "downAsk": down_ask if down_ask is not None else 0.0,
            "upBid": st.up_book.best_bid or 0.0,
            "downBid": st.down_book.best_bid or 0.0,
            "exposureUsd": round(inv.total_cost, 2),
            "cooldownUntil": int(cooldown_until * 1000) if cooldown_until else None,
            "signal": signal,
            "edge": round(edge, 4),
        })
    return rows


def install_risk_engine():
    """Install the optional risk hook, failing closed when initialization fails."""
    if os.getenv("RISK_ENGINE_ENABLED", "false").lower() not in ("1", "true", "yes"):
        return
    try:
        from app.services.risk_service import install_bot_gate_hook
        install_bot_gate_hook()
        log.info("advanced risk engine gate hook installed")
    except Exception as exc:
        log.exception("risk engine failed to initialise")
        reason = f"risk engine failed to initialise: {exc}"
        gates.register_check(lambda _slug, _size: gates.GateResult(False, reason))


def main():
    live_gate = is_live_trading_allowed()
    console.print(Panel.fit(
        "[bold green]Polymarket Quant Bot[/bold green]  (+ Nexus-style gates)\n"
        f"Mode: [bold]{cfg.mode.upper()}[/bold]  |  "
        f"Live allowed: [bold]{'YES' if live_gate.allowed else 'NO'}[/bold]\n"
        f"Assets: {', '.join(cfg.assets)}  |  Windows: {cfg.windows}m\n"
        f"[dim]{live_gate.reason or 'double opt-in OK'}[/dim]\n"
        "[dim]Paper by default. Live needs MODE=live + LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISK[/dim]",
        title="bosona-style + Nexus protections",
    ))

    feed = PriceFeed()
    ws_feed = ClobWebSocketFeed(url=cfg.clob_ws_url) if cfg.clob_ws_enabled else None
    if ws_feed:
        ws_feed.start()
        console.print(f"[dim]Public CLOB WebSocket enabled: {cfg.clob_ws_url}[/dim]")
    strategy = Strategy()
    executor = create_executor(strategy)
    install_risk_engine()
    resolver = Resolver(strategy)

    # Plugin-based strategy loading (Priority 2): every module in
    # bot/strategies/ that exposes build(shared_strategy) gets auto-registered,
    # gated by its own STRATEGY_ENABLED_ENV if it declares one. Add/remove a
    # strategy by dropping/deleting a file in bot/strategies/ — no main.py edits.
    registry = load_all(strategy)

    status_srv = start_status_server()
    metrics.start_metrics_server()
    if status_srv:
        console.print("[dim]Status endpoint enabled — set BOT_STATUS_URL on the dashboard to this host's /status[/dim]")

    cycle = 0
    while running:
        cycle += 1
        cycle_started = time.perf_counter()
        try:
            markets = find_all_active()
            if not markets:
                console.print("[yellow]No active markets found this cycle[/yellow]")
                time.sleep(8)
                continue

            if ws_feed:
                ws_feed.set_assets(
                    token_id
                    for market in markets
                    for token_id in (market.get("up_token_id"), market.get("down_token_id"))
                )

            states = []
            for m in markets:
                st = MarketState(m, feed, book_feed=ws_feed)
                st.refresh()
                states.append(st)

            # Evaluate & execute (arb/directional + market-making + copy-trading)
            all_intents = []
            intents_by_slug = {}
            for st in states:
                intents = registry.evaluate_all(st)
                intents_by_slug[st.market.get("slug", "")] = intents
                all_intents.extend(intents)

            if hasattr(executor, "begin_cycle"):
                executor.begin_cycle(
                    arb_intents=sum(1 for intent in all_intents if intent.is_arb_leg)
                )
            if hasattr(executor, "observe"):
                for st in states:
                    executor.observe(st, intents_by_slug.get(st.market.get("slug", ""), []))
            elif all_intents:
                fills = executor.execute(all_intents)
                console.print(f"[cyan]Cycle {cycle}: executed {len(fills)} fills[/cyan]")

            # Status
            table = build_status_table(states, strategy, executor)
            console.print(table)
            rows = market_rows(states, strategy)
            update_markets(rows)
            book_ages = []
            if ws_feed:
                for state in states:
                    for token_id in (state.market.get("up_token_id"), state.market.get("down_token_id")):
                        age = ws_feed.book_age_ms(token_id) if token_id else None
                        if age is not None:
                            book_ages.append(age)
            cycle_summary = getattr(executor, "last_cycle_summary", {})
            update_cycle_summary({
                "scanned": len(states),
                "arb_intents": int(cycle_summary.get("arb_intents", 0)),
                "gated": int(cycle_summary.get("gated", 0)),
                "would_fill": int(cycle_summary.get("would_fill", 0)),
                "skipped_no_depth": int(cycle_summary.get("skipped_no_depth", 0)),
                "book_age_ms": round(max(book_ages), 1) if book_ages else None,
                "cycle_ms": round((time.perf_counter() - cycle_started) * 1000.0, 1),
            })

            # Outcome resolution: once a window's countdown hits zero, track it
            # until Gamma reports the settlement price, then record real PnL.
            for row in rows:
                if row["secondsToClose"] <= 0:
                    resolver.mark_closed(row["slug"], row["asset"])
            resolver.poll()

            # Kill switch (paper only tracks simple daily for now)
            if hasattr(executor, "check_kill_switch") and executor.check_kill_switch():
                break

            # Cadence: fast enough for short windows, not spammy
            time.sleep(4.0)

        except KeyboardInterrupt:
            break
        except Exception as e:
            log.exception(f"Cycle error: {e}")
            time.sleep(5)

    console.print("[bold]Bot stopped.[/bold]")
    if ws_feed:
        ws_feed.stop()
    summary = ledger.session_summary()
    console.print(
        f"Session ledger: intents={summary['intents']} blocked={summary['blocked']} "
        f"fills={summary['fills']} (dry={summary['dry_run_fills']} live={summary['live_fills']}) "
        f"total_usd≈{summary['total_usd']:.1f}"
    )
    active_cd = cooldown.status()
    if active_cd:
        console.print(f"Active cooldowns: {list(active_cd.keys())}")


if __name__ == "__main__":
    main()
