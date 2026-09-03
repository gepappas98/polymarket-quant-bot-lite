# Roadmap

Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

**Audit snapshot (static + runtime on `polymarket-quant-bot-lite`):** ~6.2/10 as a framework at audit time; **rising as P0 lands**. Strong gates/ledger/architecture. Still **not** full real-money ready until remaining P0-1 paper labels, P0-2 pair timeout policy, and **P0-4 realistic fills** are done. Do **not** treat paper/backtest PnL as proof of edge until P0-4.

External references that shaped priorities (research only — not affiliations):

- Public trader **@hot-garbage** (`0x3139…9e2e`): complete-set accumulation + residual directional + inventory rebalance (~50–55% event win rate).
- Viral “GROK / GROKTOPUS” and cinematic terminals: treat as **simulated / marketing UI** unless a wallet is independently verified.

---

## Just shipped (reference)

### v0.4.x — risk engine & dashboard

- [x] FastAPI risk-engine sidecar (`app/`), Kelly, leaderboard adapter, trailing-stop path, auth on mutating routes (when `API_TOKEN` set)
- [x] Plugin strategies (MM, copy, ML, cross-venue **signal**), gates, kill switch, Prometheus hooks
- [x] React control room (Monitor / Desk / Leaders / Sizing / Strategies / Settings)
- [x] Analytics dashboard refresh: status bar, live metric cards, market snapshot, SHAP, volatility, and RSI views

### v0.5.0 — inventory & swarm (worker)

- [x] `bot/inventory.py` — paired / residual / avg_set_cost / second-side lag
- [x] Complete-set accumulator + SECOND_SIDE + spot fair blend (`USE_SPOT_FAIR`)
- [x] `bot/ctf_ops.py` — paper-safe split/merge/redeem skeleton (live fail-closed)
- [x] `bot/swarm.py` — non-LLM module consensus (TIDAL…LUMEN)
- [x] Ledger `meta.swarm` / `set_id`; `/status` swarm block
- [x] Deploy docs: `fly.risk.toml`, `Dockerfile.risk` (Leaders API ≠ worker)

### v0.5.1 — hygiene & arb path (partial → complete)

- [x] **P0-3** Swarm bypass for deterministic ARB / SECOND_SIDE (`is_arb_leg` / reason)
- [x] Regression: both-sides ARB test passes with `SWARM_ENABLED=true`
- [x] **P1-5** `getattr(state, "fair_up_prob", None)` (no AttributeError on mocks)
- [ ] Document MarketState required vs optional fields
- [ ] Full `pytest` green on clean checkout
- [ ] Delete unused `bot/bot_config.py`, `bot/bot_strategy.py`, `bot/bot_inventory.py`
- [ ] Grep CI: no `bot_strategy` / `bot_inventory` / `bot_config` imports

### v0.5.2 — fill reconciliation & pairs (in progress)

- [x] **P0-1 (core):** order id + requested vs filled; poll to terminal state; inventory/ledger only on confirmed fills; never `filled` on submit alone
- [ ] **P0-1 (paper honesty):** paper fills labeled `SIMULATED_FILL`; excluded from “proven edge” reports
- [x] **P0-2 (core):** `ArbPair` states `PAIR_PENDING | PAIR_PARTIAL | PAIR_COMPLETE | PAIR_FAILED`; `set_id` through executor; `is_arb_leg` not forced false
- [ ] **P0-2 (policy):** on `PAIR_PARTIAL` — active second-side / reduce / timeout
- [ ] Optional: reject new independent arb while pair incomplete on same window
- [ ] **P1-7:** `update_inventory(..., is_arb_leg=intent.is_arb_leg)` + arb vs directional PnL attribution (if not fully wired)

---

## CRITICAL — remaining v0.5 overhaul

> Prefer **paper** until P0-2 policy + P0-4 are done. Live only with tiny size after P0-1 verified against real CLOB fill reports.

### P0-4 — Realistic paper + backtest execution 🔴 NEXT

**Bug:** `shares = size_usd / price` ignores book depth, fees, partials, latency.

- [ ] Consume L1 (later L2) size at touch; partial fills; residual unfilled
- [ ] Fee model (taker/maker), optional slippage bps, stale-quote reject
- [ ] Backtest: one fill per level/snapshot; no infinite refill of the same touch across bars
- [ ] Report **net edge** = `1 - exec_up - exec_down - fees - slippage` (not raw `1 - sum_asks`)
- [ ] Mark reports: `SIMULATED — not live expectancy`

### P0 pipeline (target)

```text
ARB / SECOND_SIDE → depth + risk gates → execute     (swarm bypassed) ✅
DIRECTIONAL       → fair value → swarm → risk → execute
MM / COPY         → strategy gates → risk → execute
```

Still open:

- [ ] Keep swarm **only** for directional (and optional MM soft-score) — confirm MM/COPY never hard-blocked by swarm unless intended
- [ ] Document the pipeline in README / STRATEGY.md

---

## P1 — after soft green

### P1-6 — Remove duplicate modules 🟠

- [ ] Delete or quarantine: `bot/bot_config.py`, `bot/bot_strategy.py`, `bot/bot_inventory.py`
- [ ] Single path: `bot.config` / `bot.strategy` / `bot.inventory`
- [ ] CI grep guard

### P1-8 — Execution policy (not global PREFER_MAKER) 🟠

- [ ] ARB: taker if net edge > X; maker only if expected fill allows
- [ ] DIRECTIONAL: maker-preferred default
- [ ] Config: `ARB_EXECUTION_MODE=taker|maker|auto`

### P1-9 — API security for exposed deploys 🟠

- [ ] Require `API_TOKEN` when bound beyond localhost (not only `MODE=live`)
- [ ] Production: explicit `API_CORS_ORIGINS` (no `*`); see `deploy/RISK_API_FLY.md`
- [ ] Multi-user: replace hard-coded `user_id=1` before any shared SaaS claim

### P1-10 — Single source of truth for positions 🟠

- [ ] Worker ledger (JSONL/Postgres) → `/status` or risk API → dashboard
- [ ] Supabase / in-browser sim documented as **demo only**
- [ ] Optional: dashboard read-only when `BOT_STATUS_URL` set (no dual write)

---

## Near-term (after P0-4)

### Execution quality

- [ ] Maker ladder + cancel/replace (order lifecycle)
- [ ] WebSocket CLOB user + market channels
- [ ] Explicit maker|taker from exchange fill messages

### CTF / settlement

- [ ] Live relayer for split/merge/redeem (today paper-safe only)
- [ ] Settlement identity: `order_id → fill_id → position_id → outcome` (not broad slug+time)

### Observability (incl. CLAUDE×QUANT-style, data-bound only)

- [ ] **Inventory & Flow panel** — matched % vs residual %, naked USD, avg set cost (`InventoryBook`)
- [ ] **Decision funnel** on `/status`: `scanned → arb → dir → swarm_pass → gate_pass → submitted → filled`
- [ ] **Set completion stream** — ledger events when pair completes (`set_id`)
- [ ] Session report: sets completed, mean set edge, residual vs paired PnL
- [ ] Cycle latency: `book_age_ms`, `cycle_ms` in status + ledger meta
- [ ] Copy-trading latency: detect → execute ms
- [ ] Market tile grid (dashboard) — compact multi-window UP/DOWN; PAPER/LIVE badge mandatory

### Spot fair

- [ ] `SPOT_FAIR_MODE=window|vwap` (blended prior, not sole signal)

### Naming / honesty

- [ ] Rename `cross_platform_arbitrage` → `cross_platform_signal` (or label “directional only”)
- [ ] Trailing stop: document peak-price trail vs fixed adverse threshold

### Explicitly defer from cinematic UIs

- Hexbin / spectrogram as proof of alpha before realistic fills
- Unverified $/day and six-figure equity as product targets
- “Neural” branding without walk-forward metrics

---

## Medium term (v0.6)

- [ ] Event-driven backtest + walk-forward validation for ML
- [ ] ML: calibration, Brier / log-loss, PnL-after-fees at threshold (not accuracy alone)
- [ ] Shadow mode: live signals, paper size; parity report
- [ ] Injectable clock for gates/backtest
- [ ] Historical book snapshot worker (stop synthetic-only training)
- [ ] Kalshi **execution** client only after dual-leg risk limits exist
- [ ] MCP read-only status tools

---

## Longer term

- [ ] Adaptive set-cost threshold by volatility regime
- [ ] Multi-process / multi-region coordination (optional)
- [ ] True hedged Polymarket ↔ Kalshi

---

## Explicit non-goals

- Guaranteed profit or “copy hot-garbage / bosona / GROKTOPUS”
- Treating viral screenshots as verified live performance
- 100% win-rate marketing metrics
- Running the trading loop on Vercel / Lovable serverless
- Blind copy of Telegram “bot packs”
- Labeling Kalshi gap signals as risk-free arb without dual-leg execution
- Using optimistic backtest as live go-ahead

---

## Deployment targets

| Platform | Role | Status |
|----------|------|--------|
| **Fly.io worker** | `fly.toml` → `python -m bot.main` + `/status` | Config ready |
| **Fly.io risk API** | `fly.risk.toml` → `uvicorn app.main:app` | Config ready (`Dockerfile.risk`) |
| **Railway / Render** | Worker alternatives | Config ready |
| **Docker** | Any host | `Dockerfile` / `Dockerfile.risk` |
| **Vercel / Lovable** | Dashboard only | Not a worker host |

---

## Suggested milestone tags

| Tag | Theme | Status |
|-----|--------|--------|
| **v0.5.0** | Inventory + set accumulator + second-side + swarm | Shipped |
| **v0.5.1** | Swarm ARB bypass + MarketState hygiene + delete `bot_*` + green pytest | Partial (bypass + getattr done) |
| **v0.5.2** | Real fill reconciliation + pair state machine | Partial (core done; policy/labels open) |
| **v0.5.3** | Realistic paper/backtest fills + fees/slippage net edge | **Next** |
| **v0.6.0** | WS books, shadow mode, walk-forward ML, dashboard↔worker SoT | Planned |

---

## Immediate work order (updated)

1. ~~P0-3 swarm skip for ARB~~ ✅  
2. ~~P1-5 getattr fair_up_prob~~ ✅  
3. **P1-6** — delete `bot/bot_*.py` dupes + CI grep  
4. **Finish P0-2 policy** — PAIR_PARTIAL second-side / timeout; block stacked arb on incomplete pair  
5. **Finish P0-1 paper** — `SIMULATED_FILL` label; no proven-edge claims from paper  
6. **P0-4** — realistic paper/backtest (depth, fees, partials, net edge)  
7. **P1-7 / P1-8** — arb leg attribution + execution mode config  
8. Observability panels (inventory flow, funnel, set stream) bound to ledger  
9. Only then meaningful **live** size  

Contributions and issues: [github.com/gepappas98/polymarket-quant-bot-lite](https://github.com/gepappas98/polymarket-quant-bot-lite).
