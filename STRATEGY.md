# Strategy and MarketState contract

## MarketState

`MarketState.market` is the parsed active-market dictionary. Strategy execution requires `slug`, `up_token_id`, and `down_token_id`. `asset` is optional and defaults to `BTC`. Order books are refreshed for both outcome tokens each cycle; `fair_up_prob` is an optional adapter-provided spot-fair estimate and is read defensively.

## Execution pipeline

- `ARB`, `SET_ACCUM`, and `SECOND_SIDE` intents pass depth, exposure, and risk gates, then execute without optional weighted scoring.
- Directional intents compute fair-value/book edges and pass the track-record and executor risk gates. An optional weighted score of existing local fields may filter them only when explicitly enabled with `SWARM_ENABLED=true`; it is off by default and never replaces executor gates.
- Paper fills are explicitly labeled `SIMULATED_FILL`; live inventory and ledger updates occur only after confirmed CLOB fills.
- An incomplete arbitrage pair carries its `set_id` into second-side recovery and blocks duplicate independent pairs until the residual is resolved.
- `bot/ctf_ops.py` split/merge/redeem fail closed in live mode (no relayer client, no unsigned txs) — `ctf_live_available=false` on the status payload. `ARB` / `SET_ACCUM` / `SECOND_SIDE` intents therefore carry `meta.settlement="hold_to_resolution_no_merge"` in live mode: a paired complete-set buy is directional inventory held to resolution, not a closed risk-free arbitrage, until merge/redeem is implemented.
- The `bot.swarm` module contains score-component compatibility names for existing tests and status records; it makes no LLM calls. Its RUNE field is informational context only—risk vetoes remain in executor gates.

This document describes routing and contracts only; it does not change trading or execution behavior.
