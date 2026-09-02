# PostgreSQL app database

The FastAPI sidecar supports any SQLAlchemy database URL through `APP_DATABASE_URL`. SQLite remains the default for local development:

```env
APP_DATABASE_URL=sqlite:///data/app.db
```

For PostgreSQL, install the optional Psycopg driver and use the explicit SQLAlchemy dialect:

```bash
sudo pip install 'psycopg[binary]>=3.1.0'
```

```env
APP_DATABASE_URL=postgresql+psycopg://user:password@host:5432/polymarket_app
```

On startup, `init_db()` imports all app models, creates missing tables, and applies the existing lightweight missing-column migration. PostgreSQL uses SQLAlchemy's native PostgreSQL dialect and does not receive SQLite-only `check_same_thread` connection arguments.

## Deployment checklist

| Check | Requirement |
| --- | --- |
| Driver | `psycopg[binary]` installed in the runtime image/environment |
| URL | `postgresql+psycopg://user:password@host:5432/database` |
| Network | The deployed API process can reach the database host and port |
| Schema | The database user can create/alter tables during first startup, or the schema is provisioned separately |
| Secrets | Keep the URL in deployment secrets; do not commit credentials to `.env` or source control |
| Verification | Run the API health check and the database-backed test suite against a disposable PostgreSQL database |

This repository currently verifies PostgreSQL URL construction and dialect-specific configuration in unit tests. A live PostgreSQL server is not bundled with the repository or the local development sandbox, so end-to-end network/database verification must be run in CI or the target deployment environment.
