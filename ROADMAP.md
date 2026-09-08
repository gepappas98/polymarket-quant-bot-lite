# Roadmap

## P0 — REAL vs PAPER vs DEMO/MOCK boundary (2026-09-08)

- [x] Inventory Polymarket REST/WebSocket, metadata, trader activity, historical, Binance, Supabase, browser, demo, and test-fixture sources.
- [x] Make app mode explicit: `APP_MODE=PRODUCTION` is the default fail-closed behavior, while synthetic status requires explicit `APP_MODE=DEMO`; dashboard metrics expose provenance and unavailable values remain `NO DATA`.
- [x] Add explicit `data_source`, `execution_mode`, `market_data_source`, and `is_simulated` runtime metadata.
- [x] Replace browser Polymarket MM's Binance proxy with a public Polymarket CLOB L2 WebSocket keyed by `token_id`; fail closed as OFFLINE / NO DATA, and label all orders PAPER and fills SIMULATED.
- [x] Reject malformed worker status and stop silently replacing worker failures with DEMO values.
- [x] Block browser paper orders and marking when only DEMO/proxy data is available.
- [x] Replace browser copy-position simulation with normalized REAL Polymarket Data API activity; deduplicate source events, reject stale/invalid/risky signals, show NO DATA on failure, and keep LIVE copy disabled.
- [x] Label live market input, paper execution, demo data, and test mocks distinctly.
- [x] Preserve legitimate unit-test mocks and document remaining simulation paths in `docs/DATA_BOUNDARY_AUDIT.md`.
- [x] Establish the worker execution ledger as the authoritative execution/event source with stable event IDs, lifecycle metadata, idempotent appends, health/stale/reconciliation endpoints, and worker-authority markers; browser PaperDesk execution is blocked when worker authority is present.
- [x] Build the production REAL Polymarket CLOB L2 historical recorder with WebSocket primary ingestion, REST snapshot/reconciliation, restart-safe SQLite persistence, deduplication, stale detection, reconnects, retention, and recorder metrics.
- [x] Replace production backtest historical input with fail-closed REAL recorder replay; retain legacy fixture inputs only for unit-test mocks.
- [x] Make ML retraining fail closed on anything except provenance-bearing REAL Polymarket observations joined to Polymarket resolution labels; use chronological market-grouped train/validation/test splits and persist dataset provenance in model artifacts.
- [x] Calibrate REAL paper execution from chronological Polymarket L2 observations with conservative maker-fill ranges, observed snapshot latency, spread/depth/mid-move metrics, explicit assumptions, and out-of-sample reporting; exact queue position and unobserved fills remain unclaimed.

## 0.4.0 Architecture Clarification & Realism

- [x] **[SIM]** Keep the legacy Binance path as `Research Simulation — Binance/Generic`; it is not connected to production Polymarket MM.
- [x] **[MM]** Browser paper market maker consumes real public Polymarket CLOB L2 by `token_id`, with live book metrics and stale/offline fail-closed behavior.
- [x] **[WORKER]** Add market quality filters and configurable defaults.
- [x] **[WORKER]** Make the arb threshold volatility-aware and cap fractional Kelly sizing.
- [x] **[WORKER]** Protect the status API with optional `X-API-Token` authentication.
- [x] **[WORKER]** Add backtest slippage, copy-trading eligibility filters, and a consecutive-loss pause.
- [x] **[WORKER]** Add validated dependency extras and keep paper mode as the default.
- [x] **[WORKER]** WebSocket CLOB feed with heartbeat, reconnect, local books, and REST fallback.
- [x] **[RECORDER]** Persist REAL CLOB L2 snapshots/events for multiple tokens without changing live order execution.
- [ ] **[WORKER]** Hedged Kalshi execution.


Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

## Just shipped (v0.3.0) — see CHANGELOG.md for full detail

- [x] **Plugin strategy architecture** — `bot/strategies/loader.py` auto-discovers strategies; no `main.py` edits to add/remove one
- [x] **Market making** — `bot/strategies/market_making.py`, inventory-skewed two-sided quoting
- [x] **Copy trading** — `bot/strategies/copy_trading.py`, tracked-wallet replication
- [x] **Kelly Criterion sizing** — `bot/kelly.py`
- [x] **Daily kill switch persisted across restarts** — `bot/daily_limit.py`
- [x] **Backtest harness** against historical order-book snapshots — `bot/backtest.py` (see near-term note below on its risk-model simplification)
- [x] **PostgreSQL ledger option** — `bot/ledger_pg.py`, `LEDGER_BACKEND=postgres`
- [x] **ML ensemble (XGBoost)** for win-probability prediction — `bot/ml_model.py`, `bot/strategies/ml_directional.py` (production training requires validated REAL Polymarket datasets)
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
- [x] **WebSocket CLOB market channel** — lower-latency books than REST polling
- [ ] **Window open-price delta** — `bot/feeds.py::PriceFeed` (ccxt/Binance) already exists as a hook point but isn't consumed by the strategy yet; wire it in to replace the lightweight imbalance-only signal
- [x] **Order lifecycle** — partial fills remain open, timed-out remainders are canceled and cancellation is confirmed before accounting
- [ ] **Verified live fill pricing** — consume exchange VWAP/average only; no intent-price fallback

## Shipped earlier (v0.2.x, previously undocumented — folded in for completeness)

- [x] **Auto-redeem** resolved winning positions — internal PnL bookkeeping settles automatically via `bot/resolver.py` once Gamma reports a window's outcome (on-chain redemption for LIVE mode is still a separate, not-yet-done step)
- [x] **Structured logging** (JSON) + legacy Prometheus-text metrics — `LOG_FORMAT=json`; `ENABLE_METRICS=true` on the status server
  - [x] **Unit tests** for strategy gates, arb math, market slug discovery, sidecar health, and depth-aware paper execution — `tests/` (run `pytest` for the current count)
- [x] **Multi-asset** defaults: ETH, SOL, XRP 5m/15m with per-asset exposure caps — code default `ASSETS=BTC,ETH,SOL,XRP`; `MAX_MARKET_EXPOSURE_BY_ASSET` overrides per asset
- [x] **Max drawdown + low-profit pair locks** (Nexus-style portfolio protections) — `bot/portfolio_gates.py`
- [x] **Dashboard bridge** — `bot/status_server.py` JSON status API for the frontend's `BOT_STATUS_URL`

## Medium term (v0.4)

### v0.5.0 — inventory & swarm (worker)

- [x] `bot/inventory.py` — paired / residual / avg_set_cost / second-side lag
- [x] Complete-set accumulator + SECOND_SIDE + spot fair blend (`USE_SPOT_FAIR`)
- [x] `bot/ctf_ops.py` — paper-safe split/merge/redeem skeleton (live fail-closed; production relayer remains deferred)
- [x] `bot/swarm.py` — non-LLM module consensus (TIDAL…LUMEN)
- [x] Ledger `meta.swarm` / `set_id`; `/status` swarm block
- [x] Deploy docs: `fly.risk.toml`, `Dockerfile.risk` (Leaders API ≠ worker)

### v0.5.1 — hygiene & arb path (partial → complete)

- [x] **P0-3** Swarm bypass for deterministic ARB / SECOND_SIDE (`is_arb_leg` / reason)
- [x] Regression: both-sides ARB test passes with `SWARM_ENABLED=true`
- [x] **P1-5** `getattr(state, "fair_up_prob", None)` (no AttributeError on mocks)
- [x] Document MarketState required vs optional fields
- [x] Full `pytest` green on clean checkout
- [x] Delete unused `bot/bot_config.py`, `bot/bot_strategy.py`, `bot/bot_inventory.py`
- [x] Grep CI: no `bot_strategy` / `bot_inventory` / `bot_config` imports

### v0.5.1 — execution realism

- [x] Explicit partial-fill order state machine and cancel-remainder confirmation
- [x] Verified fill aggregation via exchange average/VWAP; no intent-price fallback
- [x] Depth-aware taker simulation with partial L1 consumption, VWAP, fees, and slippage
- [x] Probabilistic maker simulation with queue-ahead and latency
- [x] Gross PnL minus fees and slippage net reporting

### v0.5.2 — fill reconciliation & pairs (in progress)

- [x] Shadow live mode observes real CLOB books, signals, would-be fills, and market movement without order submission

- [x] **P0-1 (core):** order id + requested vs filled; poll to terminal state; inventory/ledger only on confirmed fills; never `filled` on submit alone
- [x] **P0-1 (paper honesty):** paper fills labeled `SIMULATED_FILL`; excluded from “proven edge” reports
- [x] **P0-2 (core):** `ArbPair` states `PAIR_PENDING | PAIR_PARTIAL | PAIR_COMPLETE | PAIR_FAILED`; `set_id` through executor; `is_arb_leg` not forced false
- [x] **P0-2 (policy):** on `PAIR_PARTIAL` — active second-side recovery
- [x] Reject new independent arb while pair incomplete on same window
- [x] **P1-7:** `update_inventory(..., is_arb_leg=intent.is_arb_leg)` + arb vs directional fill attribution

---

## Current implementation status (2026-09)

- Risk API sidecar: deployed at https://polymarket-quant-bot-lite-1.onrender.com; the frontend uses the public `VITE_API_URL` at build time.
- P0-4 realistic fills: worker requires an observed L2 book and consumes real bid/ask depth; synthetic infinite liquidity is rejected. This remains complete only while the focused paper-execution tests pass.
- Paper accounting: worker ledger and Lovable/Supabase Paper Desk remain separate persistence systems until the shared execution service is moved behind one server-side ledger.
- Live trading remains disabled by default; Kalshi remains signal-only; CTF settlement remains an open gap.

## Full P0 execution foundation

- [x] Shared order lifecycle, fill aggregation, VWAP, fee/slippage, and injectable clock primitives in `bot/execution.py`
- [x] Depth-aware paper fill engine with residuals and account-level buy/sell realized P&L (primitive; worker wiring now uses observed books)
- [x] Deterministic lifecycle, depth, account, and clock tests
- [x] Wire the shared primitives into the existing worker executor; Supabase Paper Desk remains explicitly simulation-only and is not a second confirmed-fill ledger
- [x] Add position settlement, exit policy, and arbitrage scanner primitives in `bot/p0.py`
- [ ] Move the Supabase Paper Desk behind the worker ledger/read-only status path; no dual writes are permitted

## CRITICAL — remaining v0.5 overhaul

> Prefer **paper** until P0-2 policy + P0-4 are done. Live only with tiny size after P0-1 verified against real CLOB fill reports.

### P0-4 — Realistic paper + backtest execution 🔴 NEXT

**Bug:** `shares = size_usd / price` ignores book depth, fees, partials, latency.

- [x] Consume observed L2 size at touch; partial fills; residual unfilled in the worker path
- [x] Fee model (taker/maker), optional slippage bps, stale-quote reject in shared fill primitives
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

- [x] Delete or quarantine: `bot/bot_config.py`, `bot/bot_strategy.py`, `bot/bot_inventory.py`
- [x] Single path: `bot.config` / `bot.strategy` / `bot.inventory`
- [x] CI grep guard

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
- [x] ML: chronological train/validation/test validation with Brier/log-loss provenance; calibration and PnL-after-fees remain follow-up metrics
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
