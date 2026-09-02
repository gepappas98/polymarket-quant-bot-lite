# Polymarket closed-position data source

**Verified:** 2026-09-02

The official Polymarket Data API exposes a public `GET https://data-api.polymarket.com/closed-positions` endpoint for a user-scoped closed-position history.

| Item | Contract |
| --- | --- |
| Required wallet parameter | `user`, a `0x`-prefixed 40-hex-character profile/proxy-wallet address |
| Pagination | `limit` and `offset` |
| Useful response fields | `proxyWallet`, `asset`, `conditionId`, `avgPrice`, `totalBought`, `realizedPnl`, `curPrice`, `timestamp`, `slug`, `outcome`, `endDate` |
| Scoring interpretation | `realizedPnl` is the realized return numerator; `totalBought` is the invested notional/size denominator; `timestamp` preserves chronology for drawdown calculation |

This endpoint is preferable to raw public fills for leaderboard score enrichment because raw fills do not themselves contain realized PnL. The integration must remain fail-soft: if a trader's detailed history cannot be obtained, retain that trader's normalized aggregate leaderboard observation rather than fabricating results or discarding the whole refresh.

## Source

[Polymarket documentation — Get closed positions for a user](https://docs.polymarket.com/api-reference/core/get-closed-positions-for-a-user)
