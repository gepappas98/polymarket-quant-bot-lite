# P0 Data Boundary Audit

**Project:** `polymarket-quant-bot-lite`  
**Audit date:** 2026-09-08  
**Policy:** Real market observations may feed paper execution; paper fills, fees, slippage, and P&L remain simulated. Demo and mock values are never presented as live worker data.

## Classification vocabulary

| Classification | Meaning | Allowed production behavior |
|---|---|---|
| **REAL** | An observation obtained from Polymarket or another explicitly identified external provider | May be displayed as live market data when its provider and freshness are explicit |
| **PAPER** | Simulated execution/accounting against REAL observations | Must remain labeled paper/simulated and must never be counted as live fills |
| **DEMO** | Browser-generated, synthetic, fallback, or proxy values | Read-only demonstration only; never used for paper order submission |
| **MOCK** | Test doubles and fixtures | Test code only; not a runtime data source |

## Files inspected and source inventory

| Source | Files inspected | Classification | Notes |
|---|---|---|---|
| Polymarket Gamma metadata | `bot/market_finder.py`, `src/lib/polymarket.server.ts`, `src/lib/polymarket.functions.ts` | **REAL** | Active markets, token IDs, outcomes, and metadata come from Polymarket APIs. |
| Polymarket CLOB REST books | `bot/feeds.py`, `src/lib/polymarket.server.ts` | **REAL** | L1/L2 bids and asks; REST is the worker fallback when the socket book is stale/unavailable. |
| Polymarket CLOB WebSocket | `bot/clob_ws.py`, `bot/main.py` | **REAL** | Public market channel; snapshots and price changes are maintained in a thread-safe local cache. |
| Polymarket trader activity/history | `bot/strategies/copy_trading.py`, `docs/polymarket-leaderboard-api-notes.md`, `docs/polymarket-closed-positions-api.md` | **REAL** | Data API activity, leaderboard aggregates, and closed positions where configured. |
| Worker execution | `bot/executor.py`, `bot/execution.py`, `bot/ledger.py`, `bot/status_server.py` | **PAPER** by default; **REAL** only behind live gates | Paper fills and ledger entries are simulated. Live mode remains double opt-in and disabled by default. |
| Worker backtest | `bot/backtest.py` | **PAPER** when replaying observations; historical input can be **REAL** or fixture data | Slippage, fees, and fills are modeled, not exchange confirmations. |
| Binance/ccxt spot feed | `bot/feeds.py`, `bot/config.py` | **REAL external spot**, not Polymarket market data | Auxiliary fair-value signal only. It must never be labeled as a Polymarket book. |
| Browser Binance market maker | `src/simulation/useMarketMaker.sim.ts`, `docs/FEATURES.md` | **DEMO** for Polymarket provenance; auxiliary source is real Binance | Browser-only Supabase simulation uses Binance trades as a proxy and cannot submit orders. |
| Browser-generated dashboard status | `src/lib/bot-demo.ts`, `src/routes/index.tsx` | **DEMO** | Deterministic synthetic markets, ledger, P&L, and swarm are explicitly marked DEMO. |
| Supabase/browser simulation | `src/simulation/*`, `src/lib/paper.functions.ts`, Supabase paper tables/migrations | **PAPER** execution with Supabase persistence | It is simulation-only and must consume REAL worker quotes for paper orders. It is not the worker ledger. |
| Test fixtures and doubles | `tests/*`, `src/**/*.test.ts`, `src/lib/execution/*.test.ts` | **MOCK** | `FakeBook`, `FakeClient`, `FakeResponse`, random seeded fixtures, and monkeypatched HTTP remain test-only and were not removed. |
| Historical/reference data | `historical_candles`, `historical_winrate`, `bot/backtest.py`, Polymarket historical docs | **REAL** when imported from Polymarket; **MOCK** when test fixture; **PAPER** when used for simulated replay | Provenance must be carried with the dataset; a historical observation is not a live quote. |

## Enforcement changes

The worker now emits `data_source`, `execution_mode`, `market_data_source`, `is_simulated`, `market_data_provider`, and `auxiliary_data_sources` in `/status`. A paper worker reports REAL Polymarket market input plus `execution_mode=PAPER` and `is_simulated=true`.

The dashboard demo generator reports `DEMO` for both data and execution. If `BOT_STATUS_URL` is configured, failed or malformed worker responses now raise an error instead of silently being merged with synthetic demo values. The dashboard renders an explicit unavailable state and never substitutes demo values for a failed worker.

The browser Paper Desk disables buys, closes, and unrealized marking unless the current status declares `market_data_source=REAL`. Its UI labels real input as **LIVE MARKET DATA** and execution as **PAPER / SIMULATED EXECUTION**. Demo input is labeled **DEMO DATA**.

## Files changed in this P0

- `bot/data_boundary.py`
- `bot/status_server.py`
- `src/lib/bot-types.ts`
- `src/lib/bot-demo.ts`
- `src/lib/bot.server.ts`
- `src/routes/index.tsx`
- `src/components/paper/PaperDesk.tsx`
- `src/simulation/useMarketMaker.sim.ts`
- `docs/FEATURES.md`
- `docs/DATA_BOUNDARY_AUDIT.md`
- `tests/test_data_boundary.py`
- `src/lib/bot.server.test.ts`
- `ROADMAP.md`
- `CHANGELOG.md`

## Remaining simulated or demo sources

1. `src/lib/bot-demo.ts` intentionally generates synthetic dashboard values when no worker URL is configured. It is explicit DEMO and read-only.
2. `src/simulation/useMarketMaker.sim.ts` uses real Binance trades as a DEMO proxy for a browser simulation; it is not a Polymarket feed.
3. Supabase `paper_*`, `mm_trades`, `copy_trades`, and `backtest_results` remain browser/paper persistence and do not constitute real fills.
4. Worker paper execution models fills, fees, slippage, and P&L against observed books.
5. Backtest and unit-test fixtures remain synthetic by design.

## Remaining production risks

- The dashboard and worker have separate ledgers; Supabase paper state is not the worker's JSONL/PostgreSQL ledger.
- Real WebSocket data requires a persistent worker process and a correctly configured `BOT_STATUS_URL`; no live data is fabricated when that connection fails.
- Auxiliary Binance spot data can influence worker fair-value logic, but it is not evidence of Polymarket liquidity or execution.
- Live order placement remains a separate, explicitly gated path and was not enabled by this audit.
- Historical datasets need operational provenance and freshness checks before being used for production decisions.
