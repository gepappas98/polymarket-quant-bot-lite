import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.feeds import PriceFeed
from bot.ctf_ops import split_complete_set, merge_complete_set, redeem_positions, maybe_merge_excess


class _FakeFeed(PriceFeed):
    def __init__(self):
        self._exchange = object()  # pretend available
        self._cache = {}
        self._cache_ttl_sec = 2.0
        self._window_open = {}
        self._prices = {}

    def get_price(self, asset: str):
        return self._prices.get(asset.upper())


def test_window_delta_and_fair():
    f = _FakeFeed()
    f._prices["BTC"] = 100.0
    assert f.anchor_window("btc-5m-1", "BTC") == 100.0
    f._prices["BTC"] = 101.0  # +1%
    d = f.window_delta_pct("btc-5m-1", "BTC")
    assert abs(d - 0.01) < 1e-9
    # MarketState.fair uses 0.5 + 35*d
    fair = max(0.05, min(0.95, 0.5 + 35 * d))
    assert abs(fair - 0.85) < 1e-9


def test_ctf_paper_ops():
    r = split_complete_set("0xabc", 25.0)
    assert r.ok and r.dry_run
    r = merge_complete_set("0xabc", 10.0)
    assert r.ok and r.dry_run
    r = redeem_positions("0xabc")
    assert r.ok and r.dry_run
    r = maybe_merge_excess("0xabc", paired_shares=5, keep_shares=5)
    assert r.ok and "nothing" in r.detail
