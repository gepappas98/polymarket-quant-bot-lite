import pytest

from bot.backtest import (
    BacktestFill,
    PairRecord,
    Snapshot,
    _build_pair_records,
    _real_paper_fill,
    _simulate_maker,
    _simulate_taker,
    run_backtest,
)
from bot.config import cfg
from bot.execution import PaperFillEngine
from bot.strategy import Intent, Side


def test_taker_consumes_multiple_ask_levels(monkeypatch):
    monkeypatch.setattr(cfg, "paper_fee_bps", 10.0)
    intent = Intent("m", "token", Side.UP, "BUY", 0.49, 25.0, "TEST")
    snap = Snapshot(1.0, {"slug": "m"}, up_asks=[{"price": "0.49", "size": "20"}, {"price": "0.50", "size": "20"}, {"price": "0.51", "size": "20"}])
    fill = _simulate_taker(intent, snap, {})
    assert fill is not None
    assert fill.size_usd == pytest.approx(25.0)
    assert fill.price == pytest.approx(0.498046875)
    assert fill.fee_usd == pytest.approx(0.025)
    assert fill.slippage_usd == pytest.approx(0.4039215686)


def test_maker_is_not_guaranteed(monkeypatch):
    monkeypatch.setattr(cfg, "maker_fill_probability", 0.0)
    intent = Intent("m", "token", Side.UP, "BUY", 0.49, 25.0, "TEST")
    snap = Snapshot(1.0, {"slug": "m"}, up_bids=[{"price": "0.49", "size": "100"}])
    assert _simulate_maker(intent, snap, __import__("random").Random(0)) is None


def test_fill_reports_net_costs():
    fill = BacktestFill(1.0, "m", "UP", 0.5, 25.0, "SIMULATED_FILL", fee_usd=0.1, slippage_usd=0.2)
    assert fill.net_pnl_usd == pytest.approx(-0.3)


# --- P0-8: one fill per book level per snapshot -----------------------------

def test_taker_shared_consumed_dict_blocks_second_intent_same_touch():
    """Two intents in the same snapshot must not each drain the full
    displayed size at the same touch (roadmap P0-4)."""
    snap = Snapshot(1.0, {"slug": "m"}, up_asks=[{"price": "0.49", "size": "20"}])
    consumed: dict = {}
    first = Intent("m", "token", Side.UP, "BUY", 0.49, 9.8, "TEST")
    second = Intent("m", "token", Side.UP, "BUY", 0.49, 9.8, "TEST")
    fill1 = _simulate_taker(first, snap, consumed)
    fill2 = _simulate_taker(second, snap, consumed)
    assert fill1 is not None and fill1.size_usd == pytest.approx(9.8)
    # 20 shares @ 0.49 = $9.80 available total; first intent already took it all.
    assert fill2 is None


def test_maker_shared_consumed_dict_blocks_second_intent_same_touch(monkeypatch):
    monkeypatch.setattr(cfg, "maker_fill_probability", 1.0)
    monkeypatch.setattr(cfg, "maker_queue_ahead", 0.0)
    snap = Snapshot(1.0, {"slug": "m"}, up_bids=[{"price": "0.49", "size": "20"}])
    consumed: dict = {}
    rng = __import__("random").Random(0)
    first = Intent("m", "token", Side.UP, "BUY", 0.49, 9.8, "TEST")
    second = Intent("m", "token", Side.UP, "BUY", 0.49, 9.8, "TEST")
    fill1 = _simulate_maker(first, snap, rng, consumed)
    fill2 = _simulate_maker(second, snap, rng, consumed)
    assert fill1 is not None and fill1.size_usd == pytest.approx(9.8)
    assert fill2 is None


def test_real_paper_fill_shared_consumed_dict_blocks_second_intent_same_touch():
    """Regression test for the run_real_backtest bug: previously each call
    rebuilt a fresh, undepleted book from the raw snapshot, so two intents
    against the same snapshot could each claim the full touch."""
    engine = PaperFillEngine(fee_bps=0.0, slippage_bps=0.0)
    snap = Snapshot(1.0, {"slug": "m"}, up_asks=[{"price": "0.49", "size": "20"}])
    consumed: dict = {}
    first = Intent("m", "token", Side.UP, "BUY", 0.49, 9.8, "TEST")
    second = Intent("m", "token", Side.UP, "BUY", 0.49, 9.8, "TEST")
    fills1 = _real_paper_fill(first, snap, engine, consumed)
    fills2 = _real_paper_fill(second, snap, engine, consumed)
    total_filled = sum(f.size_usd for f in fills1) + sum(f.size_usd for f in fills2)
    # 20 shares @ 0.49 = $9.80 of real liquidity in this snapshot, full stop —
    # no matter how many intents draw on it in the same snapshot.
    assert total_filled == pytest.approx(9.8)
    assert not fills2


# --- P0-8: net-after-execution pair reporting -------------------------------

def test_build_pair_records_complete_pair_computes_net_edge():
    up = Intent("m", "u", Side.UP, "BUY", 0.48, 25.0, "ARB pair (sum=0.9700)", is_arb_leg=True, set_id="m:set:1")
    down = Intent("m", "d", Side.DOWN, "BUY", 0.49, 25.0, "ARB pair (sum=0.9700)", is_arb_leg=True, set_id="m:set:1")
    up_fill = BacktestFill(1.0, "m", "UP", 0.48, 25.0, "SIMULATED_FILL", fee_usd=0.05, slippage_usd=0.02)
    down_fill = BacktestFill(1.0, "m", "DOWN", 0.49, 25.0, "SIMULATED_FILL", fee_usd=0.05, slippage_usd=0.02)
    records = _build_pair_records(
        [up, down], {id(up): up_fill, id(down): down_fill}, ts=1.0, data_source="LEGACY_SNAPSHOT_INPUT",
    )
    assert len(records) == 1
    pair = records[0]
    assert pair.state == "PAIR_COMPLETE"
    assert pair.set_id == "m:set:1"
    assert pair.legs == 2 and pair.filled_legs == 2
    assert pair.exec_up == pytest.approx(0.48)
    assert pair.exec_down == pytest.approx(0.49)
    assert pair.gross_edge == pytest.approx(1.0 - 0.48 - 0.49)
    expected_net = pair.gross_edge - (0.14 / 50.0)  # (fees+slippage)/filled_usd
    assert pair.net_edge == pytest.approx(expected_net)
    assert pair.fill_ratio == pytest.approx(1.0)
    assert pair.residual_usd == pytest.approx(0.0)
    assert pair.execution_mode == "PAPER_SIMULATION"


def test_build_pair_records_partial_pair_makes_no_edge_claim():
    """A leg that didn't fill (limit/depth) must never be reported as a
    profitable arb — no gross_edge/net_edge for PAIR_PARTIAL."""
    up = Intent("m", "u", Side.UP, "BUY", 0.48, 25.0, "ARB pair (sum=0.9700)", is_arb_leg=True, set_id="m:set:2")
    down = Intent("m", "d", Side.DOWN, "BUY", 0.49, 25.0, "ARB pair (sum=0.9700)", is_arb_leg=True, set_id="m:set:2")
    up_fill = BacktestFill(1.0, "m", "UP", 0.48, 25.0, "SIMULATED_FILL")
    records = _build_pair_records(
        [up, down], {id(up): up_fill}, ts=1.0, data_source="LEGACY_SNAPSHOT_INPUT",
    )
    assert len(records) == 1
    pair = records[0]
    assert pair.state == "PAIR_PARTIAL"
    assert pair.filled_legs == 1 and pair.legs == 2
    assert pair.gross_edge is None
    assert pair.net_edge is None
    assert pair.residual_usd == pytest.approx(25.0)
    assert pair.fill_ratio == pytest.approx(0.5)


def test_build_pair_records_failed_pair_makes_no_edge_claim():
    up = Intent("m", "u", Side.UP, "BUY", 0.48, 25.0, "ARB pair (sum=0.9700)", is_arb_leg=True, set_id="m:set:3")
    down = Intent("m", "d", Side.DOWN, "BUY", 0.49, 25.0, "ARB pair (sum=0.9700)", is_arb_leg=True, set_id="m:set:3")
    records = _build_pair_records([up, down], {}, ts=1.0, data_source="LEGACY_SNAPSHOT_INPUT")
    assert len(records) == 1
    pair = records[0]
    assert pair.state == "PAIR_FAILED"
    assert pair.filled_legs == 0
    assert pair.gross_edge is None
    assert pair.net_edge is None
    assert pair.fill_ratio == pytest.approx(0.0)
    assert pair.residual_usd == pytest.approx(50.0)


def test_build_pair_records_ignores_non_arb_intents():
    """SET_ACCUM/SECOND_SIDE/directional legs are not simultaneous pairs and
    must not be reported as PairRecords."""
    solo = Intent("m", "u", Side.UP, "BUY", 0.48, 25.0, "SET_ACCUM sum=0.9700 leg=UP", is_arb_leg=True)
    records = _build_pair_records([solo], {}, ts=1.0, data_source="LEGACY_SNAPSHOT_INPUT")
    assert records == []


def test_run_backtest_records_complete_pair_and_stamps_simulated(monkeypatch):
    monkeypatch.setattr(cfg, "prefer_maker", False)
    monkeypatch.setattr(cfg, "max_order_usd", 25.0)
    monkeypatch.setattr(cfg, "paper_fee_bps", 10.0)
    snap = Snapshot(
        ts=1.0,
        market={"slug": "btc-updown-5m-1", "asset": "BTC", "up_token_id": "u", "down_token_id": "d"},
        up_asks=[{"price": "0.48", "size": "100"}],
        down_asks=[{"price": "0.49", "size": "100"}],
        up_bids=[{"price": "0.47", "size": "100"}],
        down_bids=[{"price": "0.48", "size": "100"}],
    )
    result = run_backtest([snap])
    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.state == "PAIR_COMPLETE"
    assert pair.exec_up == pytest.approx(0.48)
    assert pair.exec_down == pytest.approx(0.49)
    assert pair.gross_edge == pytest.approx(1 - 0.48 - 0.49)
    assert pair.net_edge is not None and pair.net_edge < pair.gross_edge
    assert "SIMULATED — not live expectancy." in result.summary()
