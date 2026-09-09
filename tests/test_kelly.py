"""
Tests for bot/kelly.py.

These tests exist to prevent:
  - The fraction_of_kelly parameter lying about its default (was 0.5 in the
    signature but silently clamped to 0.25 inside the function body).
  - A second silent 0.15*bankroll cap that was undocumented and not in config.
  - DEFAULT_KELLY_FRACTION drifting from what actually runs.
"""
import pytest

from bot.kelly import (
    DEFAULT_KELLY_FRACTION,
    KellyInput,
    kelly_fraction,
    kelly_size_from_edge,
    kelly_size_usd,
)
from bot.config import cfg


# ---------------------------------------------------------------------------
# DEFAULT_KELLY_FRACTION
# ---------------------------------------------------------------------------

class TestDefaultKellyFraction:
    def test_is_quarter_kelly(self):
        """The named constant must be 0.25 (quarter-Kelly)."""
        assert DEFAULT_KELLY_FRACTION == pytest.approx(0.25)

    def test_default_param_matches_constant(self):
        """
        The function signature default must equal DEFAULT_KELLY_FRACTION.
        Previously the signature said 0.5 but the body clamped to 0.25 —
        the two faces of the same lie.
        """
        import inspect
        sig = inspect.signature(kelly_size_usd)
        default = sig.parameters["fraction_of_kelly"].default
        assert default == pytest.approx(DEFAULT_KELLY_FRACTION), (
            f"kelly_size_usd default ({default}) != DEFAULT_KELLY_FRACTION "
            f"({DEFAULT_KELLY_FRACTION}). Update the signature or the constant."
        )

    def test_edge_wrapper_default_matches_constant(self):
        import inspect
        sig = inspect.signature(kelly_size_from_edge)
        default = sig.parameters["fraction_of_kelly"].default
        assert default == pytest.approx(DEFAULT_KELLY_FRACTION)


# ---------------------------------------------------------------------------
# kelly_fraction — pure math, no side effects
# ---------------------------------------------------------------------------

class TestKellyFraction:
    def test_positive_edge_gives_positive_fraction(self):
        # win_prob=0.6, price=0.5 → b=1, f* = (1*0.6 - 0.4)/1 = 0.2
        assert kelly_fraction(0.6, 0.5) == pytest.approx(0.2)

    def test_zero_edge_gives_zero(self):
        # win_prob == price → no edge
        assert kelly_fraction(0.5, 0.5) == pytest.approx(0.0)

    def test_negative_edge_clamped_to_zero(self):
        assert kelly_fraction(0.4, 0.5) == pytest.approx(0.0)

    def test_clamped_to_one_at_most(self):
        # At extreme params the raw f* can slightly exceed 1; clamp must hold.
        # Use win_prob=1.0 (certain win) which drives f* → 1.0 exactly.
        assert kelly_fraction(1.0, 0.01) == pytest.approx(1.0)
        # And the result is always <= 1 regardless of inputs
        assert kelly_fraction(0.99, 0.01) <= 1.0

    def test_win_prob_clamped(self):
        assert kelly_fraction(-1.0, 0.5) == pytest.approx(0.0)
        assert kelly_fraction(2.0, 0.5) >= 0.0

    def test_price_clamped(self):
        # Should not raise or return nonsense
        assert kelly_fraction(0.6, 0.0) >= 0.0
        assert kelly_fraction(0.6, 1.0) >= 0.0


# ---------------------------------------------------------------------------
# kelly_size_usd — no silent second clamp, fraction used as passed
# ---------------------------------------------------------------------------

class TestKellySizeUsd:
    def _inp(self, bankroll=100.0):
        # win_prob=0.6, price=0.5 → kelly_fraction=0.2
        return KellyInput(win_prob=0.6, price=0.5, bankroll_usd=bankroll)

    def test_fraction_passed_is_fraction_used(self, monkeypatch):
        """
        Whatever fraction_of_kelly is passed must be used directly.
        Old bug: passing 0.5 silently became 0.25.
        """
        monkeypatch.setattr(cfg, "max_order_usd", 1000.0)
        inp = self._inp(bankroll=1000.0)
        # kelly_fraction = 0.2; size at fraction=0.5 should be 0.2*0.5*1000=100
        size_half = kelly_size_usd(inp, fraction_of_kelly=0.5)
        # size at fraction=0.25 should be 0.2*0.25*1000=50
        size_quarter = kelly_size_usd(inp, fraction_of_kelly=0.25)
        assert size_half == pytest.approx(100.0, abs=0.01)
        assert size_quarter == pytest.approx(50.0, abs=0.01)
        # They must differ — the old bug made them equal.
        assert size_half != pytest.approx(size_quarter)

    def test_no_silent_15pct_bankroll_cap(self, monkeypatch):
        """
        Old code capped at 0.15*bankroll silently. With a large bankroll and
        fraction=1.0, the result must exceed 15% of bankroll (up to max_order_usd).
        """
        monkeypatch.setattr(cfg, "max_order_usd", 100_000.0)
        inp = KellyInput(win_prob=0.9, price=0.5, bankroll_usd=1000.0)
        # kelly_fraction ≈ 0.8; at fraction=1.0 size ≈ 800 > 0.15*1000=150
        size = kelly_size_usd(inp, fraction_of_kelly=1.0)
        assert size > 150.0, (
            f"Silent 15%-of-bankroll cap still present: got {size}, expected > 150"
        )

    def test_max_order_usd_cap_still_applies(self, monkeypatch):
        monkeypatch.setattr(cfg, "max_order_usd", 10.0)
        inp = KellyInput(win_prob=0.9, price=0.5, bankroll_usd=10_000.0)
        assert kelly_size_usd(inp, fraction_of_kelly=1.0) == pytest.approx(10.0, abs=0.01)

    def test_bankroll_cap_still_applies(self, monkeypatch):
        """Size must never exceed the bankroll itself."""
        monkeypatch.setattr(cfg, "max_order_usd", 100_000.0)
        inp = KellyInput(win_prob=0.99, price=0.01, bankroll_usd=50.0)
        # kelly_fraction approaches 1.0; fraction=1.0 → size capped at bankroll
        size = kelly_size_usd(inp, fraction_of_kelly=1.0)
        assert size <= 50.0

    def test_zero_edge_gives_zero_size(self, monkeypatch):
        monkeypatch.setattr(cfg, "max_order_usd", 1000.0)
        inp = KellyInput(win_prob=0.5, price=0.5, bankroll_usd=1000.0)
        assert kelly_size_usd(inp) == pytest.approx(0.0)

    def test_negative_fraction_treated_as_zero(self, monkeypatch):
        monkeypatch.setattr(cfg, "max_order_usd", 1000.0)
        inp = self._inp(bankroll=1000.0)
        assert kelly_size_usd(inp, fraction_of_kelly=-1.0) == pytest.approx(0.0)

    def test_default_fraction_is_quarter_kelly(self, monkeypatch):
        """Calling with no fraction arg must use exactly DEFAULT_KELLY_FRACTION."""
        monkeypatch.setattr(cfg, "max_order_usd", 10_000.0)
        inp = self._inp(bankroll=1000.0)
        expected = kelly_fraction(0.6, 0.5) * DEFAULT_KELLY_FRACTION * 1000.0
        assert kelly_size_usd(inp) == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# kelly_size_from_edge — passes fraction through unchanged
# ---------------------------------------------------------------------------

class TestKellySizeFromEdge:
    def test_matches_equivalent_kelly_size_usd(self, monkeypatch):
        monkeypatch.setattr(cfg, "max_order_usd", 1000.0)
        edge, price, bankroll = 0.1, 0.5, 500.0
        direct = kelly_size_usd(
            KellyInput(win_prob=price + edge, price=price, bankroll_usd=bankroll),
            fraction_of_kelly=DEFAULT_KELLY_FRACTION,
        )
        via_edge = kelly_size_from_edge(edge, price, bankroll)
        assert via_edge == pytest.approx(direct, abs=0.01)

    def test_fraction_passed_through_unchanged(self, monkeypatch):
        monkeypatch.setattr(cfg, "max_order_usd", 10_000.0)
        size_half = kelly_size_from_edge(0.1, 0.5, 1000.0, fraction_of_kelly=0.5)
        size_quarter = kelly_size_from_edge(0.1, 0.5, 1000.0, fraction_of_kelly=0.25)
        assert size_half == pytest.approx(2 * size_quarter, abs=0.01)

    def test_no_15pct_cap_from_edge(self, monkeypatch):
        monkeypatch.setattr(cfg, "max_order_usd", 100_000.0)
        # Large edge, large bankroll — result must exceed 15% of bankroll
        size = kelly_size_from_edge(0.4, 0.5, 1000.0, fraction_of_kelly=1.0)
        assert size > 150.0
