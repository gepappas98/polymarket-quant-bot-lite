from app.services.leaderboard_adapter import fetch_polymarket_leaderboard


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


def test_public_leaderboard_rows_are_normalized():
    client = FakeClient([
        {"rank": "1", "proxyWallet": "0xabc", "pnl": "125.50", "vol": "1000.25", "userName": "alice", "verifiedBadge": True},
        {"rank": "2", "wallet": "0xdef", "pnl": -10, "vol": 200},
        {"rank": "3", "pnl": 1, "vol": 20},
    ])

    history = fetch_polymarket_leaderboard(category="crypto", time_period="month", limit=999, client=client)

    assert set(history) == {"0xabc", "0xdef"}
    assert history["0xabc"][0]["pnl"] == 125.5
    assert history["0xabc"][0]["size"] == 1000.25
    assert history["0xabc"][0]["verified_badge"] is True
    assert client.calls[0][1] == {"category": "CRYPTO", "timePeriod": "MONTH", "orderBy": "PNL", "limit": 50, "offset": 0}


def test_non_list_payload_is_rejected():
    client = FakeClient({"data": []})
    try:
        fetch_polymarket_leaderboard(client=client)
    except ValueError as exc:
        assert "JSON list" in str(exc)
    else:
        raise AssertionError("expected malformed payload to be rejected")
