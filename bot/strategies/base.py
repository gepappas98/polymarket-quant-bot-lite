"""
Κοινό interface για όλα τα strategy modules (arb/directional, market-making,
copy-trading, ...). Δεν αλλάζει τίποτα στο υπάρχον bot/strategy.py::Strategy —
απλά του δίνει ένα σχήμα ώστε το main.py να τρέχει λίστα από strategies και
να μαζεύει τα intents τους μαζί, μέσα από το ίδιο gate/executor pipeline.

Design: Protocol αντί για ABC, γιατί το υπάρχον Strategy class ήδη ταιριάζει
(.evaluate(state) -> List[Intent]) χωρίς να χρειάζεται να κληρονομήσει τίποτα.
"""

from __future__ import annotations

import logging
from typing import List, Protocol, runtime_checkable

from ..strategy import Intent

log = logging.getLogger(__name__)


@runtime_checkable
class StrategyModule(Protocol):
    name: str

    def evaluate(self, state) -> List[Intent]:
        """state: bot.feeds.MarketState. Πρέπει να επιστρέφει [] αν δεν κάνει τίποτα."""
        ...


class StrategyRegistry:
    """
    Τρέχει πολλά strategy modules πάνω στο ίδιο MarketState και μαζεύει τα
    intents τους σε μία λίστα. Ένα module που κάνει raise δεν κατεβάζει το
    process — απλά το κύκλωμα εκείνης της στρατηγικής παραλείπεται εκείνο
    το cycle (fail-closed ως προς το process, όχι ως προς τη στρατηγική).
    """

    def __init__(self):
        self._modules: List[StrategyModule] = []

    def register(self, module: StrategyModule) -> "StrategyRegistry":
        name = getattr(module, "name", module.__class__.__name__)
        log.info(f"[REGISTRY] registered strategy module: {name}")
        self._modules.append(module)
        return self

    def evaluate_all(self, state) -> List[Intent]:
        intents: List[Intent] = []
        for m in self._modules:
            name = getattr(m, "name", m.__class__.__name__)
            try:
                new = m.evaluate(state)
                if new:
                    intents.extend(new)
            except Exception:
                log.exception(f"[{name}] evaluate() failed — skipping this cycle")
        return intents

    @property
    def modules(self) -> List[StrategyModule]:
        return list(self._modules)
