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