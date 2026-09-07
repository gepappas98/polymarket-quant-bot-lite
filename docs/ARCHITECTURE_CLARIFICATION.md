# Architecture clarification

The repository intentionally contains two separate trading systems.

| Area | Purpose | Persistence | Order behavior |
|---|---|---|---|
| `bot/` | Python worker and real execution path | JSONL / PostgreSQL ledger | Real orders only when explicitly live-gated; paper mode remains the default |
| `src/simulation/` | Browser paper-trading and dashboard simulations | Supabase `mm_trades`, `copy_trades`, `backtest_results` (plus alert tables) | Simulated only; no real funds and no real orders |

`src/simulation/` is deliberately named and marked so UI behavior cannot be mistaken for worker execution. The dashboard may read worker status for visibility, but it does not share the worker ledger.
