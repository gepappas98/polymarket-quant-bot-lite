# Competitive research: viral "Polymarket bot" dashboard videos

Analysis of two social-media posts ("GROK BOT" / xAI desk, and "hot-garbage //
POLYMARKET BOT") claiming large, consistent profits on short-window BTC
Up/Down markets — the same market category this repo trades. Written up
because (a) the claims are directly relevant to what "good performance"
should look like for this strategy class, and (b) several of the dashboard
*concepts* shown are genuinely worth building here, independent of whether
the bots themselves are real.

**Verdict up front: both are almost certainly fabricated marketing content,
not evidence of a working strategy.** Treat the numbers as zero signal. Some
of the dashboard *ideas* are still worth stealing — see [What's worth
building](#whats-worth-building-here) below.

## What was reviewed

Four screenshots/video-frames, each with a media player overlay (pause,
progress bar, volume) and an X/Twitter-style engagement bar (like, reply,
repost, share) — i.e. these are screen-recorded video posts, not static
screenshots of a live app someone is actively using.

1–2. **"GROK BOT · BTC POLYMARKET · LIVE"** — "xAI desk," two frames 153
seconds apart.
3–4. **"hot-garbage // POLYMARKET BOT"** — wallet `0x3119...9E2E`,
"TWO-SIDED MAKER," two frames 4 seconds apart.

## Why these don't hold up

### 1. GROK BOT: the trade rate is impossible for this market

| | Frame @ 18:17:37 | Frame @ 18:20:10 | Delta |
|---|---|---|---|
| Trades | 58 | 201 | **143 trades in 153s** |
| Win rate | 100.0% | 100.0% | — |
| Balance | $12.06 | $14,485 | +$14,473 |
| BTC spot (shown) | $78,128 | $78,148 | +0.026% (a realistic tick) |

143 trades in 153 seconds is roughly **one trade every 1.07 seconds**, sustained,
on markets that only exist as 5- and 15-minute windows and can't settle
faster than their window closes. A 100.0% win rate holding across that
entire jump — and across 201 trades total — isn't a strategy edge, it's a
sign the "WIN" figure isn't computed from real settled outcomes at all.
Meanwhile the BTC price tick between the two frames *is* a realistic 153-second
move — consistent with a live price feed wired into an otherwise scripted
performance panel (a common tell: pull one real, verifiable number to anchor
credibility, script the rest).

The chart itself is labeled **"SIMULATED"** directly under the candlesticks,
sitting next to a **"LIVE"** badge elsewhere on the same screen — the
dashboard contradicts itself in plain text.

### 2. hot-garbage: PnL and win rate move with zero new fills

| | Frame @ 21:35:10 UTC | Frame @ 21:35:14 UTC | Delta |
|---|---|---|---|
| Fills (24h) | 454 | 454 | **0 new fills** |
| Win rate | 49.7% | 50.5% | **+0.8pp** |
| PnL | $264,835 | $264,939 | +$104 |
| BTC spot (shown) | $77,884 | $77,782 | −0.131% in 4s |

Unrealized PnL moving between two frames with no new fills is fine (open
inventory marking to market). A **win-rate percentage computed over a fixed
count of settled fills cannot change** unless the fill count also changes —
here it doesn't. That's not noise, it's two numbers that were animated
independently of each other. Separately, −0.131% in 4 seconds is an extreme,
flash-crash-level move for BTC spot; real market-making dashboards built on
a genuine feed don't tick like that at rest.

"MODEL EDGE +11.4pp" is also worth flagging on its own: an 11-percentage-point
edge on a short-window binary market is not a plausible market-making edge —
real edges in this space are typically low single-digit percent at best. A
number that large is a red flag on its own, with or without the timing
inconsistency above.

### 3. This matches a documented, current scam pattern

This isn't a one-off guess — it matches reporting from mid-2026 on exactly
this genre of content:

- A finance-writer investigation (reported via 10pmtrader.com, June 2026)
  documented the actual production pipeline for these videos: paste a
  screenshot of a real trading dashboard into an AI coding tool, ask it to
  reproduce the design with arbitrary numbers, export as a webpage,
  screen-record it, post it. Minutes of work, indistinguishable from a real
  live app at video resolution.
- StepSecurity's February 2026 research found a hijacked, previously
  legitimate GitHub organization seeded with 20+ fake Polymarket
  copy-trading bot repos, each with a polished README and fabricated star
  counts, hiding typosquatted npm packages that steal wallet private keys
  and open an SSH backdoor. The pattern: viral "proof" video → GitHub repo
  or Telegram link → credential theft.
- Separately, a Wall Street Journal/Politico investigation (June 2026) found
  Polymarket itself had paid creators to film fake trades on cloned
  lookalike sites and post them as genuine wins — 118 videos showing ~$900K
  in fabricated profit where the real underlying bets would have *lost*
  over $166K. This is the same "confident, good-looking, false" content
  category, at platform scale.

None of this proves these two specific posts are part of either campaign —
there's no way to verify that from four frames — but it establishes that
fabricated Polymarket trading-bot proof videos are a known, current,
well-documented pattern, not a fringe theory. The internal math
inconsistencies above are sufficient on their own regardless.

### 4. Neither gives you a way to actually check

Neither post shows a full wallet address. "hot-garbage" shows
`0x3119...9E2E` — truncated, so it can't be looked up on Polygonscan (where
all Polymarket trades are real, public, and auditable). A genuine claim like
this is trivially easy to back up with a full address; showing only a
truncated one is a way to *look* grounded while staying unverifiable. If a
claim like this shows up again: ask for the full address and check the fill
history on-chain yourself before taking any of it as a benchmark.

**Practical safety note:** if either of these posts links to a GitHub repo,
Telegram group, or "download the bot" offer, don't clone it or paste
credentials into it — see the StepSecurity finding above. This applies
generally, not just to these two.

## What's worth building here

Setting the numbers aside, a handful of the *visualization ideas* in the
hot-garbage dashboard map cleanly onto data this repo's ledger and strategy
modules already produce. Building the real version of these (fed by
`bot/ledger.py`, not invented) would be a legitimate, honest addition:

| Idea seen | Maps onto (already exists) | What it would need |
|---|---|---|
| **Resolution grid** — live heatmap of open windows colored by current UP price | `market_finder`/`feeds.MarketState` across configured assets/windows | New dashboard panel; data already available each cycle |
| **Inventory plane** — UP shares vs. DOWN shares scatter, per market | `strategy.py`'s `Inventory` (`up_shares`, `down_shares`, `up_cost`, `down_cost`) | Expose per-market inventory snapshot via `status_server.py` |
| **Second-side lag** — time between the first and second leg of a market-making pair filling | Ledger `kind="fill"` entries, timestamp + `market_slug` + `side` | Derive from existing fills; no new tracking needed |
| **Run chain** — sequence of which side filled recently (UP→DOWN→UP...) | Same ledger fill history, ordered by `ts` | Pure read-side query over existing data |
| **Complete-set vs. directional-remainder split** | Already distinguished internally (arb pairing vs. directional tilt in `strategy.py`) | Surface the existing distinction as a stat instead of computing something new |
| **Maker/taker fill ratio** | Not tracked today — `executor.py` does optimistic-fill simulation only | Real prerequisite: actual resting-order tracking (already a ROADMAP item — real order lifecycle / WebSocket book) |
| **Drawdown-risk gauge (0–10)** | `bot/daily_limit.py::current_daily_pnl()` vs. `cfg.daily_loss_limit_usd`, plus `portfolio_gates.max_drawdown_gate()` | Normalize the existing ratio into a 0–10 display value |
| **Loop health strip** (cycle count / lag / next-refresh countdown) | `bot/main.py`'s own cycle loop | Add a heartbeat timestamp + last-cycle-duration to the `/status` JSON |
| **Win-streak counter** | Ledger `kind="outcome"` history | Consecutive-win count over recent settled outcomes — genuinely computable, unlike the fake dashboards' framing |

Two explicit **don'ts**, learned directly from what made these look fake:

- **Don't display a "model edge" stat without deriving it from real fills.**
  If this repo's dashboard ever shows something like "+11pp edge," that's
  the same red flag identified above, just self-inflicted. Compute it as
  `fair_value_at_fill − fill_price`, averaged over real fills, and expect a
  small number.
- **Don't decorate with content-free visuals.** The "GROK NET" force-directed
  node graph in the other bot's dashboard is pure eye-candy — colored dots
  and edges with no stated data mapping. It looks sophisticated and
  communicates nothing. Skip anything in the new dashboard that can't be
  traced to a real field in the ledger or `Inventory`.
- **If a wallet address is ever shown, show the full address** (or link
  straight to Polygonscan), not a truncated one — this repo's own paper
  ledger already has nothing to hide, so there's no reason to imitate the
  one habit that made these two posts unverifiable by design.

## Sources

- 10pmtrader.com, "Polymarket Bot Scam: What the Viral AI Trading Terminal Is
  Really About" (June 2026) — documents the screenshot → AI-cloned dashboard
  → screen-record → GitHub/Telegram funnel pipeline.
- StepSecurity, "Malicious Polymarket Bot Hides in Hijacked dev-protocol
  GitHub Org and Steals Wallet Keys" (February 2026).
- Wall Street Journal / Politico, reported via CBS News, TechCrunch, PYMNTS,
  Odaily (June 2026) — Polymarket paid-creator fake-trade video investigation.
- MEXC News, on a separately *verified* $1M Polymarket wallet (June 2026) —
  included for contrast: real claims in this space are the ones that
  publish a full, on-chain-auditable address, which is exactly what both
  bots above omit.
