from dataclasses import dataclass

from bot.strategies.copy_trading import CopyTradingConfig, CopyTradingStrategy


@dataclass
class Response:
    payload: object
    status_code: int = 200

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class State:
    market = {
        "slug": "btc-updown-5m-1",
        "asset": "BTC",
        "up_token_id": "up-token",
        "down_token_id": "down-token",
    }
    up_ask = 0.45
    down_ask = 0.55


def config(**overrides):
    values = dict(
        enabled=True,
        target_wallets=["0xwallet"],
        size_multiplier=1.0,
        min_target_trade_usd=10.0,
        min_target_trades=100,
        min_history_days=30,
        max_price_move_after_target=0.02,
        poll_interval_sec=0,
        max_trade_age_sec=120,
        http_timeout=1,
    )
    values.update(overrides)
    return CopyTradingConfig(**values)


def test_short_new_trade_page_does_not_false_negative_separate_history(monkeypatch):
    now = 2_000_000_000
    history = [{"timestamp": now - 31 * 86400, "id": f"history-{i}"} for i in range(100)]
    activity = [{
        "id": "new-1", "timestamp": now - 10, "side": "BUY", "asset": "up-token",
        "usdcSize": 100, "price": 0.44, "currentPrice": 0.45,
    }]
    calls = []

    def get(url, params, timeout):
        calls.append((url, params))
        if url.endswith("/trades"):
            return Response(history)
        return Response(activity)

    monkeypatch.setattr("bot.strategies.copy_trading.requests.get", get)
    monkeypatch.setattr("bot.strategies.copy_trading.time.time", lambda: now)
    strategy = CopyTradingStrategy(config())

    intents = strategy.evaluate(State())

    assert len(intents) == 1
    assert intents[0].token_id == "up-token"
    assert intents[0].size_usd == 25.0
    assert any(url.endswith("/trades") for url, _ in calls)
    assert any(url.endswith("/activity") and params["limit"] == 20 for url, params in calls)


def test_missing_history_fails_closed_and_surfaces_skip_reason(monkeypatch):
    def get(url, params, timeout):
        raise OSError("history unavailable")

    monkeypatch.setattr("bot.strategies.copy_trading.requests.get", get)
    strategy = CopyTradingStrategy(config())

    assert strategy.evaluate(State()) == []
    assert strategy.skip_reason == "history_fetch_failed:0xwallet"


def test_duplicate_trade_id_is_not_replayed(monkeypatch):
    now = 2_000_000_000
    history = [{"timestamp": now - 31 * 86400, "id": f"history-{i}"} for i in range(100)]
    activity = [{
        "id": "same-trade", "timestamp": now - 10, "side": "BUY", "asset": "up-token",
        "usdcSize": 20, "price": 0.44, "currentPrice": 0.45,
    }]
    monkeypatch.setattr(
        "bot.strategies.copy_trading.requests.get",
        lambda url, params, timeout: Response(history if url.endswith("/trades") else activity),
    )
    monkeypatch.setattr("bot.strategies.copy_trading.time.time", lambda: now)
    strategy = CopyTradingStrategy(config())

    assert len(strategy.evaluate(State())) == 1
    assert strategy.evaluate(State()) == []


def test_only_buy_tracked_tokens_and_max_order_cap(monkeypatch):
    now = 2_000_000_000
    history = [{"timestamp": now - 31 * 86400, "id": f"history-{i}"} for i in range(100)]
    activity = [
        {"id": "sell", "timestamp": now - 10, "side": "SELL", "asset": "up-token", "usdcSize": 100, "price": 0.4, "currentPrice": 0.4},
        {"id": "untracked", "timestamp": now - 10, "side": "BUY", "asset": "other-token", "usdcSize": 100, "price": 0.4, "currentPrice": 0.4},
        {"id": "buy", "timestamp": now - 10, "side": "BUY", "asset": "down-token", "usdcSize": 1000, "price": 0.5, "currentPrice": 0.5},
    ]
    monkeypatch.setattr(
        "bot.strategies.copy_trading.requests.get",
        lambda url, params, timeout: Response(history if url.endswith("/trades") else activity),
    )
    monkeypatch.setattr("bot.strategies.copy_trading.time.time", lambda: now)
    strategy = CopyTradingStrategy(config(size_multiplier=1.0))

    intents = strategy.evaluate(State())

    assert len(intents) == 1
    assert intents[0].action == "BUY"
    assert intents[0].token_id == "down-token"
    assert intents[0].size_usd == 25.0
