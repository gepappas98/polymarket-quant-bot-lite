# Roadmap

Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

## Near term (v0.3)

- [ ] **WebSocket CLOB market channel** — lower-latency books than REST polling
- [ ] **Window open-price delta** — fair value from Chainlink/Binance vs Polymarket implied (replace lightweight imbalance signal)
- [ ] **Order lifecycle** — cancel stale limits, reconcile fills via user channel
- [ ] **Auto-redeem** resolved winning positions
- [ ] **Structured logging** (JSON) + optional Prometheus metrics
- [ ] **Unit tests** for strategy gates, arb math, and market slug discovery

## Medium term (v0.4–v0.5)

- [ ] **Multi-asset** defaults: ETH, SOL, XRP 5m/15m with per-asset exposure caps
- [ ] **Backtest harness** against historical CLOB snapshots (if available)
- [ ] **Max drawdown + low-profit pair locks** (Nexus-style portfolio protections)
- [ ] **Dashboard** (optional): small FastAPI/React status UI deployable on Vercel + worker on Fly
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