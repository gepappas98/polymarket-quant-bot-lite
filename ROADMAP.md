# Roadmap

Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

## Near term (v0.3)

- [ ] **WebSocket CLOB market channel** — lower-latency books than REST polling
- [ ] **Window open-price delta** — fair value from Chainlink/Binance vs Polymarket implied (replace lightweight imbalance signal)
- [ ] **Order lifecycle** — cancel stale limits, reconcile fills via user channel
- [x] **Auto-redeem** resolved winning positions — internal PnL bookkeeping now settles automatically via `bot/resolver.py` once Gamma reports a window's outcome (on-chain redemption for LIVE mode is still a separate, not-yet-done step)
- [x] **Structured logging** (JSON) + optional Prometheus metrics — set `LOG_FORMAT=json`; `/metrics` on the status server with `ENABLE_METRICS=true`
- [x] **Unit tests** for strategy gates, arb math, and market slug discovery — see `tests/` (`pytest`)

## Medium term (v0.4–v0.5)

- [x] **Multi-asset** defaults: ETH, SOL, XRP 5m/15m with per-asset exposure caps — `ASSETS` defaults to `BTC,ETH,SOL,XRP`; optional `MAX_MARKET_EXPOSURE_BY_ASSET` overrides per asset (falls back to the global cap)
- [ ] **Backtest harness** against historical CLOB snapshots (if available)
- [x] **Max drawdown + low-profit pair locks** (Nexus-style portfolio protections) — `bot/portfolio_gates.py`; also fixed a pre-existing bug where the daily-loss kill switch read a counter that was never updated
- [x] **Dashboard** — React/TanStack dashboard (`polymarket-quant-bot-lite-main`, Lovable/Vercel) + `bot/status_server.py` JSON bridge on the worker (Fly/Railway); not FastAPI as originally sketched, same effect
- [ ] **MCP tools** — read-only status / safety model for AI clients (like Nexus MCP)

## Longer term

- [ ] Adaptive arb threshold and edge model per volatility regime
- [ ] Maker rebate optimization and multi-level quotes
- [ ] Paper ↔ live parity checks and shadow mode (live signals, paper size)
- [ ] Multi-process / multi-region coordination (optional)

## Non-goals (for now)

- Guaranteed profit or “copy bosona”
- Full browser trading UI as the primary product
- Running the trading loop on Vercel serverless (use Fly / Railway / Render workers)

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