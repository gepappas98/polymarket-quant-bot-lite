# Roadmap

Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

## Just shipped (v0.3.0) — see CHANGELOG.md for full detail

- [x] **Plugin strategy architecture** — `bot/strategies/loader.py` auto-discovers strategies; no `main.py` edits to add/remove one
- [x] **Market making** — `bot/strategies/market_making.py`, inventory-skewed two-sided quoting
- [x] **Copy trading** — `bot/strategies/copy_trading.py`, tracked-wallet replication
- [x] **Kelly Criterion sizing** — `bot/kelly.py`
- [x] **Daily kill switch persisted across restarts** — `bot/daily_limit.py`
- [x] **Backtest harness** against historical order-book snapshots — `bot/backtest.py` (see near-term note below on its risk-model simplification)
- [x] **PostgreSQL ledger option** — `bot/ledger_pg.py`, `LEDGER_BACKEND=postgres`
- [x] **ML ensemble (XGBoost)** for win-probability prediction — `bot/ml_model.py`, `bot/strategies/ml_directional.py`
- [x] **Cross-venue signal (Polymarket ↔ Kalshi)** — `bot/strategies/cross_platform_arbitrage.py` — directional only, see near-term item below for the hedged version
- [x] **Prometheus/Grafana monitoring stack** — `bot/metrics.py` + `deploy/`
- [x] **Dashboard trading panels** (Supabase-backed, in-browser) — market making, copy trading, Kelly slider, cooldown timer, strategy manager, backtester, alerting — see `docs/FEATURES.md`
- [x] **`.env.example` and `requirements.txt` synced** with all v0.3.0 plugins — every new env var is documented with inline comments in `.env.example`; optional deps (`xgboost`, `cryptography`, `prometheus-client`, `psycopg[binary]`) are listed commented-out in `requirements.txt` so the base install stays lightweight
- [x] **Competitive research** — `docs/COMPETITIVE_RESEARCH.md`: analysis of two viral "Polymarket bot" videos claiming outsized returns; both show internally inconsistent numbers (impossible trade rates / win rates that move with zero new fills) and match a documented current scam pattern (AI-cloned dashboard mockups screen-recorded as "proof"). Several of their dashboard *visualization ideas* are legitimately buildable from this repo's real ledger data — tracked as new items below.

## Near term (v0.3.1)

- [ ] **Kalshi order-execution client** — the current cross-venue module only trades the Polymarket leg; without a Kalshi execution client it's a directional signal, not the hedged arbitrage originally scoped
- [ ] **Decide the relationship between `bot/strategies/*` and the dashboard's Supabase equivalents** (`useMarketMaker`, copy-trading panel, in-browser backtester) — today they're fully independent implementations of the same ideas; either connect them (dashboard reads the worker's real ledger) or explicitly document the dashboard versions as simulation/monitoring-only
- [ ] **Exercise the PostgreSQL ledger against a real database** — implemented and unit-tested for its fallback path, but not yet run against live Postgres
- [ ] **Injectable clock for gates** — `bot/gates.py`/`bot/portfolio_gates.py` cooldown and drawdown checks use wall-clock time, which is why `bot/backtest.py` has to fall back to a simplified, time-independent risk model; making the clock injectable would let backtests replay the real gates faithfully
- [ ] **WebSocket CLOB market channel** — lower-latency books than REST polling
- [ ] **Window open-price delta** — `bot/feeds.py::PriceFeed` (ccxt/Binance) already exists as a hook point but isn't consumed by the strategy yet; wire it in to replace the lightweight imbalance-only signal
- [ ] **Order lifecycle** — cancel stale limits, reconcile fills via user channel

## Shipped earlier (v0.2.x, previously undocumented — folded in for completeness)

- [x] **Auto-redeem** resolved winning positions — internal PnL bookkeeping settles automatically via `bot/resolver.py` once Gamma reports a window's outcome (on-chain redemption for LIVE mode is still a separate, not-yet-done step)
- [x] **Structured logging** (JSON) + legacy Prometheus-text metrics — `LOG_FORMAT=json`; `ENABLE_METRICS=true` on the status server
- [x] **Unit tests** for strategy gates, arb math, and market slug discovery — `tests/` (`pytest`, 82 tests)
- [x] **Multi-asset** defaults: ETH, SOL, XRP 5m/15m with per-asset exposure caps — code default `ASSETS=BTC,ETH,SOL,XRP`; `MAX_MARKET_EXPOSURE_BY_ASSET` overrides per asset
- [x] **Max drawdown + low-profit pair locks** (Nexus-style portfolio protections) — `bot/portfolio_gates.py`
- [x] **Dashboard bridge** — `bot/status_server.py` JSON status API for the frontend's `BOT_STATUS_URL`

## Medium term (v0.4)

### v0.5.0 — inventory & swarm (worker)

- [x] `bot/inventory.py` — paired / residual / avg_set_cost / second-side lag
- [x] Complete-set accumulator + SECOND_SIDE + spot fair blend (`USE_SPOT_FAIR`)
- [x] `bot/ctf_ops.py` — paper-safe split/merge/redeem skeleton (live fail-closed)
- [x] `bot/swarm.py` — non-LLM module consensus (TIDAL…LUMEN)
- [x] Ledger `meta.swarm` / `set_id`; `/status` swarm block
- [x] Deploy docs: `fly.risk.toml`, `Dockerfile.risk` (Leaders API ≠ worker)

### v0.5.1 — hygiene & arb path (partial → complete)

- [x] **P0-3** Swarm bypass for deterministic ARB / SECOND_SIDE (`is_arb_leg` / reason)
- [x] Regression: both-sides ARB test passes with `SWARM_ENABLED=true`
- [x] **P1-5** `getattr(state, "fair_up_prob", None)` (no AttributeError on mocks)
- [x] Document MarketState required vs optional fields
- [x] Full `pytest` green on clean checkout
- [ ] Delete unused `bot/bot_config.py`, `bot/bot_strategy.py`, `bot/bot_inventory.py`
- [ ] Grep CI: no `bot_strategy` / `bot_inventory` / `bot_config` imports

### v0.5.2 — fill reconciliation & pairs (in progress)

- [x] **P0-1 (core):** order id + requested vs filled; poll to terminal state; inventory/ledger only on confirmed fills; never `filled` on submit alone
- [x] **P0-1 (paper honesty):** paper fills labeled `SIMULATED_FILL`; excluded from “proven edge” reports
- [x] **P0-2 (core):** `ArbPair` states `PAIR_PENDING | PAIR_PARTIAL | PAIR_COMPLETE | PAIR_FAILED`; `set_id` through executor; `is_arb_leg` not forced false
- [x] **P0-2 (policy):** on `PAIR_PARTIAL` — active second-side recovery
- [x] Reject new independent arb while pair incomplete on same window
- [ ] **P1-7:** `update_inventory(..., is_arb_leg=intent.is_arb_leg)` + arb vs directional PnL attribution (if not fully wired)

---

## CRITICAL — remaining v0.5 overhaul

> Prefer **paper** until P0-2 policy + P0-4 are done. Live only with tiny size after P0-1 verified against real CLOB fill reports.

### P0-4 — Realistic paper + backtest execution 🔴 NEXT

**Bug:** `shares = size_usd / price` ignores book depth, fees, partials, latency.

- [ ] Consume L1 (later L2) size at touch; partial fills; residual unfilled
- [ ] Fee model (taker/maker), optional slippage bps, stale-quote reject
- [ ] Backtest: one fill per level/snapshot; no infinite refill of the same touch across bars
- [ ] Report **net edge** = `1 - exec_up - exec_down - fees - slippage` (not raw `1 - sum_asks`)
- [ ] Mark reports: `SIMULATED — not live expectancy`

### P0 pipeline (target)

```text
ARB / SECOND_SIDE → depth + risk gates → execute     (swarm bypassed) ✅
DIRECTIONAL       → fair value → swarm → risk → execute
MM / COPY         → strategy gates → risk → execute
```

Still open:

- [ ] Keep swarm **only** for directional (and optional MM soft-score) — confirm MM/COPY never hard-blocked by swarm unless intended
- [x] Document the pipeline in STRATEGY.md

---

## P1 — after soft green

### P1-6 — Remove duplicate modules 🟠

- [ ] Delete or quarantine: `bot/bot_config.py`, `bot/bot_strategy.py`, `bot/bot_inventory.py`
- [ ] Single path: `bot.config` / `bot.strategy` / `bot.inventory`
- [ ] CI grep guard

### P1-8 — Execution policy (not global PREFER_MAKER) 🟠

- [ ] ARB: taker if net edge > X; maker only if expected fill allows
- [ ] DIRECTIONAL: maker-preferred default
- [ ] Config: `ARB_EXECUTION_MODE=taker|maker|auto`

### P1-9 — API security for exposed deploys 🟠

- [ ] Require `API_TOKEN` when bound beyond localhost (not only `MODE=live`)
- [ ] Production: explicit `API_CORS_ORIGINS` (no `*`); see `deploy/RISK_API_FLY.md`
- [ ] Multi-user: replace hard-coded `user_id=1` before any shared SaaS claim

### P1-10 — Single source of truth for positions 🟠

- [ ] Worker ledger (JSONL/Postgres) → `/status` or risk API → dashboard
- [ ] Supabase / in-browser sim documented as **demo only**
- [ ] Optional: dashboard read-only when `BOT_STATUS_URL` set (no dual write)

---

## Near-term (after P0-4)

### Execution quality

- [ ] Maker ladder + cancel/replace (order lifecycle)
- [ ] WebSocket CLOB user + market channels
- [ ] Explicit maker|taker from exchange fill messages

### CTF / settlement

- [ ] Live relayer for split/merge/redeem (today paper-safe only)
- [ ] Settlement identity: `order_id → fill_id → position_id → outcome` (not broad slug+time)

### Observability (incl. CLAUDE×QUANT-style, data-bound only)

- [ ] **Inventory & Flow panel** — matched % vs residual %, naked USD, avg set cost (`InventoryBook`)
- [ ] **Decision funnel** on `/status`: `scanned → arb → dir → swarm_pass → gate_pass → submitted → filled`
- [ ] **Set completion stream** — ledger events when pair completes (`set_id`)
- [ ] Session report: sets completed, mean set edge, residual vs paired PnL
- [ ] Cycle latency: `book_age_ms`, `cycle_ms` in status + ledger meta
- [ ] Copy-trading latency: detect → execute ms
- [ ] Market tile grid (dashboard) — compact multi-window UP/DOWN; PAPER/LIVE badge mandatory

### Spot fair

- [ ] `SPOT_FAIR_MODE=window|vwap` (blended prior, not sole signal)

### Naming / honesty

- [ ] Rename `cross_platform_arbitrage` → `cross_platform_signal` (or label “directional only”)
- [ ] Trailing stop: document peak-price trail vs fixed adverse threshold

### Explicitly defer from cinematic UIs

- Hexbin / spectrogram as proof of alpha before realistic fills
- Unverified $/day and six-figure equity as product targets
- “Neural” branding without walk-forward metrics

---

## Medium term (v0.6)

- [ ] Event-driven backtest + walk-forward validation for ML
- [ ] ML: calibration, Brier / log-loss, PnL-after-fees at threshold (not accuracy alone)
- [ ] Shadow mode: live signals, paper size; parity report
- [ ] Injectable clock for gates/backtest
- [ ] Historical book snapshot worker (stop synthetic-only training)
- [ ] Kalshi **execution** client only after dual-leg risk limits exist
- [ ] MCP read-only status tools

---
## Additional dashboard and infrastructure items

- [ ] **MCP tools** — read-only status / safety model for AI clients (like Nexus MCP)
- [ ] **Real historical snapshot capture** — a small worker/cron that writes `bot/backtest.py`-compatible JSONL snapshots from live order books, so backtesting and ML training stop depending on hand-built synthetic data
- [ ] **Automated test coverage for the dashboard** (`src/`, `supabase/`) — currently none
- [ ] **Dashboard panels derived from competitive research** — see `docs/COMPETITIVE_RESEARCH.md` for the full mapping; each of these is buildable from data the ledger/strategy layer already produces, no new tracking required except where noted:
  - [ ] Resolution grid — live heatmap of open windows colored by current UP price
  - [ ] Inventory plane — UP vs. DOWN shares scatter, per market
  - [ ] Second-side lag — time between the two legs of a market-making pair filling
  - [ ] Run chain — recent fill sequence (UP→DOWN→UP...) per market
  - [ ] Complete-set vs. directional-remainder split, surfaced as a stat
  - [ ] Drawdown-risk gauge (0–10), normalized from the existing daily-limit/drawdown ratio
  - [ ] Loop health strip (cycle heartbeat + last-cycle duration) on `/status`
  - [ ] Win-streak counter from settled ledger outcomes
  - [ ] Maker/taker fill ratio — blocked on real resting-order tracking (see "Order lifecycle" above)

## Longer term

- [ ] Adaptive arb threshold and edge model per volatility regime
- [ ] Maker rebate optimization and multi-level quotes
- [ ] Paper ↔ live parity checks and shadow mode (live signals, paper size)
- [ ] Multi-process / multi-region coordination (optional)

## Non-goals (for now)

- Guaranteed profit or “copy bosona”
- Full browser trading UI as the primary product
- Running the trading loop on Vercel serverless (use Fly / Railway / Render workers)
- Treating the cross-venue Kalshi signal as risk-free arbitrage before a real execution client exists on both legs

## Deployment targets

| Platform | Role | Status |
|----------|------|--------|
| **Fly.io** | Primary long-running worker | Config ready (`fly.toml`) |
| **Railway** | Worker alternative | Config ready (`railway.toml`) |
| **Render** | Worker alternative | Blueprint ready (`render.yaml`) |
| **Docker** | Any host / K8s | `Dockerfile` |
| **Vercel** | Static placeholder / future dashboard only | `vercel.json` + `public/` |
| **Lovable** | Not a runtime for this worker; use for UI experiments only | N/A |

---

Contributions and issues: open on [github.com/gepappas98/polymarket-quant-bot](https://github.com/gepappas98/polymarket-quant-bot).
