# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
- Full existing `pytest` suite (82 tests) passes unmodified against the
  merged codebase

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

[0.3.0]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gepappas98/polymarket-quant-bot/releases/tag/v0.1.0