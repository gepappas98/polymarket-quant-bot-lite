# REAL Historical Polymarket Backtesting

The production historical replay path is `run_real_backtest()` in `bot.backtest`. It consumes `PolymarketHistoricalL2DataSource`, which reads the append-only SQLite dataset produced by the REAL Polymarket CLOB recorder. Each row identifies the market, token, event timestamp, bid levels, and ask levels. Rows are replayed in event-time order, with each token's latest complete book retained for subsequent strategy evaluation.

Historical market data is real; executions are simulated.

## CLI

```bash
python -m bot.backtest \
  --real-db data/polymarket_l2.db \
  --market-id <market-id> \
  --token-id <token-id> \
  --start-ms 1700000000000 \
  --end-ms 1700003600000
```

The legacy positional JSONL input remains available for existing unit-test fixtures. It is not used by the REAL path and cannot be selected implicitly. A missing database, empty filter result, malformed row, or invalid source metadata raises `HistoricalDataUnavailable`; there is no synthetic, random, demo, or manual fallback in REAL mode.

## Result contract

REAL results contain `data_source=REAL_HISTORICAL_POLYMARKET` and `execution_mode=PAPER_SIMULATION`. They expose trades/fills, partial fills, fees, slippage, gross and net PnL, drawdown, peak exposure, turnover, fill ratio, data coverage, and data-quality warnings. The existing `PaperFillEngine` consumes the reconstructed bid/ask depth and therefore produces level-by-level partial fills rather than infinite liquidity. Legacy fixture helpers remain unchanged for unit tests.
