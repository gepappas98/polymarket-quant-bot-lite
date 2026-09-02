# Polymarket leaderboard API notes

Verified 2026-09-02 from official Polymarket documentation:

- Endpoint: `GET https://data-api.polymarket.com/v1/leaderboard`.
- Query parameters: `category` (default `OVERALL`), `timePeriod` (`DAY`, `WEEK`, `MONTH`, `ALL`), `orderBy` (`PNL`, `VOL`), `limit` (1–50), `offset` (0–1000), optional `user`, and optional `userName`.
- Response entries expose `rank`, `proxyWallet` in the API reference example, `wallet` in the analytics type, `userName`, `vol`, `pnl`, `profileImage`, `xUsername`, and `verifiedBadge`.
- Profit and volume may be returned as decimal strings in the analytics type; adapter should parse numeric strings defensively.
- Documentation presents the leaderboard as public data available through public/secure clients; implementation should not require an API key.

Sources:
- https://docs.polymarket.com/api-reference/core/get-trader-leaderboard-rankings
- https://docs.polymarket.com/market-data/public-analytics
