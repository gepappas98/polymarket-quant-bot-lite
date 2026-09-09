"""
Kelly Criterion position sizing — ιδέα από LvcidPsyche/polymarket-arbitrage-bot.

Uses quarter-Kelly (DEFAULT_KELLY_FRACTION = 0.25) as the default because
win_prob estimates here come from heuristics (book imbalance, momentum) rather
than a calibrated model. Quarter-Kelly is deliberately conservative: it roughly
halves variance relative to half-Kelly and is standard practice when the edge
estimate is uncertain.

The fraction can be overridden per call-site (e.g. ML_KELLY_FRACTION for the
ML strategy), but the constant here is the canonical default and is what runs
unless an explicit override is supplied.

IMPORTANT: Kelly sizing never overrides the existing risk caps (cfg.max_order_usd,
exposure_cap_for). It is an additional constraint, not a replacement — always
clamp to the smaller of the two.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import cfg

# Quarter-Kelly is the default. Win-prob estimates here are uncalibrated
# heuristics, not a trained probability model. Quarter-Kelly keeps variance
# manageable without killing edge entirely. Change via the fraction_of_kelly
# argument — there is no second silent clamp inside the functions below.
DEFAULT_KELLY_FRACTION: float = 0.25


@dataclass
class KellyInput:
    win_prob: float        # estimated win probability (0–1), from the strategy
    price: float           # purchase price of the outcome token (0–1)
    bankroll_usd: float    # available capital for this market (e.g. remaining exposure)


def kelly_fraction(win_prob: float, price: float) -> float:
    """
    Binary outcome token at price `price` that pays $1 on a win:
        b = (1 - price) / price          (net odds, "b to 1")
        f* = (b * win_prob - (1 - win_prob)) / b

    Clamped to [0, 1]: never negative (means "do not trade"), never above
    100% of the available bankroll.
    """
    win_prob = min(max(win_prob, 0.0), 1.0)
    price = min(max(price, 0.01), 0.99)
    b = (1.0 - price) / price
    if b <= 0:
        return 0.0
    f = (b * win_prob - (1.0 - win_prob)) / b
    return max(0.0, min(f, 1.0))


def kelly_size_usd(
    inp: KellyInput,
    fraction_of_kelly: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """
    Return a USD size using fractional Kelly.

    fraction_of_kelly defaults to DEFAULT_KELLY_FRACTION (0.25, quarter-Kelly).
    The caller may pass a different value; whatever is passed is used as-is —
    there is no second clamp inside this function.

    Hard caps applied (in order, smallest wins):
      1. cfg.max_order_usd   — global per-order limit from config/env
      2. inp.bankroll_usd    — remaining exposure budget passed by the caller

    No silent 15%-of-bankroll cap. No re-clamping of fraction_of_kelly.
    """
    fraction_of_kelly = max(fraction_of_kelly, 0.0)  # negative fraction is nonsensical
    f = kelly_fraction(inp.win_prob, inp.price) * fraction_of_kelly
    size = f * max(inp.bankroll_usd, 0.0)
    return round(min(size, cfg.max_order_usd, max(inp.bankroll_usd, 0.0)), 2)


def kelly_size_from_edge(
    edge: float,
    price: float,
    bankroll_usd: float,
    fraction_of_kelly: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """
    Convenience wrapper for strategies that work with 'edge' (e.g.
    bot/strategy.py::edge_up/edge_down) rather than an explicit win_prob.

    edge = fair_value - price  (e.g. 0.5 + tilt - ask, as computed in
    strategy.py). Converted to win_prob as price + edge, clamped to [0, 1].

    fraction_of_kelly defaults to DEFAULT_KELLY_FRACTION (0.25). Passed
    through unchanged to kelly_size_usd — no additional clamping here.
    """
    win_prob = min(max(price + edge, 0.0), 1.0)
    return kelly_size_usd(
        KellyInput(win_prob=win_prob, price=price, bankroll_usd=bankroll_usd),
        fraction_of_kelly=fraction_of_kelly,
    )
