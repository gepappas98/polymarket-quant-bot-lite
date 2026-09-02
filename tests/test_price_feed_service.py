from app.core import database
from app.models.trade import Trade
from app.services.price_feed_service import (
    fetch_clob_midpoint,
    update_open_trade_prices,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params):
        self.calls.append((url, params))
        return FakeResponse(self.payload)


def test_fetch_clob_midpoint_normalizes_supported_payload():
    client = FakeClient({"mid": "0.47"})

    assert fetch_clob_midpoint("token-1", client=client, endpoint="https://clob.test/midpoint") == 0.47
    assert client.calls == [("https://clob.test/midpoint", {"token_id": "token-1"})]


def test_fetch_clob_midpoint_rejects_invalid_price_and_empty_token():
    assert fetch_clob_midpoint("", client=FakeClient({"mid": 0.5})) is None
    assert fetch_clob_midpoint("token-1", client=FakeClient({"mid": "1.2"})) is None
    assert fetch_clob_midpoint("token-1", client=FakeClient({"unexpected": 0.5})) is None


def test_update_open_trade_prices_routes_price_to_trailing_stop():
    client = FakeClient({"mid": "0.49"})
    with database.SessionLocal() as db:
        trade = Trade(
            market_slug="btc-up-or-down",
            token_id="up-token",
            category="crypto",
            side="UP",
            entry_price=0.5,
            size_usd=10,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)

        updates = update_open_trade_prices(db=db, client=client)
        db.refresh(trade)

        assert len(updates) == 1
        assert updates[0].trade_id == trade.id
        assert updates[0].status == "held"
        assert trade.current_price == 0.49
        assert client.calls == [("https://clob.polymarket.com/midpoint", {"token_id": "up-token"})]


def test_update_open_trade_prices_skips_missing_midpoint():
    client = FakeClient({"mid": None})
    with database.SessionLocal() as db:
        trade = Trade(
            market_slug="btc-up-or-down",
            token_id="down-token",
            category="crypto",
            side="DOWN",
            entry_price=0.5,
            size_usd=10,
        )
        db.add(trade)
        db.commit()

        assert update_open_trade_prices(db=db, client=client) == []
