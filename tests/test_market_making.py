from bot.strategies.market_making import MarketMakingConfig, MarketMakingStrategy
from bot.strategy import Strategy


class Book:
    best_bid = 0.45
    mid = 0.50


class State:
    market = {
        "slug": "btc-updown-5m-mm",
        "asset": "BTC",
        "up_token_id": "up-token",
        "down_token_id": "down-token",
    }
    # The calculated UP quote is 0.48 and crosses this ask immediately.
    up_ask = 0.47
    down_ask = 0.53
    up_book = Book()
    down_book = Book()


def test_market_making_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MM_ENABLED", raising=False)
    assert MarketMakingConfig().enabled is False


def test_crossing_quote_is_labeled_as_taker_not_resting_maker():
    strategy = MarketMakingStrategy(
        Strategy(),
        MarketMakingConfig(enabled=True, requote_interval_sec=0, quote_size_usd=10),
    )

    intents = strategy.evaluate(State())

    assert len(intents) == 1
    assert intents[0].reason.startswith("MM_TAKE")
    assert "taker quote, not resting maker" in intents[0].reason
