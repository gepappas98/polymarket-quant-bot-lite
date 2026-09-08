import json

from bot.ledger import Ledger, LedgerEntry


def test_execution_events_have_identity_and_idempotency(tmp_path):
    ledger = Ledger(tmp_path / "execution.jsonl")
    entry = LedgerEntry(
        ts=1.0,
        kind="order",
        event_type="ORDER_SUBMITTED",
        market_slug="market-1",
        token_id="token-1",
        side="UP",
        quantity=2.0,
        price=0.4,
        order_id="order-1",
        execution_mode="PAPER",
        data_source="REAL",
        idempotency_key="order-1:submitted",
    )
    assert ledger.append(entry) is True
    assert ledger.append(entry) is False
    persisted = json.loads((tmp_path / "execution.jsonl").read_text().splitlines()[0])
    assert persisted["event_id"] == entry.event_id
    assert persisted["event_type"] == "ORDER_SUBMITTED"
    assert persisted["execution_mode"] == "PAPER"
    assert persisted["data_source"] == "REAL"


def test_ledger_health_exposes_last_event_and_stale_state(tmp_path):
    ledger = Ledger(tmp_path / "execution.jsonl")
    ledger.append(LedgerEntry(ts=1.0, kind="order", event_type="ORDER_REJECTED", market_slug="market-1"))
    health = ledger.health(stale_after_seconds=0.1)
    assert health["lastEventType"] == "ORDER_REJECTED"
    assert health["lastEventId"]
    assert health["stale"] is True
    assert health["writable"] is True
