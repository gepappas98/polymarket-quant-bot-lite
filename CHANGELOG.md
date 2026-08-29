# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-08-29

### Added
- **Nexus-style safety layer** (inspired by crypto-whale-watch-nexus):
  - Double opt-in for live trading (`MODE=live` + `LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISK`)
  - Per-market cooldown lock (fail-closed)
  - JSONL trade ledger (`data/trades.jsonl`) for intents, fills, and blocks
  - Track-record win-rate gate for directional trades when enough outcomes exist
- Robust HTTP helper with timeout, retry, and jitter (`bot/http_util.py`)
- Session summary on shutdown (intents / blocked / fills)
- Deployment configs: `Dockerfile`, `fly.toml`, `railway.toml`, `render.yaml`, `Procfile`, `vercel.json`
- `CHANGELOG.md`, `ROADMAP.md`, `LICENSE` (MIT)
- Static `public/index.html` placeholder for Vercel / GitHub Pages

### Changed
- `create_executor` and live path require double opt-in
- Strategy applies ledger-based confidence gate to directional (not pure arb) intents
- Feeds: optional `ccxt`, hardened CLOB book parsing (dict levels)

### Security
- Secrets only via environment variables; `.env` gitignored
- Fail-closed gates when checks fail

## [0.1.0] — 2026-08-29

### Added
- Initial bosona-style Polymarket short-window crypto Up/Down bot
- Market discovery for BTC (and configurable assets) 5m / 15m windows via Gamma API
- Complete-set arb when `UP_ask + DOWN_ask ≤ ARB_THRESHOLD`
- Directional tilt + inventory rebalance logic
- Paper executor (default) and live CLOB skeleton (`py_clob_client_v2`)
- Risk limits: max order USD, max market exposure, daily loss kill-switch
- Rich terminal status table

---

[0.2.0]: https://github.com/gepappas98/polymarket-quant-bot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gepappas98/polymarket-quant-bot/releases/tag/v0.1.0