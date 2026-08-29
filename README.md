# Polymarket Quant Bot

**Short-window crypto Up/Down trading framework for [Polymarket](https://polymarket.com)** — bosona-style inventory/arb logic with Nexus-inspired safety gates.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)

> **Educational software.** Not financial advice. Past performance does not guarantee future results. You can lose money. Paper trade first.

Repository: [github.com/gepappas98/polymarket-quant-bot](https://github.com/gepappas98/polymarket-quant-bot)

---

## Features

| Area | What it does |
|------|----------------|
| **Markets** | Discovers live BTC (configurable) 5m / 15m Up/Down markets via Gamma API |
| **Complete-set arb** | Buys both sides when `UP_ask + DOWN_ask ≤ ARB_THRESHOLD` |
| **Directional + inventory** | Mild edge tilt; can add the opposite side and pair inventory |
| **Paper mode (default)** | Safe simulation with full ledger |
| **Live mode** | Double opt-in + CLOB client skeleton |
| **Safety** | Cooldown locks, size limits, daily loss kill-switch, track-record gate |
| **Ledger** | JSONL intents / fills / blocks under `data/` |

---

## Quick start (local)

```bash
git clone https://github.com/gepappas98/polymarket-quant-bot.git
cd polymarket-quant-bot

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
python -m bot.main
```

### Live trading (real money)

Only after thorough paper testing:

```bash
# .env
MODE=live
LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISK
POLYMARKET_PRIVATE_KEY=0x...
```

```bash
pip install py_clob_client_v2
```

Fund the wallet with **pUSD** (and a little POL for gas if using EOA).

---

## Configuration

See `.env.example`. Important variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `paper` | `paper` or `live` |
| `LIVE_TRADING_CONFIRM` | — | Must be exactly `I_UNDERSTAND_THE_RISK` for live |
| `ASSETS` | `BTC` | Comma-separated |
| `WINDOWS` | `5,15` | Minutes |
| `MAX_ORDER_USD` | `25` | Per order |
| `MAX_MARKET_EXPOSURE_USD` | `150` | Per market total |
| `ARB_THRESHOLD` | `0.985` | Buy both when sum ≤ this |
| `COOLDOWN_MINUTES` | `3` | Per-market admission cooldown |
| `MIN_TRACK_RECORD_WIN_PCT` | `48` | Directional gate floor (own ledger) |
| `DAILY_LOSS_LIMIT_USD` | `-200` | Kill switch |

---

## Project layout

```
polymarket-quant-bot/
├── bot/                  # application package
├── data/                 # runtime ledger (gitignored contents)
├── public/               # static placeholder (Vercel)
├── Dockerfile
├── fly.toml              # Fly.io
├── railway.toml          # Railway
├── render.yaml           # Render worker
├── Procfile
├── vercel.json           # static only — not the worker
├── CHANGELOG.md
├── ROADMAP.md
└── LICENSE
```

---

## Deployment

This is a **long-running worker**, not a serverless function.

| Platform | Recommended? | Notes |
|----------|--------------|--------|
| **Fly.io** | Yes | `fly.toml` |
| **Railway** | Yes | `railway.toml` + Dockerfile |
| **Render** | Yes | `render.yaml` worker |
| **Docker** | Yes | Any VPS / K8s |
| **Vercel** | Static only | Placeholder; do **not** run the bot on serverless |
| **Lovable** | UI only | Not a worker host |

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
3. Start: `python -m bot.main`.
4. Set env vars in the dashboard.

### Render

Use Blueprint `render.yaml` or create a **Background Worker** with the Dockerfile.

### Docker

```bash
docker build -t polymarket-quant-bot .
docker run --rm -e MODE=paper polymarket-quant-bot
```

### Vercel / Lovable

- **Vercel**: serves `public/index.html` only. Use for landing or a future dashboard, not the trading loop.
- **Lovable**: prototype a React dashboard that talks to a worker API later; run the bot on Fly/Railway/Render.

---

## Safety model

1. Default is **paper** — no real orders.
2. **Live requires two env flags** — hard to enable by accident.
3. **Cooldown** — per-market admission lock.
4. **Size & exposure caps**.
5. **Track-record gate** on directional trades when own outcome history is weak.
6. **Ledger** under `data/trades.jsonl`.

---

## Disclaimer

Trading prediction markets involves substantial risk of loss. This repository is for **educational and research purposes**. Authors assume no liability. Comply with Polymarket terms and local law.

---

## License

[MIT](LICENSE) © 2026 [gepappas98](https://github.com/gepappas98)

## See also

- [CHANGELOG.md](CHANGELOG.md)
- [ROADMAP.md](ROADMAP.md)
