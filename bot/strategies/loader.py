"""
Dynamic loader για το plugin-based strategy architecture (Priority 2).

Σύμβαση που πρέπει να ακολουθεί κάθε αρχείο μέσα στο bot/strategies/ για να
φορτωθεί αυτόματα:

    # προαιρετικό: αν λείπει, το module φορτώνεται πάντα ενεργό
    STRATEGY_ENABLED_ENV = "MY_STRATEGY_ENABLED"

    def build(shared_strategy) -> StrategyModule:
        return MyStrategy(...)

Ένα module χωρίς `build()` αγνοείται σιωπηλά (π.χ. `base.py` είναι απλά
utilities, όχι μια στρατηγική). Αυτό επιτρέπει να προσθέτεις/αφαιρείς
στρατηγικές αντιγράφοντας/σβήνοντας ένα αρχείο μέσα στο bot/strategies/,
χωρίς να αγγίζεις καθόλου το main.py.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from typing import Set

from .base import StrategyRegistry

log = logging.getLogger(__name__)

_SKIP: Set[str] = {"base", "loader"}


def load_all(shared_strategy, package_name: str = "bot.strategies") -> StrategyRegistry:
    """
    Ανακαλύπτει κάθε module μέσα στο bot/strategies/ (εκτός base.py/loader.py),
    το κάνει import, και αν εκθέτει `build(shared_strategy)`, καλεί το registry.

    Fail-soft ανά module: αν ένα strategy module αποτύχει στο import ή στο
    build(), καταγράφεται σφάλμα και ο loader προχωράει στο επόμενο — ένα
    σπασμένο plugin δεν πρέπει να ρίξει ολόκληρο τον bot.
    """
    registry = StrategyRegistry()
    package = importlib.import_module(package_name)

    for _, name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg or name in _SKIP:
            continue

        try:
            mod = importlib.import_module(f".{name}", package=package_name)
        except Exception:
            log.exception(f"[LOADER] failed to import {package_name}.{name} — skipping")
            continue

        enabled_env = getattr(mod, "STRATEGY_ENABLED_ENV", None)
        if enabled_env and os.getenv(enabled_env, "false").lower() != "true":
            log.debug(f"[LOADER] {name}: {enabled_env} is not 'true' — skipping")
            continue

        build_fn = getattr(mod, "build", None)
        if build_fn is None:
            continue  # utility module χωρίς build() -> δεν είναι strategy plugin

        try:
            instance = build_fn(shared_strategy)
        except Exception:
            log.exception(f"[LOADER] {package_name}.{name}.build() failed — skipping")
            continue

        registry.register(instance)

    return registry
