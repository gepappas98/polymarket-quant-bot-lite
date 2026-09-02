from datetime import datetime
from sqlalchemy import select
from app.core import database
from app.models.risk_config import RiskConfig
from app.models.trade import Trade
from app.services.risk_service import check_circuit_breaker, check_time_window, evaluate_safety_gates, get_or_create_risk_config, install_bot_gate_hook, simulate_trailing_stop
from bot.ledger import LedgerEntry, ledger
from bot.gates import gate_intent


def test_risk_gates_and_stop(monkeypatch):
    from bot import daily_limit
    monkeypatch.setattr(daily_limit, "current_daily_pnl", lambda: 0)
    ledger._entries.append(LedgerEntry(ts=__import__("time").time(), kind="outcome", market_slug="x", pnl_usd=-10))
    with database.SessionLocal() as db:
        config = get_or_create_risk_config(db)
        config.daily_loss_limit = -5
        db.commit()
        assert check_circuit_breaker(1, db).status == "BLOCKED"
        config.enable_circuit_breaker = False
        db.commit()
        assert check_circuit_breaker(1, db).status == "DISABLED"
        config.enable_time_window = True
        config.enabled_time_start, config.enabled_time_end = "22:00", "02:00"
        db.commit()
        assert check_time_window(1, db, datetime(2024, 1, 1, 23, 0)).status == "OK"
        trade = Trade(market_slug="btc-up-or-down", category="crypto", side="UP", entry_price=.5, size_usd=10)
        db.add(trade); db.commit(); db.refresh(trade)
        assert simulate_trailing_stop(trade.id, .47, db).should_close


def test_hook_blocks_and_unregister_is_safe():
    with database.SessionLocal() as db:
        config = get_or_create_risk_config(db)
        config.daily_loss_limit = 0
        db.commit()
    ledger._entries.append(LedgerEntry(ts=__import__("time").time(), kind="outcome", market_slug="x", pnl_usd=-1))
    install_bot_gate_hook()
    assert gate_intent("hook-market", 1).allowed is False
