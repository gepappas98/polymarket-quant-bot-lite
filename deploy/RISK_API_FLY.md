# Risk API on Fly.io

The trading worker (`fly.toml` → `python -m bot.main`) is separate from the
**Risk / Leaders FastAPI** sidecar (`fly.risk.toml` → `uvicorn app.main:app`).

The Lovable dashboard Leaders / Sizing / Strategies pages call:

```text
VITE_API_URL + /api/leaders
VITE_API_URL + /api/risk/...
```

Default without config is `http://localhost:8000`, which does not work from Lovable.

## Files

| File | Role |
|------|------|
| `fly.risk.toml` | Fly app for risk API |
| `Dockerfile.risk` | Slim image: `app/` + `bot/` + uvicorn |
| `.env.risk.example` | Env checklist |
| Existing `app/main.py` | CORS via `API_CORS_ORIGINS` |

## Deploy

```bash
fly apps create polymarket-quant-risk
fly volumes create risk_data --region iad --size 1 -a polymarket-quant-risk

fly secrets set -a polymarket-quant-risk \
  MODE=paper \
  API_TOKEN="$(openssl rand -hex 24)" \
  API_CORS_ORIGINS="https://polymarket-quant-bot-lite.lovable.app,http://localhost:5173"

fly deploy -a polymarket-quant-risk -c fly.risk.toml
```

Save the `API_TOKEN` value — set the same on Lovable as `VITE_API_TOKEN`.

## Lovable / frontend env

```bash
VITE_API_URL=https://polymarket-quant-risk.fly.dev
VITE_API_TOKEN=<same as API_TOKEN>
```

Rebuild / redeploy the frontend after changing any `VITE_*` variable.

## Verify

```bash
curl -s https://polymarket-quant-risk.fly.dev/health
# {"ok":true}

curl -s "https://polymarket-quant-risk.fly.dev/api/leaders?limit=5"

curl -s -X POST "https://polymarket-quant-risk.fly.dev/api/leaders/refresh?sync=true" \
  -H "Authorization: Bearer $API_TOKEN"
```

Then open `/leaders` on the dashboard and click **Refresh**.

## CORS

`app/main.py` already reads:

```text
API_CORS_ORIGINS=https://polymarket-quant-bot-lite.lovable.app,http://localhost:5173
```

Use exact origins (not `*`) when the browser sends credentials / Authorization.

## Optional Postgres

```bash
fly secrets set -a polymarket-quant-risk \
  APP_DATABASE_URL="postgresql+psycopg://USER:PASS@HOST:5432/risk"
```

Install driver in the image if needed (`psycopg[binary]` in `requirements.txt`).

## Do not mix with worker fly.toml

| Config | Process |
|--------|---------|
| `fly.toml` | Trading worker + optional `/status` on 8080 |
| `fly.risk.toml` | Risk API on 8000 for Leaders / Kelly / gates |
