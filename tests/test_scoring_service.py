from app.services.scoring_service import compute_leader_scores, hampel_filter, refresh_leaderboard
from app.core import database
from app.models.leader import Leader


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
