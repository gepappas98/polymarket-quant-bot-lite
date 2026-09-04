import pytest

from bot.executor import LiveExecutor, PaperExecutor
from bot.ledger import ledger
from bot.strategy import Intent, Side
from bot.config import cfg


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.cancelled = []

    def get_order(self, order_id):
        return next(self.responses)

    def cancel(self, order_id):
        self.cancelled.append(order_id)


def executor_with(client):
    executor = LiveExecutor.__new__(LiveExecutor)
    executor.client = client
    return executor


def test_paper_fill_is_explicitly_marked_simulated(monkeypatch):
    ledger._entries.clear()
    strategy = type("Strategy", (), {
        "update_inventory": lambda *args, **kwargs: None,
    })()
    executor = PaperExecutor(strategy)
    intent = Intent("market", "token", Side.UP, "BUY", 0.4, 10.0, "TEST_SIGNAL")

    monkeypatch.setattr("bot.executor.daily_limit_check", lambda: type("Gate", (), {"allowed": True, "reason": ""})())
    monkeypatch.setattr("bot.executor.max_drawdown_gate", lambda: type("Gate", (), {"allowed": True, "reason": ""})())
    monkeypatch.setattr("bot.executor.pair_lock.check", lambda slug: type("Gate", (), {"allowed": True, "reason": ""})())
    monkeypatch.setattr("bot.executor.gate_intent", lambda *args, **kwargs: type("Gate", (), {"allowed": True, "reason": ""})())

    fills = executor.execute([intent])

    assert fills[0].simulated is True
    fill_entry = next(entry for entry in ledger._entries if entry.kind == "fill")
    assert fill_entry.reason == "SIMULATED_FILL"
    assert fill_entry.meta["original_reason"] == "TEST_SIGNAL"


def test_reconcile_returns_confirmed_partial_fill(monkeypatch):
    monkeypatch.setattr(cfg, "live_order_timeout_sec", 1.0)
    client = FakeClient([{"status": "OPEN"}, {"status": "MATCHED", "size_matched": 3, "avg_price": 0.42}])
    executor = executor_with(client)

    assert executor._reconcile_order("order-1") == ("MATCHED", 3.0, 0.42)
    assert client.cancelled == []


def test_reconcile_cancels_unknown_order_on_timeout(monkeypatch):
    monkeypatch.setattr(cfg, "live_order_timeout_sec", 0.0)
    client = FakeClient([{}])
    executor = executor_with(client)

    assert executor._reconcile_order("order-2") == ("CANCELLED", 0.0, 0.0)
    assert client.cancelled == ["order-2"]
