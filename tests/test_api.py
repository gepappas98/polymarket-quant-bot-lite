from fastapi.testclient import TestClient
from app.main import app


def test_api_shapes_and_updates():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"ok": True}
        assert client.get("/api/status").status_code == 200
        assert client.post("/api/sizing/calculate", json={"confidence": .6, "odds": 2, "category": "crypto", "balance": 100}).status_code == 200
        assert client.post("/api/risk/update", json={"enable_category_ceiling": True}).status_code == 200
        assert client.get("/api/risk").json()["enable_category_ceiling"] is True
        assert client.post("/api/strategies/update", json={"politics_only": True}).status_code == 200
        assert client.get("/api/strategies").json()["politics_only"] is True
        assert client.post("/api/leaders/refresh?sync=true").status_code == 200
        assert client.get("/api/leaders").status_code == 200


def test_place_order_respects_strategy():
    with TestClient(app) as client:
        client.post("/api/strategies/update", json={"politics_only": True})
        ignored = client.post("/api/trades/place", json={"market_slug": "btc-up-or-down", "token_id": "t", "side": "UP", "price": .5, "confidence": .8, "balance": 100})
        assert ignored.json()["status"] == "ignored"
