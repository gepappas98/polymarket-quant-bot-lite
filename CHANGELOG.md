# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- **P1-6 duplicate module cleanup** — canonical imports are guarded against regressions; legacy `bot.bot_config`, `bot.bot_strategy`, and `bot.bot_inventory` paths remain absent.
- **P1-7 strategy attribution** — inventory updates preserve arb metadata, ledger fills are tagged `arb` or `directional`, and session summaries expose per-strategy fill counts and volume.
- **P0-1 paper honesty** — paper fills now use the stable `SIMULATED_FILL` marker while preserving the original strategy reason in ledger metadata.
- **P0-2 pair lifecycle tracking** — arb legs share a generated `set_id`, preserve `is_arb_leg` through inventory accounting, and emit confirmed pair lifecycle ledger states; the full pair/strategy regression set is green.
- **P0-1 live fill reconciliation** — live orders now poll terminal CLOB status, cancel timed-out orders, and update inventory/ledger only from confirmed full or partial fills.
- **P0-3 swarm boundary** — deterministic `ARB` and `SECOND_SIDE` intents now bypass soft swarm consensus while directional intents remain filtered.
- **P1-5 MarketState hygiene** — optional `fair_up_prob` is read safely with `getattr`, preserving compatibility with partial state adapters and test doubles; required and optional fields are documented in `STRATEGY.md`.
- **P0-2 pair policy** — deterministic second-side recovery and same-window duplicate blocking are now documented and covered by the strategy pipeline contract.
- **Roadmap realigned (v0.5 direction)** — `ROADMAP.md` now prioritizes inventory economics observed on high-volume public Up/Down makers (e.g. complete-set accumulation, paired vs residual inventory, second-side lag, hold-to-resolution bias, CTF split/merge/redeem), while keeping existing v0.4 risk-engine and dashboard work as shipped baseline.
- Documented research context: public trader analytics (e.g. `@hot-garbage`) inform **product priorities**; viral “Grok terminal” UIs are treated as unverified/simulated unless a wallet is independently confirmed — not as performance targets.
- Explicit non-goals extended: no guaranteed profit, no 100% win-rate marketing metrics, no blind copy of Telegram/GitHub bot packs.

### Added
- `bot/inventory.py` — per-market paired/residual inventory, average complete-set cost, edge-per-set, second-side lag helpers
- Core strategy paths: `SECOND_SIDE`, staggered `SET_ACCUM`, instant `ARB` pair (priority order)
- Config: `TARGET_SET_COST`, `SECOND_SIDE_LAG_SEC`, `MAX_NAKED_RESIDUAL_USD`, `RESIDUAL_SIZE_FACTOR`, `MIN_BOOK_DEPTH_USD`
- Tests: `tests/test_inventory.py`


### Added (roadmap continuation)
- Spot fair value: `PriceFeed.anchor_window` / `window_delta_pct`, `MarketState.fair_up_prob`; strategy blends with book edge (`USE_SPOT_FAIR`, `SPOT_FAIR_WEIGHT`)
- `bot/ctf_ops.py` — paper split/merge/redeem skeleton; live fails closed until relayer integration
- `HOLD_TO_RESOLUTION` config flag (core strategy remains BUY-oriented)
- Tests: `tests/test_spot_fair_and_ctf.py`


### Added (swarm)
- `bot/swarm.py` — non-LLM module consensus (TIDAL/NORO/ZEPHR/OKAPI/RUNE/VESKA/MARIN/LUMEN)
- Config: `SWARM_ENABLED`, `CONSENSUS_THRESHOLD`
- Strategy filters intents through swarm; RUNE veto blocks the batch
- Tests: `tests/test_swarm.py`

### Added (ledger / status)
- Ledger `meta.swarm` + unique `meta.set_id` on intents/fills
- `/status` includes `swarm` agents snapshot and ledger rows with setId/consensus
- Tests: `tests/test_ledger_swarm_status.py`

### Planned (see `ROADMAP.md`)
- Live-gated CTF split / merge / redeem; on-chain redeem after resolve
- Maker-first multi-level quote ladder; richer fill ledger (`set_id`, maker/taker)
- Wire `PriceFeed` (Binance/ccxt) into strategy fair value
- Worker ↔ dashboard dual-implementation clarity; injectable clock for faithful backtests

---

## [0.4.7] — 2026-09-02

### Added
- PostgreSQL app-database setup guide at `docs/app-database-postgres.md`.
- Compatibility tests verifying `postgresql+psycopg://...` engine configuration and preserving SQLite-specific in-memory/thread options.
- Explicit optional `psycopg[binary]` driver guidance for `APP_DATABASE_URL`.

### Changed
- Documented the deployment checklist, secret handling and schema initialization behavior for the FastAPI app database.
- Marked PostgreSQL app-database support as completed in `ROADMAP.md`, while clearly distinguishing local compatibility tests from live database verification.

## [0.4.6] — 2026-09-02

### Added
- Explicit regression coverage for the authentication boundary on every mutating `/api/*` route: risk updates, trailing-stop simulation, strategy updates, leaderboard refresh, ML retraining, trade placement and price updates.

### Security
- Confirmed that all mutating sidecar routes use the shared `require_api_token` dependency.
- Confirmed that missing `API_TOKEN` remains fail-closed in live mode and returns the existing `503 API_TOKEN required in live mode` response.
- Confirmed that valid `Authorization: Bearer ...` credentials continue to allow authenticated settings/strategy changes.

## [0.4.5] — 2026-09-02

### Added
- Public CLOB midpoint adapter for `GET https://clob.polymarket.com/midpoint?token_id=...`.
- Optional FastAPI sidecar poller controlled by `CLOB_PRICE_FEED_ENABLED` and `CLOB_PRICE_FEED_INTERVAL_SECONDS`.
- Open-position routing that supplies valid midpoint prices to the existing `process_price_update()` and trailing-stop execution path.
- Regression coverage for midpoint normalization, invalid-price rejection, missing-price fail-soft behavior and open-trade updates.

### Safety
- The feed is disabled by default and only supplies market prices; it does not bypass risk gates or change paper/live execution semantics.
- Each polling cycle uses a fresh database session, ignores invalid/unavailable prices, isolates failures per trade and cancels cleanly during API shutdown.

## [0.4.4] — 2026-09-02

### Added
- Public `GET https://data-api.polymarket.com/closed-positions` adapter for normalized realized-PnL observations per leaderboard wallet.
- Bounded, configurable leaderboard-history enrichment: `LEADERBOARD_ENRICH_HISTORY`, `LEADERBOARD_HISTORY_TRADER_LIMIT` (default `20`) and `LEADERBOARD_HISTORY_POSITION_LIMIT` (default `25`).
- Regression coverage for closed-position normalization, public-API parameter clamping, fail-soft wallet-level fallback, chronological drawdown, and enrichment opt-out.
- `docs/polymarket-closed-positions-api.md`, recording the supported public data contract used by the adapter.

### Changed
- Official leaderboard refresh now replaces aggregate PnL/volume snapshots with public closed-position observations for the configured number of leading wallets, yielding stronger Sharpe, win-rate, ROI and drawdown estimates.
- A failed, empty or malformed per-wallet history request preserves the original aggregate row; the refresh remains free of synthetic traders and continues for all other wallets.
- The legacy `LEADERBOARD_SOURCE_URL` mapping override still takes precedence and intentionally skips public enrichment to preserve its established contract.

## [0.4.3] — 2026-09-02

### Added
- Public Polymarket Data API adapter at `GET https://data-api.polymarket.com/v1/leaderboard`.
- Configurable leaderboard category, time period, ordering, pagination, and timeout settings.
- Defensive normalization for decimal-string PnL/volume values and both `proxyWallet` and `wallet` response fields.
- Regression coverage for API normalization, parameter clamping, malformed responses, and scoring integration.

### Changed
- Leaderboard refresh now prefers the official public API when no legacy custom source override is configured.
- Removed synthetic mock traders from the production fallback path; API failures fall back to the local closed-trade ledger only.
- Documented the new settings in `.env.example`; `LEADERBOARD_SOURCE_URL` remains available for compatibility.

## [0.4.2] — 2026-09-02

### Added
- Persisted `Trade.token_id` and `Trade.current_price` support for position exits.
- `POST /api/trades/price`, an authenticated price-update endpoint that evaluates the configured trailing-stop threshold.
- Automatic SELL intents through the existing paper/live executor when a trailing stop is reached.
- Close-event persistence and WebSocket broadcast with realized PnL.
- Regression tests for held positions, trailing-stop closes, token propagation, and realized PnL.

### Safety
- The close path reuses the existing execution abstraction, so `MODE=paper` remains simulated and live execution still requires the existing double opt-in.
- A failed close fill leaves the position open and records no realized PnL.

## [0.4.1] — 2026-09-02

### Changed
- Added `python-dotenv` to the base requirements because `bot/config.py` loads `.env` configuration at startup.
- Added `pythonpath = .` to `pytest.ini` so the documented `pytest` command imports the `app` and `bot` packages from a clean checkout without requiring `PYTHONPATH`.
- Re-verified the v0.4.0 advanced-risk scope: variance-capped Kelly sizing, Hampel filtering, composite leaderboard, category-aware strategies, circuit-breaker/time-window/trailing-stop gates, API routes, and dashboard pages remain integrated without changing the paper/live execution boundary.

## [0.4.0] — 2026-09-01

### Added

**Advanced risk engine API (`app/`, FastAPI sidecar over `bot/`)**
- `app/main.py` — FastAPI app (`uvicorn app.main:app`, `API_PORT`) with
  `/health`, `/api/*` routes and a `/api/ws` WebSocket that broadcasts
  `position_opened` and `circuit_breaker` events
- SQLite persistence (`APP_DATABASE_URL`, default `data/app.db`) via
  SQLAlchemy — `RiskConfig`, `Leader`, `Trade`, `StrategyConfig` models;
  `init_db()` creates tables and adds missing columns in place (lightweight
  migration)
- `app/ledger/reader.py` — reads the worker ledger (`data/trades.jsonl`, or
  the in-process ledger) as the primary history source: daily PnL, per-category
  outcomes, merged fill/outcome trade history

**New services**
- `sizing_service.calculate_kelly_size()` — Variance-Capped Kelly: fractional
  Kelly scaled by `k_value`, damped by the rolling variance of the last 20
  category outcomes, capped by `max_position_pct` and `MAX_ORDER_USD`;
  returns `suggested_amount` (USDC) and `f_value` (%)
- `scoring_service` — composite leaderboard: Hampel filter (MAD, threshold
  3.5) on Sharpe/ROI across traders, composite score from Sharpe, ROI,
  win-rate, drawdown and stability; `refresh_leaderboard()` upserts `Leader`
  rows from `LEADERBOARD_SOURCE_URL` or the own ledger + deterministic mock
  traders
- `strategy_service.should_ignore_market()` — category-aware filter
  (politics-only, sports fade, crypto focus) with persisted flags
- `preprocessing_service.clean_price_series()` — Hampel outlier handler,
  called by `ml_service.retrain_model()` on every feature column before
  XGBoost training
- `risk_service` — `check_circuit_breaker()`, `check_time_window()` (supports
  overnight windows), `simulate_trailing_stop()` (5 % adverse move default),
  per-category exposure ceilings, all combined in `evaluate_safety_gates()`
  together with the existing bot gates (daily kill switch, max drawdown,
  live double opt-in)
- `trading_service.place_order()` — strategy filter → safety gates → Kelly
  sizing → the **existing** `bot.executor` (paper/live decided by `MODE`
  exactly as before) → `Trade` row + WebSocket broadcast
- `celery_tasks` — leaderboard refresh / ML retrain / health jobs run via
  Celery when `CELERY_BROKER_URL` is set, otherwise FastAPI `BackgroundTasks`

**Endpoints**
- `GET /api/status`, `GET /api/risk`, `POST /api/risk/update`,
  `GET /api/risk/gates`, `POST /api/risk/trailing-stop`,
  `POST /api/sizing/calculate`, `GET /api/leaders`, `POST /api/leaders/refresh`,
  `GET /api/trades/history`, `POST /api/trades/place`, `GET|POST /api/strategies`,
  `POST /api/ml/retrain`

**Worker integration (opt-in, default off)**
- `bot/gates.py` gained `register_check()`; `gate_intent()` runs registered
  extra checks after the built-in ones. With `RISK_ENGINE_ENABLED=true` the
  worker installs the risk-engine hook (circuit breaker, time window, category
  ceilings) — fail-closed if the engine errors. Default behaviour is unchanged.

**Dashboard**
- New pages: `/leaders` (composite leaderboard + refresh), `/sizing`
  (k / max-position sliders with live `f` preview against the API and a local
  estimate), `/strategies` (category toggles), `/settings` (risk config form:
  daily loss limit, cooldown, time window, category ceilings, trailing stop)
- Control Room: "Simulate trade" widget (sizing + circuit-breaker / time-window
  status) and `GatesPanel` extended with time window, trailing stops and
  per-category exposure — existing gate rows untouched
- `src/lib/riskApi.ts` typed client (`VITE_API_URL`), shared `NavLinks`

### Changed
- `requirements.txt`: `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `httpx`
  are now base dependencies; `celery` stays optional
- Tests: expanded coverage for sizing, scoring, strategy, risk, ML and API

## [0.3.0] — 2026-09-01

### Added

**Strategy plugin architecture**
- Dynamic strategy loader (`bot/strategies/loader.py`): any module in
  `bot/strategies/` exposing `build(shared_strategy)` is auto-discovered and
  registered, gated by its own `STRATEGY_ENABLED_ENV` — adding or removing a
  strategy no longer requires editing `bot/main.py`
- Core arb/directional strategy wrapped as a loader-compatible plugin
  (`bot/strategies/arbitrage.py`)

**New strategies (all off by default)**
- **Market making** (`bot/strategies/market_making.py`, `MM_ENABLED`) —
  two-sided quoting around fair value with inventory skew
- **Copy trading** (`bot/strategies/copy_trading.py`, `COPY_TRADING_ENABLED`)
  — replicates tracked wallets' Polymarket buys via the public Data API, with
  a size multiplier and minimum trade-size filter
- **ML directional** (`bot/strategies/ml_directional.py`,
  `ML_STRATEGY_ENABLED`) — XGBoost win-probability model (`bot/ml_model.py`)
  trained from settled outcomes, sized with fractional Kelly; falls back to
  producing no intents if no trained model is present
- **Cross-venue signal** (`bot/strategies/cross_platform_arbitrage.py`,
  `KALSHI_ARB_ENABLED`) — detects Polymarket vs. Kalshi price gaps via a
  RSA-PSS–signed Kalshi REST client (`bot/venues/kalshi_client.py`); executes
  only the Polymarket leg (directional, not hedged — see Known Gaps in
  `README.md`)

**Risk & sizing**
- Fractional Kelly Criterion position sizing (`bot/kelly.py`), shared by the
  ML strategy and available to any future strategy
- Daily-loss kill switch now **persists across process restarts** within the
  same UTC day (`bot/daily_limit.py`, `DAILY_LIMIT_STATE_PATH`) — previously
  a restart during a losing day would silently reset the counter
- `bot/executor.py` and `bot/resolver.py` wired to the persisted daily limit
  alongside the existing session-level `max_drawdown_gate`

**Backtesting**
- `bot/backtest.py` replays historical order-book snapshots (JSONL) through
  the full enabled strategy stack with no network access; `python -m
  bot.backtest <snapshots.jsonl>` CLI entry point
- `bot.ml_model.build_training_set()` derives labeled training examples
  directly from backtest snapshots for the ML strategy above

**Storage**
- Optional PostgreSQL-backed ledger (`bot/ledger_pg.py`,
  `LEDGER_BACKEND=postgres` + `DATABASE_URL`) as a drop-in replacement for
  the JSONL ledger, with the same public interface; falls back to JSONL with
  a logged error if the driver or `DATABASE_URL` is missing

**Monitoring**
- `bot/metrics.py`: `prometheus_client`-based `/metrics` exporter on its own
  port (`PROMETHEUS_PORT`) — intents, blocked intents by reason, fills, fill
  USD notional, settled outcomes, daily PnL, and kill-switch state
- `deploy/`: Prometheus + Grafana Docker Compose stack
  (`docker-compose.monitoring.yml`, scrape config, provisioned datasource and
  dashboard)

**Dashboard (Supabase/TanStack track)**
- In-browser market-making panel (`useMarketMaker`, Binance WebSocket-driven
  simulation), copy-trading panel with wallet watchlists, Kelly sizing slider,
  cooldown timer, strategy manager for plugin params, in-browser backtester
  with equity-curve charting, and threshold-based alerting with a scheduled
  `POST /api/public/hooks/monitor-alerts` route
- Supabase schema: `mm_trades`, `copy_watchlist`, `copy_trades`,
  `cooldown_state`, `strategy_config`, `backtest_results`, `alert_config`,
  `alert_history`, `historical_winrate`, `historical_candles` — all
  row-level-security scoped to `auth.uid()` except the shared reference table
- `docs/FEATURES.md` — spec-to-implementation mapping for the above

**Configuration**
- `.env.example` documents every v0.3.0 plugin's env vars (market making,
  copy trading, ML directional, cross-venue signal, persisted daily limit,
  PostgreSQL ledger, Prometheus exporter), each off by default
- `requirements.txt` lists the optional dependencies for those plugins
  (`xgboost`, `cryptography`, `prometheus-client`, `psycopg[binary]` +
  `psycopg_pool`) as commented-out entries, so the base install stays
  lightweight for anyone only using the core strategy

### Changed
- `bot/main.py` now builds its strategy registry via
  `strategies.loader.load_all()` instead of hardcoded instantiation
- `bot/ledger.py` gained a `_build_ledger()` factory selecting JSONL vs.
  PostgreSQL at import time based on `LEDGER_BACKEND`

### Known gaps (see `README.md` for detail)
- Cross-venue signal is directional only, not a hedged arbitrage
- PostgreSQL ledger backend has not been exercised against a live database
- The Python `bot/strategies/*` implementations and the dashboard's Supabase
  in-browser equivalents (market making, copy trading, backtesting) are
  independent and do not share state

### Testing
- Full existing `pytest` suite passes unmodified against the merged codebase

## [0.2.0] — 2026-08-29

### Added
- **Nexus-style safety layer** (inspired by crypto-whale-watch-nexus):
  - Double opt-in for live trading (`MODE=live` + `LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISK`)
  - Per-market cooldown lock (fail-closed)
  - JSONL trade ledger (`data/trades.jsonl`) for intents, fills, and blocks
  - Track-record win-rate gate for directional trades when enough outcomes exist
- Robust HTTP helper with timeout, retry, and jitter (`bot/http_util.py`)
- Session summary on shutdown (intents / blocked / fills)
- Deployment configs: `Dockerfile`, `fly.toml`, `railway.toml`, `render.yaml`, `Procfile`, `vercel.json`
- `CHANGELOG.md`, `ROADMAP.md`, `LICENSE` (MIT)
- Static `public/index.html` placeholder for Vercel / GitHub Pages

### Changed
- `create_executor` and live path require double opt-in
- Strategy applies ledger-based confidence gate to directional (not pure arb) intents
- Feeds: optional `ccxt`, hardened CLOB book parsing (dict levels)

### Security
- Secrets only via environment variables; `.env` gitignored
- Fail-closed gates when checks fail

## [0.1.0] — 2026-08-29

### Added
- Initial bosona-style Polymarket short-window crypto Up/Down bot
- Market discovery for BTC (and configurable assets) 5m / 15m windows via Gamma API
- Complete-set arb when `UP_ask + DOWN_ask ≤ ARB_THRESHOLD`
- Directional tilt + inventory rebalance logic
- Paper executor (default) and live CLOB skeleton (`py_clob_client_v2`)
- Risk limits: max order USD, max market exposure, daily loss kill-switch
- Rich terminal status table

---

[Unreleased]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.4.7...HEAD
[0.4.7]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.4.6...v0.4.7
[0.4.6]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.4.5...v0.4.6
[0.4.5]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gepappas98/polymarket-quant-bot/releases/tag/v0.1.0
