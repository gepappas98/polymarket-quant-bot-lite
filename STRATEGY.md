# Strategy and MarketState contract

## MarketState

`MarketState.market` is the parsed active-market dictionary. Strategy execution requires `slug`, `up_token_id`, and `down_token_id`. `asset` is optional and defaults to `BTC`. Order books are refreshed for both outcome tokens each cycle; `fair_up_prob` is an optional adapter-provided spot-fair estimate and is read defensively.

## Execution pipeline

- `ARB` and `SECOND_SIDE` intents pass depth, exposure, and risk gates, then execute without soft swarm consensus.
- Directional intents compute fair-value/book edges, pass the track-record and risk gates, then go through swarm consensus before execution.
- Paper fills are explicitly labeled `SIMULATED_FILL`; live inventory and ledger updates occur only after confirmed CLOB fills.
- An incomplete arbitrage pair carries its `set_id` into second-side recovery and blocks duplicate independent pairs until the residual is resolved.

This document describes routing and contracts only; it does not change trading or execution behavior.
