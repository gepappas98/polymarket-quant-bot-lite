import json
import time

from fastapi.testclient import TestClient

from app.core import database
from app.ledger.reader import read_entries, trade_history
from app.main import app
from app.models.trade import Trade
from app.services import risk_service
from app.services.risk_service import category_exposure, evaluate_safety_gates, get_or_create_risk_config
from app.services.trading_service import place_order
from bot import gates
from bot.config import cfg
from bot.executor import Fill
from bot.ledger import LedgerEntry, ledger


def test_risk_engine_startup_failure_blocks_intents(monkeypatch):
    import bot.main as bot_main

    monkeypatch.setenv("RISK_ENGINE_ENABLED", "true")
    gates.extra_checks.clear()

    def fail_install():
        raise RuntimeError("startup boom")

    monkeypatch.setattr("app.services.risk_service.install_bot_gate_hook", fail_install)
    bot_main.install_risk_engine()

    result = gates.gate_intent("startup-market", 1)
    assert not result.allowed
    assert "risk engine failed to initialise: startup boom" in result.reason


def test_extra_check_rejection_does_not_consume_cooldown():
    slug = "extra-check-market"
    gates.cooldown.clear(slug)
    state = {"blocked": True}

    def check(market_slug, size_usd):
        if state["blocked"]:
            state["blocked"] = False
            return gates.GateResult(False, "temporary rejection")
        return gates.GateResult(True)

    gates.register_check(check)
    assert not gates.gate_intent(slug, 1).allowed
    assert gates.gate_intent(slug, 1).allowed


def test_read_entries_merges_file_and_in_process_rows(tmp_path):
    path = tmp_path / "trades.jsonl"
    persisted = {
        "ts": 1.0, "kind": "fill", "market_slug": "election-2028",
        "side": "UP", "size_usd": 5.0, "order_id": "file-order",
    }
    path.write_text(json.dumps(persisted) + "\n", encoding="utf-8")
    ledger._entries.append(LedgerEntry(
        ts=2.0, kind="outcome", market_slug="election-2028",
        side="UP", pnl_usd=2.0, order_id="file-order",
    ))

    rows = read_entries(path)
    assert {row["kind"] for row in rows} == {"fill", "outcome"}


def test_orderless_outcome_closes_all_slug_fills(tmp_path, monkeypatch):
    path = tmp_path / "trades.jsonl"
    entries = [
        {"ts": 1.0, "kind": "fill", "market_slug": "election-2028", "side": "UP", "price": .4, "size_usd": 4, "order_id": "up"},
        {"ts": 2.0, "kind": "fill", "market_slug": "election-2028", "side": "DOWN", "price": .6, "size_usd": 6, "order_id": "down"},
        {"ts": 3.0, "kind": "outcome", "market_slug": "election-2028", "side": "DOWN", "pnl_usd": 7.5},
    ]
    path.write_text("\n".join(json.dumps(row) for row in entries) + "\n", encoding="utf-8")
    monkeypatch.setenv("LEDGER_PATH", str(path))
    ledger._entries.clear()

    history = trade_history(status="closed")
    assert len(history) == 2
    by_side = {row["side"]: row for row in history}
    assert by_side["UP"]["pnl_usd"] == 0.0
    assert by_side["DOWN"]["pnl_usd"] == 7.5
    assert all(row["status"] == "closed" for row in history)


def test_invalid_side_returns_422():
    with TestClient(app) as client:
        response = client.post("/api/trades/place", json={
            "market_slug": "election-invalid-side",
            "token_id": "token",
            "side": "MAYBE",
            "price": .5,
            "confidence": .8,
            "balance": 100,
        })
    assert response.status_code == 422
    assert response.json()["detail"] == "side must be UP or DOWN"


def test_concurrent_category_ceiling_allows_only_one_fill():
    session = database.SessionLocal()
    try:
        config = get_or_create_risk_config(session)
        config.enable_category_ceiling = True
        config.category_ceiling_politics = 6.0
        config.k_value = .25
        config.max_position_pct = .05
        session.commit()
    finally:
        session.close()

    class Executor:
        def execute(self, intents):
            intent = intents[0]
            return [Fill(
                intent=intent, shares=intent.size_usd / intent.price,
                avg_price=intent.price, cost=intent.size_usd,
                ts=time.time(), order_id=f"test-{intent.market_slug}",
                simulated=True,
            )]

    import concurrent.futures

    def submit(slug):
        with database.SessionLocal() as db:
            return place_order(
                market_slug=slug, token_id="token", side="up", price=.5,
                confidence=.9, balance=100, db=db, executor=Executor(),
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("election-one", "election-two")))
    assert [result.status for result in results].count("filled") == 1


def test_settlement_reconciliation_closes_trade_and_exposure():
    slug = "election-settlement"
    risk_service.advanced_cooldown.clear(slug)
    with database.SessionLocal() as db:
        result = place_order(
            market_slug=slug, token_id="token", side="UP", price=.5,
            confidence=.9, balance=100, db=db,
        )
        assert result.status == "filled"
        ledger.append(LedgerEntry(
            ts=time.time() + 1, kind="outcome", market_slug=slug,
            side="UP", pnl_usd=3.0, order_id=result.fill["order_id"],
        ))
        exposure = category_exposure(db)
        trade = db.get(Trade, result.trade_id)
        assert exposure["politics"]["exposure"] == 0.0
        assert trade.status == "closed"
        assert trade.pnl_usd == 3.0


def test_advanced_cooldown_uses_configured_short_and_long_values():
    slug = "election-cooldown-values"
    risk_service.advanced_cooldown.clear(slug)
    with database.SessionLocal() as db:
        config = get_or_create_risk_config(db)
        config.cooldown_seconds = 30
        db.commit()
        first = evaluate_safety_gates(1, db, slug, "politics", 1)
        assert first.gates[2].name == "advanced_cooldown"
        assert first.gates[2].status == "OK"
        assert risk_service.advanced_cooldown.minutes == .5
        risk_service.advanced_cooldown.check_and_lock(slug)
        assert evaluate_safety_gates(1, db, slug, "politics", 1).allowed is False
        risk_service.advanced_cooldown.clear(slug)
        config.cooldown_seconds = 600
        db.commit()
        evaluate_safety_gates(1, db, slug, "politics", 1)
        assert risk_service.advanced_cooldown.minutes == 10


def test_api_token_auth_and_live_missing_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret-token")
    with TestClient(app) as client:
        assert client.post("/api/risk/update", json={"k_value": .2}).status_code == 401
        assert client.post(
            "/api/risk/update", json={"k_value": .2},
            headers={"Authorization": "Bearer secret-token"},
        ).status_code == 200
        assert client.post(
            "/api/risk/update", json={"k_value": .2},
            headers={"X-API-Key": "secret-token"},
        ).status_code == 200

    monkeypatch.delenv("API_TOKEN")
    monkeypatch.setattr(cfg, "mode", "live")
    try:
        with TestClient(app) as client:
            response = client.post("/api/risk/update", json={"k_value": .3})
        assert response.status_code == 503
        assert response.json()["detail"] == "API_TOKEN required in live mode"
    finally:
        monkeypatch.setattr(cfg, "mode", "paper")


def test_all_mutating_api_routes_require_auth(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret-token")
    cases = [
        ("/api/risk/update", {"k_value": 0.2}),
        ("/api/risk/trailing-stop", {"trade_id": 999999, "current_price": 0.5}),
        ("/api/strategies/update", {"politics_only": True}),
        ("/api/leaders/refresh", None),
        ("/api/ml/retrain", None),
        ("/api/trades/place", {
            "market_slug": "btc-up-or-down", "token_id": "token", "side": "UP",
            "price": 0.5, "confidence": 0.8, "balance": 100,
        }),
        ("/api/trades/price", {"trade_id": 999999, "current_price": 0.5}),
    ]
    with TestClient(app) as client:
        for path, payload in cases:
            response = client.post(path, json=payload) if payload is not None else client.post(path)
            assert response.status_code == 401, (path, response.status_code, response.text)

        allowed = client.post(
            "/api/strategies/update",
            json={"politics_only": True},
            headers={"Authorization": "Bearer secret-token"},
        )
        assert allowed.status_code == 200


def test_wildcard_cors_does_not_enable_credentials():
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.headers.get("access-control-allow-credentials") != "true"
