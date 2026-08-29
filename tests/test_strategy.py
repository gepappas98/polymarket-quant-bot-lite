import time

import pytest

from bot.config import cfg
from bot.ledger import LedgerEntry, ledger
from bot.strategy import Inventory, Side, Strategy


class FakeBook:
    def __init__(self, best_bid=None, best_ask=None):
        self._best_bid = best_bid
        self._best_ask = best_ask

    @property
    def best_bid(self):
        return self._best_bid

    @property
    def best_ask(self):
        return self._best_ask

    @property
    def mid(self):
        if self._best_bid is not None and self._best_ask is not None:
            return (self._best_bid + self._best_ask) / 2
        return self._best_ask or self._best_bid


class FakeState:
    """Stands in for feeds.MarketState without touching any network feed."""

    def __init__(self, slug, up_ask, down_ask, up_bid=None, down_bid=None, asset="BTC"):
        self.market = {
            "slug": slug,
            "asset": asset,
            "up_token_id": "UP_TOKEN",
            "down_token_id": "DOWN_TOKEN",
        }
        self.up_book = FakeBook(best_bid=up_bid, best_ask=up_ask)
        self.down_book = FakeBook(best_bid=down_bid, best_ask=down_ask)

    @property
    def up_ask(self):
        return self.up_book.best_ask

    @property
    def down_ask(self):
        return self.down_book.best_ask

    @property
    def sum_asks(self):
        if self.up_ask is not None and self.down_ask is not None:
            return self.up_ask + self.down_ask
        return None

    @property
    def arb_available(self):
        s = self.sum_asks
        return s is not None and s <= cfg.arb_threshold


@pytest.fixture(autouse=True)
def isolate_ledger(tmp_path, monkeypatch):
    """Every test gets a clean, disk-isolated ledger so runs don't pollute
    data/trades.jsonl or leak state between tests."""
    monkeypatch.setattr(ledger, "path", tmp_path / "trades.jsonl")
    ledger._entries.clear()
    yield
    ledger._entries.clear()


class TestInventory:
    def test_starts_empty(self):
        inv = Inventory()
        assert inv.total_cost == 0
        assert inv.paired == 0

    def test_total_cost_sums_both_sides(self):
        inv = Inventory(up_cost=10, down_cost=15)
        assert inv.total_cost == 25

    def test_net_exposure_is_the_absolute_imbalance(self):
        inv = Inventory(up_cost=10, down_cost=15)
        assert inv.net_exposure_usd == 5

    def test_paired_is_the_smaller_of_the_two_share_counts(self):
        inv = Inventory(up_shares=8, down_shares=3)
        assert inv.paired == 3


class TestArbDetection:
    def test_buys_both_sides_when_sum_below_threshold(self, monkeypatch):
        monkeypatch.setattr(cfg, "arb_threshold", 0.985)
        monkeypatch.setattr(cfg, "max_market_exposure_usd", 150.0)
        monkeypatch.setattr(cfg, "max_order_usd", 25.0)
        strategy = Strategy()
        state = FakeState("btc-updown-5m-1", up_ask=0.48, down_ask=0.49)  # sum=0.97
        intents = strategy.evaluate(state)
        assert len(intents) == 2
        sides = {i.side for i in intents}
        assert sides == {Side.UP, Side.DOWN}
        assert all(i.is_arb_leg for i in intents)

    def test_no_arb_when_sum_above_threshold(self, monkeypatch):
        monkeypatch.setattr(cfg, "arb_threshold", 0.985)
        monkeypatch.setattr(cfg, "min_directional_edge", 0.5)  # suppress directional too
        strategy = Strategy()
        state = FakeState("btc-updown-5m-2", up_ask=0.51, down_ask=0.50)  # sum=1.01
        intents = strategy.evaluate(state)
        assert not any(i.is_arb_leg for i in intents)

    def test_respects_max_market_exposure(self, monkeypatch):
        monkeypatch.setattr(cfg, "arb_threshold", 0.985)
        monkeypatch.setattr(cfg, "max_market_exposure_usd", 100.0)
        strategy = Strategy()
        inv = strategy.get_inv("btc-updown-5m-3")
        inv.up_cost = 60
        inv.down_cost = 60  # already at/over cap
        state = FakeState("btc-updown-5m-3", up_ask=0.48, down_ask=0.49)
        intents = strategy.evaluate(state)
        assert intents == []

    def test_no_intents_when_a_side_has_no_ask(self, monkeypatch):
        strategy = Strategy()
        state = FakeState("btc-updown-5m-4", up_ask=None, down_ask=0.49)
        intents = strategy.evaluate(state)
        assert intents == []


class TestDirectionalTilt:
    def test_prefers_up_when_book_imbalance_favors_up(self, monkeypatch):
        monkeypatch.setattr(cfg, "arb_threshold", 0.90)  # keep sum=1.0 out of arb range
        monkeypatch.setattr(cfg, "min_directional_edge", 0.03)
        monkeypatch.setattr(cfg, "max_market_exposure_usd", 150.0)
        monkeypatch.setattr(cfg, "max_order_usd", 25.0)
        monkeypatch.setattr(cfg, "prefer_maker", False)
        strategy = Strategy()
        # up_bid high relative to down_bid → imbalance favors UP
        state = FakeState(
            "btc-updown-5m-5", up_ask=0.50, down_ask=0.50, up_bid=0.48, down_bid=0.30
        )
        intents = strategy.evaluate(state)
        assert len(intents) == 1
        assert intents[0].side == Side.UP

    def test_no_directional_trade_when_edge_below_minimum(self, monkeypatch):
        monkeypatch.setattr(cfg, "arb_threshold", 0.90)
        monkeypatch.setattr(cfg, "min_directional_edge", 0.5)  # unreachable bar
        strategy = Strategy()
        state = FakeState("btc-updown-5m-6", up_ask=0.50, down_ask=0.50, up_bid=0.49, down_bid=0.48)
        intents = strategy.evaluate(state)
        assert intents == []

    def test_maker_preference_shaves_one_tick_off_price(self, monkeypatch):
        monkeypatch.setattr(cfg, "arb_threshold", 0.90)
        monkeypatch.setattr(cfg, "min_directional_edge", 0.03)
        monkeypatch.setattr(cfg, "prefer_maker", True)
        strategy = Strategy()
        state = FakeState(
            "btc-updown-5m-7", up_ask=0.50, down_ask=0.50, up_bid=0.48, down_bid=0.30
        )
        intents = strategy.evaluate(state)
        assert intents[0].price == pytest.approx(0.49, abs=1e-6)


class TestTrackRecordGate:
    def _seed_outcomes(self, slug_prefix, wins, losses):
        now = time.time()
        for i in range(wins):
            ledger._entries.append(LedgerEntry(
                ts=now, kind="outcome", market_slug=f"{slug_prefix}-{i}",
                pnl_usd=5.0, dry_run=True, status="closed",
            ))
        for i in range(losses):
            ledger._entries.append(LedgerEntry(
                ts=now, kind="outcome", market_slug=f"{slug_prefix}-loss-{i}",
                pnl_usd=-5.0, dry_run=True, status="closed",
            ))

    def test_directional_blocked_when_win_rate_below_minimum(self, monkeypatch):
        monkeypatch.setattr(cfg, "arb_threshold", 0.90)
        monkeypatch.setattr(cfg, "min_directional_edge", 0.03)
        monkeypatch.setattr(cfg, "min_track_record_win_pct", 60.0)
        monkeypatch.setattr(cfg, "min_track_record_samples", 10)
        self._seed_outcomes("btc", wins=2, losses=10)  # 12 samples, ~16.7% win rate
        strategy = Strategy()
        state = FakeState(
            "btc-updown-5m-8", up_ask=0.50, down_ask=0.50, up_bid=0.48, down_bid=0.30
        )
        intents = strategy.evaluate(state)
        assert intents == []

    def test_directional_allowed_when_win_rate_meets_minimum(self, monkeypatch):
        monkeypatch.setattr(cfg, "arb_threshold", 0.90)
        monkeypatch.setattr(cfg, "min_directional_edge", 0.03)
        monkeypatch.setattr(cfg, "min_track_record_win_pct", 40.0)
        monkeypatch.setattr(cfg, "min_track_record_samples", 10)
        self._seed_outcomes("btc", wins=6, losses=6)  # 12 samples, 50% win rate
        strategy = Strategy()
        state = FakeState(
            "btc-updown-5m-9", up_ask=0.50, down_ask=0.50, up_bid=0.48, down_bid=0.30
        )
        intents = strategy.evaluate(state)
        assert len(intents) == 1

    def test_gate_does_not_apply_below_minimum_sample_size(self, monkeypatch):
        """Too few outcomes to trust — must NOT block (fail closed means 'don't
        gate on noise', not 'block everything until we have history')."""
        monkeypatch.setattr(cfg, "arb_threshold", 0.90)
        monkeypatch.setattr(cfg, "min_directional_edge", 0.03)
        monkeypatch.setattr(cfg, "min_track_record_win_pct", 80.0)
        monkeypatch.setattr(cfg, "min_track_record_samples", 20)
        self._seed_outcomes("btc", wins=1, losses=2)  # only 3 samples, far below 20
        strategy = Strategy()
        state = FakeState(
            "btc-updown-5m-10", up_ask=0.50, down_ask=0.50, up_bid=0.48, down_bid=0.30
        )
        intents = strategy.evaluate(state)
        assert len(intents) == 1


class TestInventoryUpdates:
    def test_update_inventory_accumulates_across_calls(self):
        strategy = Strategy()
        strategy.update_inventory("btc-updown-5m-11", Side.UP, shares=10, cost=5)
        strategy.update_inventory("btc-updown-5m-11", Side.UP, shares=5, cost=2.5)
        inv = strategy.get_inv("btc-updown-5m-11")
        assert inv.up_shares == 15
        assert inv.up_cost == 7.5

    def test_up_and_down_tracked_independently(self):
        strategy = Strategy()
        strategy.update_inventory("btc-updown-5m-12", Side.UP, shares=10, cost=5)
        strategy.update_inventory("btc-updown-5m-12", Side.DOWN, shares=4, cost=2)
        inv = strategy.get_inv("btc-updown-5m-12")
        assert inv.up_shares == 10
        assert inv.down_shares == 4
