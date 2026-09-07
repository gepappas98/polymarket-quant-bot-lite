import pytest

from bot.execution import OrderBook
from bot.executor import PaperExecutor
from bot.strategy import Intent, Side, Strategy


@pytest.fixture(autouse=True)
def isolate_ledger(monkeypatch):
    monkeypatch.setattr("bot.executor.ledger.record_intent", lambda *args, **kwargs: None)
    monkeypatch.setattr("bot.executor.ledger.record_fill", lambda *args, **kwargs: None)
    monkeypatch.setattr("bot.executor._record_pair_states", lambda *args, **kwargs: None)


def test_paper_executor_requires_observed_depth(monkeypatch):
    executor = PaperExecutor(Strategy())
    intent = Intent("market", "token", Side.UP, "BUY", 0.5, 20, "test")

    fills = executor.execute([intent])

    assert fills == []


def test_paper_executor_consumes_only_available_depth():
    executor = PaperExecutor(Strategy())
    state = type("State", (), {})()
    state.market = {"slug": "market"}
    state.up_book = OrderBook.from_levels([], [{"price": 0.5, "size": 10}])
    state.down_book = OrderBook.from_levels([], [])
    executor._books["market"] = state
    intent = Intent("market", "token", Side.UP, "BUY", 0.5, 20, "test")

    fills = executor.execute([intent])

    assert len(fills) == 1
    assert fills[0].cost == pytest.approx(5)
    assert fills[0].shares == pytest.approx(10)
