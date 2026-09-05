import pytest

from bot.backtest import BacktestFill, Snapshot, _simulate_maker, _simulate_taker
from bot.config import cfg
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
