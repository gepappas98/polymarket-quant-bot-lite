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
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

from .config import cfg
from .market_finder import find_all_active
from .feeds import PriceFeed, MarketState
from .strategy import Strategy
from .executor import create_executor
from .gates import cooldown, is_live_trading_allowed
from .ledger import ledger
from .status_server import start_status_server, update_markets

console = Console()
logging.basicConfig(
    level=getattr(logging, cfg.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
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
    strategy = Strategy()
    executor = create_executor(strategy)

    status_srv = start_status_server()
    if status_srv:
        console.print("[dim]Status endpoint enabled — set BOT_STATUS_URL on the dashboard to this host's /status[/dim]")

    cycle = 0
    while running:
        cycle += 1
        try:
            markets = find_all_active()
            if not markets:
                console.print("[yellow]No active markets found this cycle[/yellow]")
                time.sleep(8)
                continue

            states = []
            for m in markets:
                st = MarketState(m, feed)
                st.refresh()
                states.append(st)

            # Evaluate & execute
            all_intents = []
            for st in states:
                intents = strategy.evaluate(st)
                all_intents.extend(intents)

            if all_intents:
                fills = executor.execute(all_intents)
                console.print(f"[cyan]Cycle {cycle}: executed {len(fills)} fills[/cyan]")

            # Status
            table = build_status_table(states, strategy, executor)
            console.print(table)
            update_markets(market_rows(states, strategy))

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