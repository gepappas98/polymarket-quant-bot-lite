import pytest

from bot.executor import LiveExecutor
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
