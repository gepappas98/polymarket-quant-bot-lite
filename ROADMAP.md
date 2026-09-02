# Roadmap

Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

External references that shaped recent priorities (research only — not affiliations):

- Public trader **@hot-garbage** (`0x3139…9e2e`): high-volume crypto Up/Down activity consistent with **complete-set accumulation + residual directional + inventory rebalance** (~50–55% event win rate, not 100%). See Polydata / Polymarket profile analytics.
- Viral **“GROK_001 / Grok Bot”** terminals: treat as **simulated / marketing UI** unless a wallet is independently verified; do not copy 100% win-rate claims into product metrics.

---

## Just shipped (v0.4.7) — PostgreSQL app-database compatibility

- [x] **PostgreSQL URL support** — `APP_DATABASE_URL=postgresql+psycopg://...` uses native SQLAlchemy engine options without SQLite-only args
- [x] **Driver guidance** — optional `psycopg[binary]`, deployment checklist, secret handling
- [x] **Compatibility tests** — PostgreSQL configuration + preserved SQLite in-memory/thread behavior
- [x] **Verification boundary** — local tests cover URL/engine config; live Postgres remains a CI/deploy responsibility

## Just shipped (v0.4.6) — mutating API authentication audit

- [x] **Protected mutating routes** — settings/risk, strategy updates, leaderboard refresh, ML retrain, trade placement, price updates, trailing-stop mutation require `require_api_token`
- [x] **Auth regression coverage** — unauthenticated rejected; Bearer strategy updates work
- [x] **Live-mode fail-closed** — missing `API_TOKEN` in live mode returns explicit config error

## Just shipped (v0.4.5) — CLOB price-feed integration

- [x] **CLOB midpoint adapter** — public midpoints for open-position token IDs
- [x] **Trailing-stop routing** — prices go through `process_price_update()` (persistence, gates, paper/live, WS close)
- [x] **Optional sidecar poller** — `CLOB_PRICE_FEED_ENABLED=false` by default
- [x] **Regression coverage** — midpoint normalization, invalid prices, fail-soft missing prices

## Just shipped (v0.4.4) — realized-PnL leaderboard enrichment

- [x] **Per-trader closed-position history** — public `/closed-positions` enrichment
- [x] **Fail-soft score enrichment** — single wallet failure does not fail refresh
- [x] **Bounded API footprint** — configurable top-N / per-wallet limits
- [x] **Regression coverage** — normalization, bounds, drawdown, opt-out

## Just shipped (v0.4.3) — public leaderboard adapter

- [x] **Official `GET /v1/leaderboard`** — category, period, pagination, wallet-field compatibility
- [x] **No synthetic fallback traders** — API failure → local closed-trade ledger only
- [x] **Configurable source** — official API + legacy `LEADERBOARD_SOURCE_URL` override

## Just shipped (v0.4.2) — trailing-stop execution

- [x] **Trailing-stop execution** — `token_id` / `current_price`; adverse-move → SELL intent
- [x] **Close-event accounting** — exit price, realized PnL, `position_closed` WebSocket event
- [x] **Price-update API** — authenticated `POST /api/trades/price`

## Just shipped (v0.4.1) — reproducibility and verification

- [x] **Clean-install deps** — `python-dotenv` declared
- [x] **Clean-checkout tests** — `pytest.ini` `pythonpath = .`
- [x] **v0.4.0 integration verification** — risk engine + dashboard surfaces intact

## Just shipped (v0.4.0) — advanced risk engine

- [x] **FastAPI risk-engine sidecar** (`app/`) — SQLite/Postgres app DB, ledger history
- [x] **Variance-capped Kelly** — rolling variance, `k_value` / `max_position_pct`
- [x] **Composite leaderboard + Hampel filtering**
- [x] **Category-aware strategy flags**
- [x] **Hampel preprocessing before XGBoost retrain**
- [x] **Advanced risk gates** — circuit breaker, time window, trailing stop, per-category ceilings; worker hook `RISK_ENGINE_ENABLED`
- [x] **Dashboard pages** `/leaders`, `/sizing`, `/strategies`, `/settings`

## Shipped in v0.3.x

- [x] Plugin strategy architecture (`bot/strategies/loader.py`)
- [x] Market making — inventory-skewed two-sided quoting
- [x] Copy trading — tracked-wallet replication
- [x] Kelly Criterion sizing (`bot/kelly.py`)
- [x] Daily kill switch persisted across restarts
- [x] Backtest harness (`bot/backtest.py`)
- [x] PostgreSQL ledger option (`bot/ledger_pg.py`)
- [x] ML ensemble (XGBoost) + `ml_directional` strategy
- [x] Cross-venue signal Polymarket ↔ Kalshi (directional only)
- [x] Prometheus/Grafana stack (`deploy/`)
- [x] Dashboard trading panels (Supabase-backed)
- [x] Multi-asset defaults (BTC, ETH, SOL, XRP) + per-asset exposure caps
- [x] Max drawdown + low-profit pair locks (`portfolio_gates.py`)
- [x] Auto-settle bookkeeping via `resolver.py` (on-chain redeem still open for LIVE)
- [x] Structured logging + metrics hooks
- [x] Unit tests for gates, arb math, discovery (`tests/`)

---

## Near-term (v0.5) — hot-garbage–style inventory edge

These items come from public analysis of high-volume Up/Down makers (complete-set + residual directional). They are the highest-ROI gaps relative to what the worker already has.

### P0 — inventory & complete-set economics

- [ ] **`bot/inventory.py` (or extend `strategy.py`)**
  - Track per-market: `up_inv`, `down_inv`, `paired = min(up, down)`, `residual = up - down`
  - Track **average complete-set cost** across staggered fills (not only instant `sum_asks`)
  - Metrics: `sets_completed`, `avg_set_cost`, `edge_per_set`, `residual_usd`
- [ ] **Complete-set accumulator strategy** (enhance core arb / dedicated plugin)
  - Build both sides over multiple executions inside the same window (bosona / hot-garbage style)
  - Target band e.g. mean set cost ≤ `0.95–0.98` (config: `TARGET_SET_COST`)
  - Prefer maker limits; allow taker only when residual edge ≫ threshold
- [ ] **Second-side lag logic**
  - After a one-sided fill, actively work the opposite side while the pair remains cheap
  - Timeout + max naked residual USD per market (`MAX_NAKED_RESIDUAL_USD`)
- [ ] **Hold-to-resolution default**
  - Align with low early-sell behavior observed on profitable MM wallets
  - Early exit only via existing risk paths (trailing stop, kill switch, pair lock) — not discretionary churn

### P0 — CTF inventory ops (live)

- [ ] **`bot/ctf_ops.py`** — split / merge / redeem via Polymarket relayer (gasless where supported)
  - Split pUSD → YES+NO before two-sided quoting
  - Merge excess pairs to free collateral
  - On-chain **redeem** winning tokens after resolve (complements `resolver.py` bookkeeping)
  - Hard-gated: `MODE=live` + double opt-in only

### P1 — execution quality

- [ ] **Maker-first quote ladder** — multi-level or single-level resting both sides; skew from residual (extends `market_making.py`)
- [ ] **Thin-book reject** — skip intents when depth/size below `MIN_BOOK_DEPTH_USD` (GROK-UI log idea, real risk control)
- [ ] **Fill ledger enrichment** — `maker|taker`, `set_id`, `residual_after`, `set_cost_contribution`
- [ ] **Wire `PriceFeed` (Binance/ccxt) into strategy fair value** — window open-price delta / spot vs mid (still open from v0.3.1)
- [ ] **Order lifecycle** — cancel stale limits; reconcile fills via CLOB user channel / WS

### P1 — worker ↔ product hygiene

- [ ] **Turn `RISK_ENGINE_ENABLED` on by default** after sustained paper co-run with the worker
- [ ] **Injectable clock for gates** — so `backtest.py` can replay cooldown / drawdown faithfully
- [ ] **Kalshi order-execution client** — until then keep cross-venue labeled **directional signal only** (not hedged arb)
- [ ] **Dashboard vs worker strategy dual implementation** — either:
  - connect desk panels to worker ledger / `/status`, or
  - document dashboard MM/copy/backtest as **simulation/monitoring only** in README + FEATURES.md
- [ ] **Exercise PostgreSQL ledger against a real database** in CI
- [ ] **WebSocket CLOB market channel** — lower-latency books than REST

### P2 — observability (honest UI)

- [ ] **Status/dashboard inventory plane (numeric)** — paired vs residual, avg set cost, naked exposure — not cinematic fake lattices
- [ ] **Explicit PAPER / LIVE / SIMULATED badges** everywhere (never imply live 100% win rate)
- [ ] **Session report** — sets completed, mean set edge, residual PnL vs paired PnL
- [ ] **Optional public-wallet watcher** — read-only poll of a configured address (e.g. research target) into leaderboard/compare tools — no auto-copy without `COPY_TRADING_ENABLED`

---

## Medium term (v0.6)

- [ ] **MCP tools** — read-only status / safety model for AI clients
- [ ] **Real historical snapshot capture worker** — JSONL books for backtest + ML (stop relying on synthetic-only data)
- [ ] **Automated tests for dashboard** (`src/`, `supabase/`)
- [ ] **Shadow mode** — live signals, paper size; parity report paper vs would-be live
- [ ] **Maker rebate / fee-aware edge** — net edge after fees and estimated maker rebate
- [ ] **Multi-level quotes + inventory reservation price** (Avellaneda-style skew documented in code comments)

## Longer term

- [ ] Adaptive arb / set-cost threshold by volatility regime
- [ ] Multi-process or multi-region coordination (optional)
- [ ] Hedged Polymarket↔Kalshi only after both execution clients + joint risk limits exist

---

## Explicit non-goals

- Guaranteed profit or “copy hot-garbage / bosona / GROK_001”
- Treating viral terminal screenshots as verified live performance
- 100% win-rate marketing metrics
- Full browser UI as the primary execution path
- Running the trading loop on Vercel serverless
- Blind copy-trading of Telegram/GitHub “bot packs” (supply-chain risk)
- Labeling Kalshi gap signals as risk-free arb before dual-leg execution exists

---

## Deployment targets

| Platform | Role | Status |
|----------|------|--------|
| **Fly.io** | Primary long-running worker | Config ready (`fly.toml`) |
| **Railway** | Worker alternative | Config ready (`railway.toml`) |
| **Render** | Worker alternative | Blueprint ready (`render.yaml`) |
| **Docker** | Any host / K8s | `Dockerfile` |
| **Vercel** | Static / dashboard only | `vercel.json` + `public/` |
| **Lovable** | Dashboard experiments only | Not a worker host |

---

## Suggested milestone tags

| Tag | Theme |
|-----|--------|
| **v0.5.0** | Inventory model + complete-set accumulator + second-side lag + set-cost metrics |
| **v0.5.1** | CTF split/merge/redeem (live-gated) |
| **v0.5.2** | PriceFeed→fair value, thin-book reject, fill ledger fields |
| **v0.6.0** | WS books, shadow mode, snapshot capture, dashboard↔worker clarity |

---

Contributions and issues: open on [github.com/gepappas98/polymarket-quant-bot](https://github.com/gepappas98/polymarket-quant-bot).
