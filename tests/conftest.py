import os
import pytest

# Force safe defaults before any bot module is imported, so tests never
# accidentally pick up a real .env with live credentials.
os.environ.setdefault("MODE", "paper")
os.environ.pop("LIVE_TRADING_CONFIRM", None)
os.environ.pop("POLYMARKET_PRIVATE_KEY", None)


@pytest.fixture(autouse=True)
def risk_engine_isolation(tmp_path, monkeypatch):
    from app.core import database
    from bot.ledger import ledger
    from bot import gates
    from app.services import execution_service

    database.configure(f"sqlite:///{tmp_path / 'app.db'}")
    database.init_db()
    monkeypatch.setenv("LEDGER_PATH", str(tmp_path / "trades.jsonl"))
    monkeypatch.setattr(ledger, "path", tmp_path / "trades.jsonl")
    ledger._entries.clear()
    gates.extra_checks.clear()
    execution_service.reset_executor()
    yield
    ledger._entries.clear()
    gates.extra_checks.clear()
    execution_service.reset_executor()
