from app.core import database
from app.models.leader import Leader
from app.services.scoring_service import (
    compute_leader_scores,
    enrich_leaderboard_history,
    hampel_filter,
    refresh_leaderboard,
)


def test_hampel_filter():
    cleaned, indices = hampel_filter([1, 1.1, 1.2, 100, 1.0])
    assert cleaned[3] != 100
    assert indices == [3]
    assert hampel_filter([1, 2, 3])[0] == [1, 2, 3]


def test_scores_rank_and_refresh():
    scores = compute_leader_scores({
        "good": [{"pnl": 10, "size": 10, "ts": 1}, {"pnl": 5, "size": 10, "ts": 2}],
        "bad": [{"pnl": -5, "size": 10, "ts": 1}, {"pnl": 1, "size": 10, "ts": 2}],
    })
    assert scores[0]["address"] == "good"
    assert scores[0]["win_rate"] == 100
    with database.SessionLocal() as db:
        first = refresh_leaderboard(db, {"a": [{"pnl": 1, "size": 1, "ts": 1}], "b": [{"pnl": -1, "size": 1, "ts": 1}]})
        count = db.query(Leader).count()
        second = refresh_leaderboard(db, {"a": [{"pnl": 1, "size": 1, "ts": 1}], "b": [{"pnl": -1, "size": 1, "ts": 1}]})
        assert len(first) == len(second) == count


def test_enrichment_uses_closed_positions_and_keeps_failed_aggregate(monkeypatch):
    monkeypatch.setenv("LEADERBOARD_ENRICH_HISTORY", "true")
    monkeypatch.setenv("LEADERBOARD_HISTORY_TRADER_LIMIT", "2")
    monkeypatch.setenv("LEADERBOARD_HISTORY_POSITION_LIMIT", "10")
    aggregate = {
        "0xgood": [{"pnl": 9, "size": 100, "ts": 1, "source": "leaderboard_aggregate"}],
        "0xfail": [{"pnl": -3, "size": 50, "ts": 2, "source": "leaderboard_aggregate"}],
    }
    calls = []

    def fetcher(*, address, limit):
        calls.append((address, limit))
        if address == "0xfail":
            raise RuntimeError("upstream unavailable")
        return [
            {"pnl": 3, "size": 10, "ts": 30, "source": "closed_position"},
            {"pnl": -1, "size": 10, "ts": 20, "source": "closed_position"},
        ]

    enriched = enrich_leaderboard_history(aggregate, fetcher=fetcher)

    assert calls == [("0xgood", 10), ("0xfail", 10)]
    assert enriched["0xgood"] == [
        {"pnl": 3, "size": 10, "ts": 30, "source": "closed_position"},
        {"pnl": -1, "size": 10, "ts": 20, "source": "closed_position"},
    ]
    assert enriched["0xfail"] == aggregate["0xfail"]

    scores = {row["address"]: row for row in compute_leader_scores(enriched)}
    assert scores["0xgood"]["trade_count"] == 2
    assert scores["0xgood"]["win_rate"] == 50
    assert scores["0xgood"]["max_drawdown"] == 0


def test_enrichment_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LEADERBOARD_ENRICH_HISTORY", "false")
    aggregate = {"0xabc": [{"pnl": 1, "size": 10, "ts": 1}]}

    def fail_if_called(**_):
        raise AssertionError("history fetcher should not be called")

    assert enrich_leaderboard_history(aggregate, fetcher=fail_if_called) == aggregate
