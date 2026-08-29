"""
Kelly Criterion position sizing — ιδέα από LvcidPsyche/polymarket-arbitrage-bot.

Χρησιμοποιεί fractional Kelly (μισό ή λιγότερο by default) γιατί plain Kelly
είναι πολύ επιθετικό όταν το win_prob estimate έχει σφάλμα — κι εδώ σίγουρα
έχει, αφού προέρχεται από heuristics (book imbalance, momentum), όχι από
calibrated μοντέλο.

ΣΗΜΑΝΤΙΚΟ: το Kelly sizing εδώ ΠΟΤΕ δεν παρακάμπτει τα υπάρχοντα risk caps
(cfg.max_order_usd, exposure_cap_for). Είναι πρόσθετος περιορισμός, όχι
αντικατάσταση — clamp πάντα στο μικρότερο από τα δύο.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import cfg


@dataclass
class KellyInput:
    win_prob: float       # εκτίμηση πιθανότητας νίκης (0-1), από τη στρατηγική
    price: float           # τιμή αγοράς του outcome token (0-1)
    bankroll_usd: float    # διαθέσιμο κεφάλαιο ΓΙ' ΑΥΤΗ την αγορά (π.χ. remaining exposure)


def kelly_fraction(win_prob: float, price: float) -> float:
    """
    Binary outcome token στην τιμή `price` που πληρώνει $1 αν κερδίσει:
        b = (1 - price) / price          (net odds, "b to 1")
        f* = (b * win_prob - (1 - win_prob)) / b

    Clamp σε [0, 1]: ποτέ αρνητικό sizing (σημαίνει "μην παίξεις"), ποτέ
    πάνω από το 100% του διαθέσιμου bankroll.
    """
    win_prob = min(max(win_prob, 0.0), 1.0)
    price = min(max(price, 0.01), 0.99)
    b = (1.0 - price) / price
    if b <= 0:
        return 0.0
    f = (b * win_prob - (1.0 - win_prob)) / b
    return max(0.0, min(f, 1.0))


def kelly_size_usd(inp: KellyInput, fraction_of_kelly: float = 0.5) -> float:
    """
    fraction_of_kelly=0.5 → half-Kelly (συνιστώμενο default για production;
    βλ. π.χ. κλασική βιβλιογραφία περί variance drag στο full-Kelly).

    Extra clamp στο cfg.max_order_usd — το Kelly κάνει το sizing πιο
    ΣΥΝΤΗΡΗΤΙΚΟ όταν το edge είναι αμφίβολο, ποτέ πιο επιθετικό από το
    υπάρχον hard cap.
    """
    fraction_of_kelly = min(max(fraction_of_kelly, 0.0), 1.0)
    f = kelly_fraction(inp.win_prob, inp.price) * fraction_of_kelly
    size = f * max(inp.bankroll_usd, 0.0)
    return round(min(size, cfg.max_order_usd), 2)


def kelly_size_from_edge(edge: float, price: float, bankroll_usd: float,
                          fraction_of_kelly: float = 0.5) -> float:
    """
    Convenience wrapper για στρατηγικές που ήδη δουλεύουν με "edge" (π.χ.
    bot/strategy.py::edge_up/edge_down) αντί για ρητή win_prob.

    edge = fair_value - price  (0.5 + tilt - ask, όπως ήδη υπολογίζεται στο
    strategy.py). Το μετατρέπουμε σε win_prob ως price + edge, clamped.
    """
    win_prob = min(max(price + edge, 0.0), 1.0)
    return kelly_size_usd(
        KellyInput(win_prob=win_prob, price=price, bankroll_usd=bankroll_usd),
        fraction_of_kelly=fraction_of_kelly,
    )
