# Polymarket Quant Bot

**Short-window crypto Up/Down trading framework for [Polymarket](https://polymarket.com).**
A Python trading worker with arbitrage, market-making, copy-trading, ML and
cross-venue signal strategies behind a fail-closed risk layer — plus a
React/TanStack + Supabase dashboard for monitoring, in-browser backtesting,
and alerting.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-82%20passing-brightgreen.svg)](tests/)

> **Educational software. Not financial advice.** Trading prediction markets carries
> substantial risk of loss. Past performance does not guarantee future results.
> Always paper trade first and never risk money you cannot afford to lose.

Repository: [github.com/gepappas98/polymarket-quant-bot](https://github.com/gepappas98/polymarket-quant-bot)

---

## Table of contents

- [Overview](#overview)
- [Features](#features)
- [Quick start](#quick-start)
- [Live trading](#live-trading-real-money)
- [Strategy plugins](#strategy-plugins)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Backtesting](#backtesting)
- [Monitoring](#monitoring)
- [Testing](#testing)
- [Dashboard](#dashboard)
- [Project layout](#project-layout)
- [Deployment](#deployment)
- [Safety model](#safety-model)
- [Known gaps](#known-gaps)
- [Disclaimer](#disclaimer)
- [License](#license)

---

## Overview

The bot polls Polymarket's Gamma API for active short-window (5m / 15m) Up/Down
crypto markets and runs a set of pluggable strategies — complete-set
arbitrage, directional tilt, market-making, copy-trading, an XGBoost
probability model, and a cross-venue (Kalshi) signal — through one shared,
fail-closed risk layer. Paper mode is the default; live trading requires an
explicit double opt-in. Every intent, fill, block, and settled outcome is
written to an append-only ledger (JSONL or PostgreSQL).

A separate React/TanStack dashboard, backed by Supabase, gives a browser-based
view for monitoring, an in-browser backtester, copy-trading watchlists, and
threshold-based alerting. It talks to its own Supabase tables and is
independent of the Python worker's own ledger — see [Architecture](#architecture)
for how the two relate.

## Features

| Area | What it does |
|------|----------------|
| **Market discovery** | Finds live Up/Down markets for configurable assets and windows via the Gamma API |
| **Complete-set arbitrage** | Buys both sides when `UP_ask + DOWN_ask ≤ ARB_THRESHOLD` |
| **Directional + inventory management** | Book-imbalance edge tilt; rebalances the underrepresented side |
| **Market making** | Two-sided quoting around fair value with inventory skew (`bot/strategies/market_making.py`) |
| **Copy trading** | Replicates tracked wallets' Polymarket buys with a size multiplier (`bot/strategies/copy_trading.py`) |
| **Kelly sizing** | Fractional Kelly position sizing shared by the ML and directional paths (`bot/kelly.py`) |
| **Plugin architecture** | Drop a file in `bot/strategies/` with a `build()` function and it's auto-loaded — no core edits (`bot/strategies/loader.py`) |
| **Backtesting** | Replays historical order-book snapshots through the live strategy stack (`bot/backtest.py`) |
| **ML ensemble** | XGBoost win-probability model trained from settled outcomes, feeding Kelly sizing (`bot/ml_model.py`) |
| **Cross-venue signal** | Polymarket vs. Kalshi price-gap detection — directional, not hedged (`bot/strategies/cross_platform_arbitrage.py`) — see [Known gaps](#known-gaps) |
| **PostgreSQL ledger** | Optional drop-in swap for the JSONL ledger (`bot/ledger_pg.py`, `LEDGER_BACKEND=postgres`) |
| **Prometheus metrics** | `/metrics` HTTP exporter + Grafana dashboard under `deploy/` (`bot/metrics.py`) |
| **Paper mode (default)** | Deterministic, optimistic-fill simulation — no funds at risk |
| **Live mode** | Double opt-in (`MODE=live` + `LIVE_TRADING_CONFIRM`) + CLOB client |
| **Safety gates** | Per-market cooldown, size/exposure caps, daily-loss kill switch (persisted across restarts), max-drawdown and low-profit pair locks, own-track-record gate |
| **Dashboard** | React/TanStack + Supabase: market-making panel, copy-trading panel, Kelly slider, cooldown timer, strategy manager, in-browser backtester, alert config — see [Dashboard](#dashboard) |

---

## Quick start

```bash
git clone https://github.com/gepappas98/polymarket-quant-bot.git
cd polymarket-quant-bot

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
python -m bot.main
```

The bot starts in **paper mode** with only the core arbitrage/directional
strategy active — every other plugin (market making, copy trading, ML,
cross-venue) is off until you set its `_ENABLED` flag. See
[Strategy plugins](#strategy-plugins).

## Live trading (real money)

Only enable this after extended paper testing and a review of the
[safety model](#safety-model) below.

```bash
# .env
MODE=live
LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISK
POLYMARKET_PRIVATE_KEY=0x...
```

```bash
pip install py_clob_client_v2
```

Fund the wallet with **pUSD** (and a small amount of POL for gas if trading
from an EOA). Both env flags above must be present and exactly correct, or
`bot/gates.py::is_live_trading_allowed()` fails closed and the bot stays in
paper mode.

---

## Strategy plugins

Every strategy under `bot/strategies/` is discovered automatically by
`bot/strategies/loader.py`. Each one is off by default and toggled by its own
env flag, so enabling a strategy is a one-line `.env` change and requires no
code edits:

| Plugin | File | Enable with |
|--------|------|--------------|
| Arbitrage + directional (core) | `arbitrage.py` | always on |
| Market making | `market_making.py` | `MM_ENABLED=true` |
| Copy trading | `copy_trading.py` | `COPY_TRADING_ENABLED=true` |
| ML directional (XGBoost + Kelly) | `ml_directional.py` | `ML_STRATEGY_ENABLED=true` (requires a trained model, see [Backtesting](#backtesting)) |
| Cross-venue signal (Kalshi) | `cross_platform_arbitrage.py` | `KALSHI_ARB_ENABLED=true` (requires Kalshi API credentials) |

To add a new strategy: create `bot/strategies/my_strategy.py` exposing
`build(shared_strategy)` (and, optionally, `STRATEGY_ENABLED_ENV`). To remove
one, delete the file. `bot/main.py` never needs to change.

---

## Configuration

Full reference lives in `.env.example`; the table below covers the variables
you're most likely to tune. Every plugin-specific variable is documented in
its own module's docstring.

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `paper` | `paper` or `live` |
| `LIVE_TRADING_CONFIRM` | — | Must be exactly `I_UNDERSTAND_THE_RISK` for live |
| `POLYMARKET_PRIVATE_KEY` | — | EOA/proxy private key, live mode only |
| `ASSETS` | `BTC` (`.env.example`); code default `BTC,ETH,SOL,XRP` if unset | Comma-separated |
| `WINDOWS` | `5,15` | Minutes |
| `MAX_ORDER_USD` | `25` | Per-order cap |
| `MAX_MARKET_EXPOSURE_USD` | `150` | Per-market total cost cap (fallback) |
| `ARB_THRESHOLD` | `0.985` | Buy both sides when `sum_asks ≤` this |
| `MIN_DIRECTIONAL_EDGE` | `0.03` | Minimum heuristic edge before a directional trade fires |
| `PREFER_MAKER` | `true` | Shade directional limit price one tick for a maker-ish fill |
| `COOLDOWN_MINUTES` | `3` | Per-market admission cooldown |
| `DAILY_LOSS_LIMIT_USD` | `-200` | Session drawdown kill switch (also the max-drawdown limit) |
| `MIN_TRACK_RECORD_WIN_PCT` / `_SAMPLES` | `48` / `12` | Directional gate floor and minimum sample size |
| `PAIR_LOCK_LOOKBACK` / `_LOSS_THRESHOLD_USD` / `_MINUTES` | `5` / `0` / `30` | Low-profit pair lock (Nexus-style) |
| `HTTP_TIMEOUT` / `HTTP_RETRIES` | `6` / `3` | Network resilience for Gamma/CLOB calls |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `text` | `LOG_FORMAT=json` for structured logs |
| `STATUS_PORT` | — | Enables `bot/status_server.py` (JSON status API for the dashboard) |
| `ENABLE_METRICS` | `false` | Legacy hand-rolled `GET /metrics` on the status server (no dependency) |

**Also in `.env.example`** — every plugin above (market making, copy
trading, ML directional, cross-venue signal), plus the PostgreSQL ledger and
Prometheus exporter, has its full set of env vars documented there with
inline comments — see the "STRATEGY PLUGINS" section.

---

## Architecture

```
bot/
├── main.py                 # cycle loop: discover → evaluate (plugins) → execute → resolve
├── config.py                # env-driven Config dataclass, single source of truth
├── market_finder.py         # Gamma API market discovery
├── feeds.py                  # CLOB order book fetch + MarketState
├── strategy.py                # arb pairing + directional tilt + inventory tracking (core)
├── kelly.py                    # fractional Kelly position sizing
├── ml_model.py                  # XGBoost win-probability model, train/save/load
├── strategies/
│   ├── loader.py                 # dynamic plugin discovery
│   ├── arbitrage.py               # wraps strategy.py for the loader
│   ├── market_making.py
│   ├── copy_trading.py
│   ├── ml_directional.py
│   └── cross_platform_arbitrage.py
├── venues/kalshi_client.py         # RSA-PSS signed Kalshi REST client
├── gates.py                          # cooldown + live-trading double opt-in (fail-closed)
├── portfolio_gates.py                 # max-drawdown and low-profit pair locks
├── daily_limit.py                      # kill switch persisted across restarts
├── executor.py                          # PaperExecutor / LiveExecutor
├── ledger.py / ledger_pg.py               # JSONL or PostgreSQL trade ledger
├── resolver.py                             # polls Gamma for settlement, records outcomes
├── metrics.py                               # Prometheus /metrics exporter
├── backtest.py                               # replays historical snapshots
└── status_server.py                           # JSON status API + legacy /metrics
```

Each cycle: `market_finder` discovers active windows → `feeds.MarketState`
pulls order books → `strategies/loader.load_all()` runs every enabled plugin's
`evaluate()` and merges their `Intent`s → `executor` runs them through
`gates`/`portfolio_gates`/`daily_limit` and the ledger → `resolver` settles
closed windows and updates the daily PnL used by the kill switch.

**Two independent systems share this repository:**

1. **`bot/`** — the Python trading worker described above. This is what
   actually places (paper or live) orders and owns the ledger of record.
2. **`src/` + `supabase/`** — a React/TanStack dashboard with its own
   Supabase-backed, in-browser paper-trading and monitoring layer
   (`useMarketMaker`, `CopyTradingPanel`, `BacktestConfig`, `AlertConfigPanel`
   — see `docs/FEATURES.md`). It talks to Supabase tables (`mm_trades`,
   `copy_trades`, `backtest_results`, `alert_history`, etc.), row-level
   security scoped per user, and a scheduled `POST /api/public/hooks/monitor-alerts`
   route for hourly alert evaluation.

The dashboard can also consume the Python worker's `GET /status` (via
`STATUS_PORT` + `BOT_STATUS_URL`) for read-only visibility, but its own
market-making/copy-trading/backtesting features run independently in the
browser against Supabase — they do not read or write `bot/`'s ledger. If
you're deciding where to add a new trading feature, `bot/` is the one place
that can place real orders; `src/` is presentation and a separate in-browser
simulation.

---

## Backtesting

```bash
python -m bot.backtest path/to/snapshots.jsonl
```

Runs the full enabled strategy stack against historical order-book snapshots,
with a simplified, time-independent risk model (cooldown and the drawdown
kill switch are wall-clock based in production and are not faithfully
reproduced in a fast-forwarded backtest — see the module docstring).

To train the ML model:

```python
from bot.backtest import load_snapshots
from bot.ml_model import build_training_set, ProbabilityModel

snapshots = load_snapshots("data/historical_snapshots.jsonl")
X, y = build_training_set(snapshots)
model = ProbabilityModel()
model.train(X, y)
model.save()  # -> data/ml_model.json (ML_MODEL_PATH)
```

Model quality depends entirely on how many real settled markets you feed it —
treat anything trained on fewer than a few hundred samples as unproven.

---

## Monitoring

Two, independent metrics surfaces exist — pick one, or run both:

- **`ENABLE_METRICS=true`** — a hand-rolled `GET /metrics` on the existing
  `STATUS_PORT` status server. No extra dependency.
- **`bot/metrics.py`** — a fuller `prometheus_client`-based exporter on its
  own port (`PROMETHEUS_PORT`, default `9108`): intents, blocks (by reason),
  fills, fill USD notional, outcomes, daily PnL, and kill-switch state.
  Pairs with `deploy/docker-compose.monitoring.yml` (Prometheus + Grafana,
  dashboard auto-provisioned from `deploy/grafana-dashboard.json`).

```bash
pip install prometheus-client
docker compose -f deploy/docker-compose.monitoring.yml up -d
```

Prometheus: http://localhost:9090 · Grafana: http://localhost:3000
(`admin` / `admin` — change this before exposing the port anywhere).

---

## Testing

```bash
pytest -q
```

82 tests covering strategy/arb math, all risk gates, market-slug discovery,
portfolio protections, and logging setup — no network access required.
Frontend/Supabase code (`src/`, `supabase/`) has no automated test suite yet.

## Dashboard

`src/` is a React/TanStack dashboard (Vite, Radix UI, Tailwind, Supabase,
TanStack Query, Recharts). Run it locally with:

```bash
npm install   # or: bun install
npm run dev
```

It can point at a running Python worker's status API by setting
`BOT_STATUS_URL` to `https://<your-worker-host>/status`. Its own trading
panels (market making, copy trading, backtesting, alerting — see
`docs/FEATURES.md` for the full spec mapping) run against Supabase and are
independent of the worker.

---

## Project layout

```
polymarket-quant-bot/
├── bot/                  # Python trading worker (see Architecture)
├── tests/                # pytest suite for bot/
├── src/                  # React/TanStack dashboard
├── supabase/              # dashboard's own schema (migrations/) + config
├── deploy/                 # Prometheus + Grafana compose stack
├── docs/FEATURES.md         # spec-to-implementation mapping for the dashboard
├── data/                     # runtime ledger (gitignored contents)
├── public/                    # static placeholder (Vercel)
├── Dockerfile
├── fly.toml / railway.toml / render.yaml / Procfile   # worker deployment
├── vercel.json                                         # static dashboard only
├── package.json / bun.lock / vite.config.ts             # dashboard tooling
├── pytest.ini
├── CHANGELOG.md
├── ROADMAP.md
└── LICENSE
```

---

## Deployment

The Python worker is a **long-running process**, not a serverless function.

| Platform | Recommended? | Notes |
|----------|--------------|--------|
| **Fly.io** | Yes | `fly.toml` |
| **Railway** | Yes | `railway.toml` + Dockerfile |
| **Render** | Yes | `render.yaml` worker |
| **Docker** | Yes | Any VPS / Kubernetes |
| **Vercel** | Static/dashboard only | Do **not** run the worker on serverless |
| **Lovable** | Dashboard only | Not a worker host |

### Fly.io

```bash
fly auth login
fly launch --no-deploy
fly secrets set MODE=paper
fly deploy
fly logs
```

Live example:

```bash
fly secrets set \
  MODE=live \
  LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISK \
  POLYMARKET_PRIVATE_KEY=0xYOUR_KEY
fly deploy
```

### Railway

1. New project → Deploy from GitHub.
2. Builder: Dockerfile.
3. Start command: `python -m bot.main`.
4. Set env vars in the dashboard.

### Render

Use Blueprint `render.yaml`, or create a **Background Worker** with the
provided Dockerfile.

### Docker

```bash
docker build -t polymarket-quant-bot .
docker run --rm -e MODE=paper polymarket-quant-bot
```

---

## Safety model

1. **Paper by default** — no real orders unless both live flags are set.
2. **Live requires two independent env flags** — hard to enable by accident.
3. **Cooldown** — fail-closed per-market admission lock.
4. **Size and exposure caps** — per-order, per-market, and optionally per-asset.
5. **Daily-loss kill switch, persisted across restarts** (`bot/daily_limit.py`)
   and **max-drawdown / low-profit pair locks** (`bot/portfolio_gates.py`).
6. **Track-record gate** — directional (non-arbitrage) trades require a
   minimum win rate from the bot's own settled history once enough samples
   exist.
7. **Append-only ledger** — every intent, block, fill, and outcome is
   recorded (JSONL by default, or PostgreSQL via `LEDGER_BACKEND=postgres`).
8. **All optional strategies (market making, copy trading, ML, cross-venue)
   are off by default** and share the same risk gates and inventory caps as
   the core strategy — enabling one never bypasses the limits above.

---

## Known gaps

Documented plainly rather than silently — these are the honest edges of the
current implementation:

- **Optional dependencies are commented out in `requirements.txt`.**
  `xgboost`, `cryptography`, `prometheus-client`, and `psycopg[binary]` +
  `psycopg_pool` are listed but commented — uncomment (or `pip install`) only
  the ones your enabled plugins need, per the table in `requirements.txt`.
  This is deliberate: `pip install -r requirements.txt` stays fast and
  dependency-light for anyone only using the core arb/directional strategy.
- **Cross-venue (Kalshi) signal is directional, not hedged.** It only
  executes the Polymarket leg; there is no Kalshi order-execution client yet,
  so enabling it takes on real directional risk informed by an external
  price, not risk-free arbitrage.
- **PostgreSQL ledger backend is untested against a real database** in this
  environment — the JSONL-backend fallback path (missing driver or
  `DATABASE_URL`) is verified to degrade gracefully.
- **Backtests use a simplified, time-independent risk model.** Wall-clock
  gates (cooldown, drawdown kill switch) are not faithfully replayed.
- **Two independent implementations of similar features exist** (Python
  `bot/strategies/market_making.py` vs. the dashboard's `useMarketMaker.ts`,
  for example). They are not connected — see [Architecture](#architecture).
  Consolidating them, or clearly scoping one as "simulation/monitoring only",
  is worth deciding deliberately rather than by accretion.

---

## Disclaimer

Trading prediction markets involves substantial risk of loss. This repository
is provided for **educational and research purposes only**. The authors
assume no liability for financial losses incurred through its use. Comply
with Polymarket's terms of service and applicable local law.

## License

[MIT](LICENSE) © 2026 [gepappas98](https://github.com/gepappas98)

## See also

- [CHANGELOG.md](CHANGELOG.md)
- [ROADMAP.md](ROADMAP.md)
- [docs/FEATURES.md](docs/FEATURES.md) — dashboard spec-to-implementation mapping
