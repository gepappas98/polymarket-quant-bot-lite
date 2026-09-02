import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.ledger import Ledger, LedgerEntry
from bot.strategy import Intent, Side, Strategy
from bot.swarm import consensus, AgentScore
from bot import status_server


def test_record_fill_stores_swarm_and_set_id(tmp_path):
    led = Ledger(path=tmp_path / "t.jsonl")
    intent = Intent(
        market_slug="btc-x",
        token_id="t1",
        side=Side.UP,
        action="BUY",
        price=0.45,
        size_usd=10,
        reason="ARB",
        is_arb_leg=True,
    )
    intent.set_id = "btc-x:set:1"
    intent.swarm = consensus([
        AgentScore("NORO", 0.9),
        AgentScore("ZEPHR", 0.85),
        AgentScore("TIDAL", 0.9),
        AgentScore("OKAPI", 0.8),
        AgentScore("VESKA", 0.9),
        AgentScore("MARIN", 0.85),
        AgentScore("LUMEN", 0.5),
    ], threshold=0.5).as_dict()
    led.record_fill(intent, shares=20, cost=9.0, order_id="oid", dry_run=True)
    e = led._entries[-1]
    assert e.meta["set_id"] == "btc-x:set:1"
    assert e.meta["swarm"]["ok"] is True
    assert "consensus" in e.meta["swarm"]


def test_status_swarm_from_ledger(tmp_path, monkeypatch):
    led = Ledger(path=tmp_path / "t2.jsonl")
    intent = Intent(
        market_slug="eth-x",
        token_id="t2",
        side=Side.DOWN,
        action="BUY",
        price=0.5,
        size_usd=8,
        reason="SET_ACCUM",
        is_arb_leg=True,
    )
    intent.set_id = "eth-x:set:3"
    intent.swarm = {"ok": True, "consensus": 0.81, "threshold": 0.7, "scores": {
        "NORO": {"score": 0.9, "veto": False, "reason": "x"},
        "RUNE": {"score": 1.0, "veto": False, "reason": "ok"},
    }, "detail": "pass", "veto_by": []}
    led.record_fill(intent, 16, 8.0, "o2", True)
    monkeypatch.setattr(status_server, "ledger", led)
    snap = status_server._swarm_from_ledger()
    assert snap["last"]["consensus"] == 0.81
    assert snap["agents"]["NORO"]["score"] == 0.9
    rows = status_server._ledger_rows()
    assert rows[0]["setId"] == "eth-x:set:3"
    assert rows[0]["consensus"] == 0.81


def test_strategy_assigns_set_id():
    s = Strategy()
    a = s.next_set_id("m1")
    b = s.next_set_id("m1")
    assert a != b
    assert a.startswith("m1:set:")
