# Roadmap

Prioritized plan for the Polymarket Quant Bot. Order may change based on usage and market structure.

**Audit snapshot (static + runtime on `polymarket-quant-bot-lite`):** ~6.2/10 as a framework, ~4.5/10 for real-money readiness. Strong gates/ledger/architecture; **not** production-ready on live fills, pair atomicity, or backtest realism. Do **not** treat paper/backtest PnL as proof of edge until the v0.5.x overhaul below lands.

External references that shaped priorities (research only — not affiliations):

- Public trader **@hot-garbage** (`0x3139…9e2e`): complete-set accumulation + residual directional + inventory rebalance (~50–55% event win rate).
- Viral “GROK / GROKTOPUS” terminals: treat as **simulated / marketing UI** unless a wallet is independently verified.

---

## Just shipped (reference)

### v0.4.x — risk engine & dashboard

- [x] FastAPI risk-engine sidecar (`app/`), Kelly, leaderboard adapter, trailing-stop path, auth on mutating routes (when `API_TOKEN` set)
- [x] Plugin strategies (MM, copy, ML, cross-venue **signal**), gates, kill switch, Prometheus hooks
- [x] React control room (Monitor / Desk / Leaders / Sizing / Strategies / Settings)

### v0.5.0-ish — inventory & swarm (worker)

- [x] `bot/inventory.py` — paired / residual / avg_set_cost / second-side lag
- [x] Complete-set accumulator + SECOND_SIDE + spot fair blend (`USE_SPOT_FAIR`)
- [x] `bot/ctf_ops.py` — paper-safe split/merge/redeem skeleton (live fail-closed)
- [x] `bot/swarm.py` — non-LLM module consensus (TIDAL…LUMEN)
- [x] Ledger `meta.swarm` / `set_id`; `/status` swarm block
- [x] Deploy docs: `fly.risk.toml`, `Dockerfile.risk` (Leaders API ≠ worker)

**Known gap after ship:** suite not fully green when swarm filters ARB; `LiveExecutor` still treats post-accept as fill; legacy `bot/bot_*.py` duplicates may remain in tree.

---

## CRITICAL — v0.5 execution & accounting overhaul

> Do not enable `MODE=live` until **P0-1** and **P0-2** are done. Do not use backtest PnL as go-live evidence until **P0-4**.

### P0-1 — Real CLOB fill reconciliation 🔴

**Bug:** `LiveExecutor` treats `create_and_post_order` acceptance as a full fill at requested size/price.

**Target state machine**

```text
ORDER_SUBMITTED → ORDER_OPEN → ORDER_PARTIAL → ORDER_FILLED
                              ↘ ORDER_CANCELLED / REJECTED
```

- [ ] Persist order id + requested vs filled qty/avg price
- [ ] Poll user channel / open-orders / trades until terminal state (or timeout → cancel + reconcile)
- [ ] Update **inventory + ledger only from confirmed fills** (partials allowed)
- [ ] Never set `status=filled` on submit alone
- [ ] Paper path may stay optimistic **but** must be labeled `SIMULATED_FILL` and excluded from “proven edge” reports

### P0-2 — Pair-aware / atomic arbitrage execution 🔴

**Bug:** UP and DOWN legs are independent posts → one leg can fill alone (naked directional risk).

- [ ] `ArbPair` / pair intent: `PAIR_PENDING | PAIR_PARTIAL | PAIR_COMPLETE | PAIR_FAILED`
- [ ] Shared `set_id` already exists — wire through executor + inventory (`is_arb_leg` must not be forced `False` in `update_inventory`)
- [ ] On `PAIR_PARTIAL`: active second-side / reduce / timeout policy (extend SECOND_SIDE)
- [ ] Optional: reject opening second independent arb while pair incomplete on same window

### P0-3 — Swarm must not veto deterministic complete-set arb 🔴

**Bug:** ARB detects `sum_asks < threshold` then swarm returns 0 intents (`consensus < 0.70`).

- [ ] **Bypass swarm** for `is_arb_leg` / reason `ARB` / `SECOND_SIDE` (deterministic + risk gates only)
- [ ] Keep swarm for **directional** (and optionally MM soft-score)
- [ ] Pipeline:

```text
ARB / SECOND_SIDE → depth + risk gates → execute
DIRECTIONAL       → fair value → swarm → risk gates → execute
MM / COPY         → strategy-specific gates → risk → execute
```

- [ ] Regression: `test_buys_both_sides_when_sum_below_threshold` must pass with `SWARM_ENABLED=true`

### P0-4 — Realistic paper + backtest execution 🔴

**Bug:** `shares = size_usd / price` ignores book depth, fees, partials, latency.

- [ ] Consume L1 (and later L2) size at touch; partial fills; residual unfilled
- [ ] Fee model (taker/maker), optional slippage bps, stale-quote reject
- [ ] Backtest: one fill per level/snapshot rules; no infinite refill of the same $3 ask across 100 bars
- [ ] Report **net edge** = `1 - exec_up - exec_down - fees - slippage` (not raw `1 - sum_asks`)
- [ ] Mark backtest reports: `SIMULATED — not live expectancy`

### P1-5 — MarketState contract hygiene 🟠

**Bug:** `state.fair_up_prob` AttributeError on FakeState / partial mocks (majority of current test failures).

- [ ] `fair_up = getattr(state, "fair_up_prob", None)` (or Protocol + adapter)
- [ ] Document required vs optional fields for strategy / backtest / tests
- [ ] Green full `pytest` on clean checkout

### P1-6 — Remove duplicate modules 🟠

- [ ] Delete or quarantine unused: `bot/bot_config.py`, `bot/bot_strategy.py`, `bot/bot_inventory.py`
- [ ] Single import path: `bot.config` / `bot.strategy` / `bot.inventory` only
- [ ] Grep CI check: no `bot_strategy` imports

### P1-7 — Pass `is_arb_leg` into inventory 🟠

- [ ] `update_inventory(..., is_arb_leg=intent.is_arb_leg)`
- [ ] Analytics: arb vs directional PnL attribution

### P1-8 — Execution policy (not global PREFER_MAKER) 🟠

- [ ] ARB: taker if net edge > X; maker only if fill-prob model allows
- [ ] DIRECTIONAL: maker-preferred default
- [ ] Config: `ARB_EXECUTION_MODE=taker|maker|auto`

### P1-9 — API security for exposed deploys 🟠

- [ ] Require `API_TOKEN` whenever process is reachable beyond localhost (not only `MODE=live`)
- [ ] Production: explicit `API_CORS_ORIGINS` (no `*`); document in `deploy/RISK_API_FLY.md`
- [ ] Multi-user: replace hard-coded `user_id=1` before any shared SaaS claim

### P1-10 — Single source of truth for positions 🟠

- [ ] Prefer: worker ledger (JSONL/Postgres) → `/status` or risk API → dashboard
- [ ] Document Supabase / in-browser sim as **demo only** (README + Monitor badge already partially does this)
- [ ] Optional: dashboard read-only mode when `BOT_STATUS_URL` set (no dual write)

---

## Near-term (after soft green + P0)

### Execution quality

- [ ] Maker ladder + cancel/replace (order lifecycle)
- [ ] WebSocket CLOB user + market channels
- [ ] Explicit maker|taker from exchange fill messages

### CTF / settlement

- [ ] Live relayer for split/merge/redeem (today paper-safe only)
- [ ] Settlement identity: `order_id → fill_id → position_id → outcome` (not broad slug+time)

### Observability

- [ ] Inventory plane on dashboard: paired vs residual, avg set cost, naked USD
- [ ] Session report: sets completed, mean set edge, residual vs paired PnL
- [ ] Copy-trading latency fields: detect → execute ms in ledger

### Naming / honesty

- [ ] Rename `cross_platform_arbitrage` → `cross_platform_signal` (or label everywhere “directional only”)
- [ ] Trailing stop: real peak-price trail vs fixed adverse threshold (document which)

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
- [ ] True hedged Polymarket↔Kalshi

---

## Explicit non-goals

- Guaranteed profit or “copy hot-garbage / bosona / GROKTOPUS”
- Treating viral screenshots as verified live performance
- 100% win-rate marketing metrics
- Running the trading loop on Vercel / Lovable serverless
- Blind copy of Telegram “bot packs”
- Labeling Kalshi gap signals as risk-free arb without dual-leg execution
- Using current optimistic backtest as live go-ahead

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

| Tag | Theme |
|-----|--------|
| **v0.5.0** | Inventory + set accumulator + second-side + swarm module |
| **v0.5.1** | Swarm ARB bypass + MarketState hygiene + delete `bot_*` dupes + green pytest |
| **v0.5.2** | Real fill reconciliation + pair state machine |
| **v0.5.3** | Realistic paper/backtest fills + fees/slippage net edge |
| **v0.6.0** | WS books, shadow mode, walk-forward ML, dashboard↔worker SoT |

---

## Immediate work order (do in this sequence)

1. **P0-3** — swarm skip for ARB/SECOND_SIDE (unblocks tests + correct arb path)  
2. **P1-5** — `getattr` / Protocol for `fair_up_prob` (green suite)  
3. **P1-6 / P1-7** — delete dupes; pass `is_arb_leg`  
4. **P0-1** — order/fill state machine on live (and honest labels on paper)  
5. **P0-2** — pair engine  
6. **P0-4** — realistic backtest/paper  
7. Only then consider **live** capital  

Contributions and issues: [github.com/gepappas98/polymarket-quant-bot-lite](https://github.com/gepappas98/polymarket-quant-bot-lite).
