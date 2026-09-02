# Roadmap

Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

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

## Near term (v0.4.1)

- [ ] **Turn the risk-engine hook on by default** once it has run alongside the paper worker for a while (today `RISK_ENGINE_ENABLED=false`)
- [ ] **Real leaderboard source** — `LEADERBOARD_SOURCE_URL` currently expects `{address: [{pnl,size,ts}]}`; add an adapter for the Polymarket Data API so `/api/leaders` stops relying on mock traders
- [ ] **Trailing-stop execution** — shipped in v0.4.2; remaining work is connecting the live CLOB feed adapter to `POST /api/trades/price`.
- [ ] **Feed live prices into `Trade.current_price`** — the persistence and close path are shipped; connect the production market-data stream next.
- [ ] **Auth on mutating `/api/*` routes** — settings/strategies endpoints are unauthenticated; bind them to the Supabase session used by `/settings` and `/strategies`
- [ ] **Postgres for the app DB** — `APP_DATABASE_URL` accepts any SQLAlchemy URL but only SQLite has been exercised

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