"""
Δεν είναι νέα στρατηγική — τυλίγει το ήδη υπάρχον bot/strategy.py::Strategy
(arb/directional) ώστε ο dynamic loader (bot/strategies/loader.py) να το
κάνει register σαν οποιοδήποτε άλλο plugin, χωρίς να αλλάξει τίποτα στη
δική του λογική. Πάντα ενεργό (χωρίς STRATEGY_ENABLED_ENV) — είναι η core
στρατηγική γύρω από την οποία είναι χτισμένα τα risk caps.
"""

from __future__ import annotations


def build(shared_strategy):
    # shared_strategy ΕΙΝΑΙ ήδη ένα Strategy instance με .evaluate(state) —
    # δεν χρειάζεται wrapping, απλά το επιστρέφουμε ως έχει.
    return shared_strategy
