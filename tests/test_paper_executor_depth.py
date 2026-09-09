import pytest

from bot.feeds import OrderBook
from bot.executor import PaperExecutor
from bot.strategy import Intent, Side, Strategy


@pytest.fixture(autouse=True)
def isolate_ledger(monkeypatch):
    monkeypatch.setattr("bot.executor.ledger.record_intent", lambda *args, **kwargs: None)
    allowed = lambda *args, **kwargs: type("Gate", (), {"allowed": True, "reason": ""})()
    monkeypatch.setattr("bot.executor.daily_limit_check", allowed)
    monkeypatch.setattr("bot.executor.max_drawdown_gate", allowed)
    monkeypatch.setattr("bot.executor.pair_lock.check", allowed)
    monkeypatch.setattr("bot.executor.gate_intent", allowed)
    monkeypatch.setattr("bot.executor.ledger.record_fill", lambda *args, **kwargs: None)
    monkeypatch.setattr("bot.executor._record_pair_states", lambda *args, **kwargs: None)


def test_paper_executor_requires_observed_depth(monkeypatch):
    from bot.gates import cooldown

    executor = PaperExecutor(Strategy())
    intent = Intent("market", "token", Side.UP, "BUY", 0.5, 20, "test")
    cooldown.clear(intent.market_slug)

    fills = executor.execute([intent])

    assert fills == []
    assert cooldown.get_until(intent.market_slug) is None


def test_paper_executor_consumes_only_available_depth():
    from bot.gates import cooldown

    executor = PaperExecutor(Strategy())
    state = type("State", (), {})()
    state.market = {"slug": "market"}
    state.up_book = OrderBook([], [{"price": "0.5", "size": "10"}])
    state.down_book = OrderBook([], [])
    executor._books["market"] = state
    intent = Intent("market", "token", Side.UP, "BUY", 0.5, 20, "test")
    cooldown.clear(intent.market_slug)

    fills = executor.execute([intent])

    assert len(fills) == 1
    assert fills[0].cost == pytest.approx(5)
    assert fills[0].shares == pytest.approx(10)
    assert cooldown.get_until(intent.market_slug) is not None
