# Simulation boundary

This directory contains the browser-only, Supabase-backed paper-trading surface. Every module is explicitly marked `IS_SIMULATION_ONLY = true`. It may display quotes, record simulated fills, copy simulated trades, backtest, and configure alerts, but it **does not place real orders**.

The real execution path lives under `bot/`; only that worker can place orders, subject to paper mode defaults and live-trading gates. The worker owns the JSONL/PostgreSQL ledger. Keep imports one-way: dashboard simulation code must not be treated as an execution adapter for `bot/`.
