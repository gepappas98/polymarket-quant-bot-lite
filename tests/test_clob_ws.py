import json
import time

from bot.clob_ws import ClobWebSocketFeed


def test_book_snapshot_and_incremental_price_change():
    feed = ClobWebSocketFeed(stale_after_sec=60)
    feed.apply_message({
        "event_type": "book",
        "asset_id": "up",
        "bids": [{"price": "0.44", "size": "10"}],
        "asks": [{"price": "0.45", "size": "8"}],
    })
    assert feed.get_book("up").best_bid == 0.44
    assert feed.get_book("up").best_ask == 0.45

    feed.apply_message({
        "event_type": "price_change",
        "price_changes": [
            {"asset_id": "up", "price": "0.44", "size": "0", "side": "BUY"},
            {"asset_id": "up", "price": "0.45", "size": "0", "side": "SELL"},
            {"asset_id": "up", "price": "0.46", "size": "5", "side": "SELL"},
        ],
    })
    book = feed.get_book("up")
    assert book.best_bid is None
    assert book.best_ask == 0.46


def test_stale_book_is_not_used():
    feed = ClobWebSocketFeed(stale_after_sec=0.01)
    feed.apply_message({"event_type": "book", "asset_id": "up", "bids": [], "asks": []})
    time.sleep(0.02)
    assert feed.get_book("up") is None


def test_subscription_payload_contains_public_market_channel():
    sent = []

    class FakeSocket:
        def send(self, value):
            sent.append(value)

    feed = ClobWebSocketFeed()
    feed.set_assets(["down", "up"])
    feed._send_subscription(FakeSocket())
    payload = json.loads(sent[0])
    assert payload["type"] == "market"
    assert payload["assets_ids"] == ["down", "up"]
    assert payload["initial_dump"] is True
    assert payload["custom_feature_enabled"] is True
