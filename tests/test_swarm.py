import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.swarm import AgentScore, consensus, score_market_state, filter_intents, SwarmConfig


def test_consensus_pass():
    scores = [
        AgentScore("NORO", 0.9),
        AgentScore("ZEPHR", 0.85),
        AgentScore("OKAPI", 0.8),
        AgentScore("TIDAL", 0.9),
        AgentScore("VESKA", 0.9),
        AgentScore("MARIN", 0.85),
        AgentScore("LUMEN", 0.5),
        AgentScore("RUNE", 1.0, veto=False),
    ]
    r = consensus(scores, threshold=0.70)
    assert r.ok
    assert r.consensus >= 0.70


def test_rune_veto():
    scores = [
        AgentScore("NORO", 1.0),
        AgentScore("RUNE", 0.0, veto=True, reason="daily limit"),
    ]
    r = consensus(scores, threshold=0.50)
    assert not r.ok
    assert "RUNE" in r.veto_by


def test_below_threshold():
    scores = [AgentScore("NORO", 0.2), AgentScore("ZEPHR", 0.2), AgentScore("TIDAL", 0.2)]
    r = consensus(scores, threshold=0.70)
    assert not r.ok


class _Book:
    mid = 0.48
    best_ask = 0.49


class _State:
    market = {"slug": "btc-test", "asset": "BTC"}
    up_ask = 0.49
    down_ask = 0.48
    sum_asks = 0.97
    up_book = _Book()
    down_book = _Book()
    fair_up_prob = 0.62
    market_key = "btc-test"


def test_score_market_state():
    s = score_market_state(_State(), risk_veto=False)
    names = {x.name for x in s}
    assert "TIDAL" in names and "NORO" in names and "RUNE" in names


def test_filter_disabled():
    intents = ["x"]
    out = filter_intents(intents, _State(), cfg=SwarmConfig(enabled=False))
    assert out == intents
