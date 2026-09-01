# Feature implementation notes

## Stack mapping

The requested "Supabase Edge Functions only" backend maps onto this project's
TanStack Start runtime as **server functions** (`createServerFn`) plus one
public HTTP route for the scheduled monitor. Same trust boundaries, no custom
server, no Python. Everything else (strategy logic, market making, backtests)
runs client-side as requested.

| JSON spec "edge" | Implementation |
| --- | --- |
| `get_mm_stats` | `getMmStats` in `src/lib/trading.functions.ts` |
| `log_trade` | `logTrade` (mm_trades / copy_trades) |
| `get_cooldown` | `getCooldown` (read or arm, persisted) |
| `send_alert` | `sendAlert` (Slack/Telegram webhook + alert_history) |
| `fetch_kalshi` | `fetchKalshi` (cross-venue reference price) |
| wallet positions | `fetchWalletPositions` in `src/lib/copy.functions.ts` |
| alert monitor (cron) | `POST /api/public/hooks/monitor-alerts` (cron-secret auth, service role) |

## Priority 1

1. **Market making** — `src/hooks/useMarketMaker.ts` opens a Binance trade
   WebSocket, quotes both sides at `spreadBps/2` around mid, simulates fills
   when the tape crosses a quote, persists each fill through `logTrade` and
   arms the cooldown. UI: `MarketMakingPanel` (spread, inventory, realized /
   unrealized / stored P&L, equity curve, fill tape).
2. **Copy trading** — `CopyTradingPanel`: watchlist CRUD on `copy_watchlist`,
   live wallet positions via `fetchWalletPositions`, position-diff table
   (their size vs mirrored size) and a Mirror action that logs `copy_trades`.
3. **Kelly sizing** — `src/lib/kelly.ts` (`kellyFraction`, `kellySizeUsd`,
   `winRateFromRecord`) with `KellySlider` for fraction, bankroll, hard order
   cap, historical win-rate source and manual override.
4. **Cooldown** — `CooldownTimer` reads server state every 30s, ticks locally,
   and can arm a cooldown that survives reloads (`cooldown_state`).

## Priority 2

5. **Plugin strategies** — `src/strategies/registry.ts` declares plugins whose
   parameter editors are `React.lazy()` code-split modules; enable/disable and
   params persist in `strategy_config` (`StrategyManager`).
6. **Backtesting** — `BacktestConfig` loads hourly candles in the browser,
   runs the selected plugin's `simulate()`, charts the equity curve with
   recharts and stores runs in `backtest_results`.
7. **Alerting** — `AlertConfigPanel` manages rules and history; the cron route
   evaluates kill-switch / daily-loss / drawdown / win-rate thresholds hourly,
   is idempotent per rule per hour, and delivers via webhook.

## Schema

All tables carry `id`, `created_at`, `updated_at`, and a `user_id` owner with
RLS restricted to `auth.uid()`: `mm_trades`, `copy_watchlist`, `copy_trades`,
`cooldown_state` (unique per user+market), `strategy_config` (unique per
user+name), `backtest_results`, `alert_config`, `alert_history`,
`historical_winrate`. `historical_candles` is shared reference data: readable
by authenticated users, writable only by the service role. Realtime is enabled
on `mm_trades`, `cooldown_state`, `alert_history`.

## Dependencies

`@supabase/supabase-js`, `@tanstack/react-query`, `recharts` and `date-fns`
were already in `package.json`; no additions were required. Realtime ships
inside `@supabase/supabase-js`.

## Scheduling the monitor

```sql
select cron.schedule(
  'monitor-alerts-hourly',
  '0 * * * *',
  $$ select net.http_post(
       url := 'https://project--3db41114-3331-414b-a186-a4769510f50f.lovable.app/api/public/hooks/monitor-alerts',
       headers := '{"Content-Type":"application/json","Authorization":"Bearer <LOVABLE_CRON_SECRET>"}'::jsonb,
       body := '{}'::jsonb
     ) $$
);
```
