# Roadmap

Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

## Just shipped (v0.4.7) — PostgreSQL app-database compatibility, see CHANGELOG.md

- [x] **PostgreSQL URL support** — verified that `APP_DATABASE_URL=postgresql+psycopg://...` uses native SQLAlchemy engine options without SQLite-only connection arguments.
- [x] **Driver guidance** — documented the optional `psycopg[binary]` dependency, deployment checklist and secret-handling requirements.
- [x] **Compatibility coverage** — added tests for PostgreSQL configuration and preserved SQLite in-memory/thread behavior.
- [x] **Verification boundary documented** — local tests cover URL/engine configuration; end-to-end live PostgreSQL verification remains a deployment/CI responsibility because no PostgreSQL server is bundled locally.

## Just shipped (v0.4.6) — mutating API authentication audit, see CHANGELOG.md

- [x] **Protected mutating routes** — settings/risk, strategy updates, leaderboard refresh, ML retraining, trade placement, price updates and trailing-stop mutation all require the shared `require_api_token` dependency.
- [x] **Authentication regression coverage** — unauthenticated requests are rejected consistently while Bearer-token authenticated strategy updates remain functional.
- [x] **Live-mode fail-closed behavior** — when `API_TOKEN` is missing in live mode, mutating routes return the existing explicit configuration error instead of allowing changes.

## Just shipped (v0.4.5) — CLOB price-feed integration, see CHANGELOG.md

- [x] **CLOB midpoint adapter** — reads public midpoint prices for persisted open-position token IDs from the Polymarket CLOB API.
- [x] **Trailing-stop routing** — each valid price is routed through the existing `process_price_update()` path, preserving persistence, safety gates, paper/live execution semantics and WebSocket close events.
- [x] **Optional sidecar poller** — `CLOB_PRICE_FEED_ENABLED=false` by default; when enabled, the FastAPI sidecar polls at the configured interval using a fresh database session per cycle and shuts down cleanly.
- [x] **Regression coverage** — midpoint normalization, invalid-price handling, open-trade routing and missing-price fail-soft behavior are tested.

## Just shipped (v0.4.4) — realized-PnL leaderboard enrichment, see CHANGELOG.md

- [x] **Per-trader closed-position history** — the top aggregate public leaderboard rows are enriched from Polymarket's public `/closed-positions` API, supplying realized PnL, invested notional, and timestamps for meaningful per-trader statistics.
- [x] **Fail-soft score enrichment** — a missing or failed trader-history response retains its aggregate leaderboard observation; no synthetic traders are introduced and a single failed wallet cannot fail the refresh.
- [x] **Controlled API footprint** — enrichment is configurable and bounded (`LEADERBOARD_ENRICH_HISTORY`, top-trader and per-wallet history limits), with defaults below the documented public endpoint limit.
- [x] **Regression coverage** — response normalization, parameter bounds, fail-soft fallback, chronological drawdown calculation, and the opt-out path are tested.

## Just shipped (v0.4.3) — public leaderboard adapter, see CHANGELOG.md

- [x] **Official leaderboard source** — added a public Data API adapter for `GET /v1/leaderboard` with category, period, ordering, pagination, timeout, numeric-string parsing, and wallet-field compatibility.
- [x] **No synthetic fallback traders** — API failures now fall back to the local closed-trade ledger instead of injecting mock addresses into production leaderboard results.
- [x] **Configurable source behavior** — the legacy `LEADERBOARD_SOURCE_URL` mapping override remains supported, while official API settings are documented in `.env.example`.
- [x] **Regression coverage** — adapter normalization, parameter clamping, malformed payload rejection, scoring, API, and review-fix tests pass.

## Just shipped (v0.4.2) — trailing-stop execution, see CHANGELOG.md

- [x] **Trailing-stop execution** — open trades now persist `token_id` and `current_price`; price updates evaluate the configured adverse-move threshold and submit a SELL intent through the existing paper/live executor.
- [x] **Close-event accounting** — successful exits persist closed status, exit price, realized PnL, close timestamp, and broadcast a `position_closed` WebSocket event.
- [x] **Price-update API** — authenticated `POST /api/trades/price` provides a deterministic integration point for live market-feed adapters.
- [x] **Regression coverage** — hold, close, PnL, token propagation, full backend suite, and frontend build verified.

## Just shipped (v0.4.1) — reproducibility and verification, see CHANGELOG.md

- [x] **Clean-install runtime dependencies** — `python-dotenv` is declared because configuration loading depends on it.
- [x] **Clean-checkout test execution** — `pytest.ini` sets `pythonpath = .`; the full test suite can run without a shell-specific `PYTHONPATH` export.
- [x] **v0.4.0 integration verification** — the advanced-risk backend, API contracts, safety-gate integration, and dashboard surfaces remain in place without changing paper/live execution semantics.

## Just shipped (v0.4.0) — advanced risk engine, see CHANGELOG.md

- [x] **FastAPI risk-engine sidecar** (`app/`) over the existing worker — `uvicorn app.main:app`; reads `data/trades.jsonl` as history, SQLite for `RiskConfig` / `Leader` / `Trade` / `StrategyConfig`
- [x] **Variance-Capped Kelly sizing** — `app/services/sizing_service.py`, rolling variance of the last 20 category outcomes, `k_value` / `max_position_pct` caps
- [x] **Composite leaderboard with Hampel filtering** — `app/services/scoring_service.py`, `GET /api/leaders`, `POST /api/leaders/refresh`
- [x] **Category-aware strategy flags** (politics-only, sports fade, crypto focus) — `app/services/strategy_service.py`, `/strategies` page
- [x] **Hampel preprocessing before XGBoost retraining** — `preprocessing_service.clean_price_series()` ← `ml_service.retrain_model()`
- [x] **Advanced risk gates** — circuit breaker, time window, trailing stop, per-category ceilings in `evaluate_safety_gates()`; opt-in worker hook via `RISK_ENGINE_ENABLED=true` (`bot/gates.register_check`)
- [x] **Dashboard pages** `/leaders`, `/sizing`, `/strategies`, `/settings`; Control Room "Simulate trade" widget and extended `GatesPanel`

## Near-term follow-ups (v0.4.x)

- [ ] **Turn the risk-engine hook on by default** once it has run alongside the paper worker for a while (today `RISK_ENGINE_ENABLED=false`).
- [x] **Real leaderboard source** — the public aggregate source shipped in v0.4.3 and per-trader realized-PnL enrichment shipped in v0.4.4.
- [x] **Trailing-stop execution** — the close path shipped in v0.4.2 and the optional CLOB midpoint poller now supplies live prices in v0.4.5.
- [x] **Feed live prices into `Trade.current_price`** — the sidecar poller updates open positions through the existing price-update service.
- [x] **Auth on mutating `/api/*` routes** — the shared API-token boundary protects all mutating sidecar routes; frontend callers can send `VITE_API_TOKEN` through the existing client configuration.
- [x] **Postgres for the app DB** — PostgreSQL dialect configuration, driver setup and compatibility tests are documented in v0.4.7; live-server execution remains an environment-specific CI/deployment check.

## Shipped in v0.3.0

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

## Still open from v0.3.1

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

## Medium term (v0.5)

- [ ] **MCP tools** — read-only status / safety model for AI clients (like Nexus MCP)
- [ ] **Real historical snapshot capture** — a small worker/cron that writes `bot/backtest.py`-compatible JSONL snapshots from live order books, so backtesting and ML training stop depending on hand-built synthetic data
- [ ] **Automated test coverage for the dashboard** (`src/`, `supabase/`) — currently none

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