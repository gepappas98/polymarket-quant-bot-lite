import pytest

from bot.executor import LiveExecutor, PaperExecutor, ShadowExecutor
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


def test_shadow_mode_factory_never_uses_live_client(monkeypatch):
    monkeypatch.setattr(cfg, "mode", "shadow")
    from bot.executor import create_executor
    executor = create_executor(object())
    assert isinstance(executor, ShadowExecutor)
    assert not hasattr(executor, "client")


def test_shadow_observes_live_book_without_submitting_orders():
    class Book:
        _asks = [{"price": "0.49", "size": "10"}, {"price": "0.50", "size": "20"}]

    class State:
        up_book = Book()
        down_book = Book()
        up_ask = 0.49
        down_ask = 0.49
        sum_asks = 0.98
        arb_available = True
        external_price = 100.0
        market = {"slug": "shadow-market"}

    ledger._entries.clear()
    shadow = ShadowExecutor(object())
    intent = Intent("shadow-market", "token", Side.UP, "BUY", 0.49, 15.0, "SHADOW_SIGNAL")

    fills = shadow.observe(State(), [intent])

    assert len(fills) == 1
    assert fills[0].cost == pytest.approx(14.9)
    assert fills[0].avg_price == pytest.approx(14.9 / 30.0)
    assert any(entry.kind == "shadow_observation" for entry in ledger._entries)
    assert all(entry.meta.get("shadow") for entry in ledger._entries if entry.kind == "fill")


def test_reconcile_polls_partial_until_filled(monkeypatch):
    monkeypatch.setattr(cfg, "live_order_timeout_sec", 1.0)
    client = FakeClient([
        {"status": "PARTIAL", "size_matched": 35, "avg_price": 0.42},
        {"status": "FILLED", "size_matched": 100, "avg_price": 0.43},
    ])
    executor = executor_with(client)

    assert executor._reconcile_order("order-1") == ("FILLED", 100.0, 0.43)
    assert client.cancelled == []


def test_reconcile_cancels_partial_remainder_and_confirms(monkeypatch):
    monkeypatch.setattr(cfg, "live_order_timeout_sec", 0.0)
    client = FakeClient([
        {"status": "PARTIAL", "size_matched": 35, "avg_price": 0.42},
        {"status": "CANCELED", "size_matched": 35, "avg_price": 0.42},
    ])
    executor = executor_with(client)

    assert executor._reconcile_order("order-partial") == ("CANCELED", 35.0, 0.42)
    assert client.cancelled == ["order-partial"]


def test_reconcile_uses_vwap_and_never_price_fallback(monkeypatch):
    assert LiveExecutor._verified_average({"fills": [{"price": "0.4", "size": "2"}, {"price": "0.6", "size": "1"}]}) == pytest.approx(0.4666667)
    assert LiveExecutor._verified_average({"price": 0.5}) == 0.0


def test_reconcile_cancels_unknown_order_on_timeout(monkeypatch):
    monkeypatch.setattr(cfg, "live_order_timeout_sec", 0.0)
    client = FakeClient([{}])
    executor = executor_with(client)

    assert executor._reconcile_order("order-2") == ("CANCEL_UNCONFIRMED", 0.0, 0.0)
    assert client.cancelled == ["order-2"]
