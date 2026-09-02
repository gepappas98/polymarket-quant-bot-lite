"""Unit tests for v0.5 inventory / complete-set accounting."""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.inventory import InventoryBook, MarketInventory


def test_paired_and_residual():
    inv = MarketInventory()
    inv.apply_fill("UP", shares=100, cost_usd=40, price=0.40)
    inv.apply_fill("DOWN", shares=60, cost_usd=30, price=0.50)
    assert inv.paired_shares == 60
    assert inv.residual_shares == 40
    assert inv.residual_side == "UP"
    assert abs(inv.avg_set_cost - (0.40 + 0.50)) < 1e-9
    assert abs(inv.edge_per_set - 0.10) < 1e-9


def test_second_side_lag():
    inv = MarketInventory()
    inv.apply_fill("UP", shares=50, cost_usd=25, price=0.50, ts=time.time() - 30)
    # residual UP for 30s → should request DOWN
    need = inv.needs_second_side(max_lag_sec=15, max_naked_usd=100)
    assert need == "DOWN"
    # pair it
    inv.apply_fill("DOWN", shares=50, cost_usd=24, price=0.48)
    assert inv.residual_side is None
    assert inv.needs_second_side(max_lag_sec=15, max_naked_usd=100) is None


def test_naked_usd_trigger():
    inv = MarketInventory()
    inv.apply_fill("DOWN", shares=200, cost_usd=80, price=0.40)  # large naked
    need = inv.needs_second_side(max_lag_sec=9999, max_naked_usd=40)
    assert need == "UP"


def test_inventory_book():
    book = InventoryBook()
    book.apply_fill("m1", "UP", 10, 5, 0.5)
    book.apply_fill("m1", "DOWN", 10, 4.5, 0.45)
    snap = book.get("m1").snapshot()
    assert snap["paired_shares"] == 10
    assert snap["avg_set_cost"] == 0.95
    assert snap["edge_per_set"] == 0.05


def test_strategy_imports():
    from bot.strategy import Strategy, Side
    s = Strategy()
    s.update_inventory("slug", Side.UP, 10, 4.0)
    s.update_inventory("slug", Side.DOWN, 8, 3.6)
    mi = s.market_inv("slug")
    assert mi.paired_shares == 8
    assert mi.residual_side == "UP"
    leg = s.get_inv("slug")
    assert leg.paired == 8
