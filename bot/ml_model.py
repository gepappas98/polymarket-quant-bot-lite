"""
ML probability model (Priority 3) — XGBoost πάνω σε book-derived features,
για να αντικαταστήσει/συμπληρώσει το heuristic `edge_up`/`edge_down` του
bot/strategy.py::Strategy.evaluate() με calibrated πιθανότητα νίκης.

Design decisions:
- Lazy import του xgboost — αν λείπει ή δεν υπάρχει trained model, κάθε
  public method επιστρέφει None και ο caller πρέπει να κάνει fallback στο
  heuristic (βλ. bot/strategies/ml_directional.py). ΠΟΤΕ δεν σκάει τον bot.
- Features εξαγόμενα ΜΟΝΟ από ό,τι ήδη υπάρχει σε bot.feeds.MarketState —
  δεν εφευρίσκω νέα data sources. Αν αργότερα συνδέσεις bot.feeds.PriceFeed
  ενεργά (window open-price delta, ROADMAP item), πρόσθεσε το feature εδώ,
  σε ΕΝΑ σημείο (extract_features), και ξανα-εκπαίδευσε.
- Training data: bot/backtest.py::Snapshot ιστορικό (ίδιο format), με label
  = 1 αν UP κέρδισε, 0 αν DOWN. ΔΕΝ training σε live παραγόμενα δεδομένα
  χωρίς επιβεβαιωμένο outcome.

ΔΕΝ έχω πραγματικά ιστορικά δεδομένα για να εκπαιδεύσω ένα χρήσιμο μοντέλο
εδώ — το training pipeline είναι πλήρες και δοκιμασμένο με συνθετικά
δεδομένα (βλ. tests), αλλά η ΠΟΙΟΤΗΤΑ του πραγματικού μοντέλου εξαρτάται
100% από το πόσα πραγματικά resolved markets θα του δώσεις. Με <200 δείγματα
μην περιμένεις κάτι καλύτερο από το heuristic.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

MODEL_PATH = Path(os.getenv("ML_MODEL_PATH", "data/ml_model.json"))
FEATURE_NAMES = [
    "up_ask", "down_ask", "up_bid", "down_bid",
    "up_mid", "down_mid", "spread_up", "spread_down", "imbalance",
]


@dataclass
class Features:
    up_ask: float
    down_ask: float
    up_bid: float
    down_bid: float
    up_mid: float
    down_mid: float
    spread_up: float
    spread_down: float
    imbalance: float

    def to_list(self) -> List[float]:
        return [getattr(self, name) for name in FEATURE_NAMES]


def extract_features(state) -> Optional[Features]:
    """state: bot.feeds.MarketState (ή bot.backtest.BacktestMarketState — ίδιο interface).
    Επιστρέφει None αν δεν έχουμε αρκετό book και για τις δύο πλευρές."""
    up_ask, down_ask = state.up_ask, state.down_ask
    up_bid, down_bid = state.up_book.best_bid, state.down_book.best_bid
    if up_ask is None or down_ask is None or up_bid is None or down_bid is None:
        return None
    up_mid = state.up_book.mid or up_ask
    down_mid = state.down_book.mid or down_ask
    return Features(
        up_ask=up_ask, down_ask=down_ask, up_bid=up_bid, down_bid=down_bid,
        up_mid=up_mid, down_mid=down_mid,
        spread_up=round(up_ask - up_bid, 4), spread_down=round(down_ask - down_bid, 4),
        imbalance=round(up_bid - down_bid, 4),
    )


class ProbabilityModel:
    """
    Thin wrapper γύρω από xgboost.XGBClassifier. Χρησιμοποίησε
    `ProbabilityModel.load()` για inference στο live/paper loop, και
    `ProbabilityModel.train(X, y)` + `.save()` offline/στο backtest pipeline.
    """

    def __init__(self):
        self._model = None
        self._available = False
        try:
            import xgboost  # noqa: F401 — μόνο έλεγχος διαθεσιμότητας εδώ
            self._xgboost = xgboost
            self._available = True
        except ImportError:
            log.warning("ProbabilityModel: xgboost δεν είναι εγκατεστημένο — ML signal disabled")
            self._xgboost = None

    @property
    def available(self) -> bool:
        return self._available and self._model is not None

    def train(self, X: List[List[float]], y: List[int], **xgb_params) -> None:
        if not self._available:
            raise RuntimeError("xgboost δεν είναι εγκατεστημένο — pip install xgboost")
        params = {
            "n_estimators": 150,
            "max_depth": 3,
            "learning_rate": 0.05,
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            **xgb_params,
        }
        model = self._xgboost.XGBClassifier(**params)
        model.fit(X, y)
        self._model = model
        log.info(f"ProbabilityModel: trained on {len(X)} samples")

    def predict_win_prob_up(self, state) -> Optional[float]:
        """Επιστρέφει P(UP wins) στο [0,1], ή None αν δεν υπάρχει trained model
        ή αν λείπουν features (π.χ. αραιό order book)."""
        if not self.available:
            return None
        feats = extract_features(state)
        if feats is None:
            return None
        proba = self._model.predict_proba([feats.to_list()])[0]
        # class 1 = "UP wins", βλ. build_training_set()
        return float(proba[1])

    def save(self, path: Optional[Path] = None) -> None:
        if self._model is None:
            raise RuntimeError("Δεν υπάρχει trained model να αποθηκευτεί")
        path = path or MODEL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(path))
        with open(str(path) + ".meta.json", "w") as f:
            json.dump({"feature_names": FEATURE_NAMES}, f)
        log.info(f"ProbabilityModel: saved to {path}")

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ProbabilityModel":
        inst = cls()
        path = path or MODEL_PATH
        if not inst._available or not path.exists():
            return inst  # available=False -> callers κάνουν fallback στο heuristic
        try:
            model = inst._xgboost.XGBClassifier()
            model.load_model(str(path))
            inst._model = model
            log.info(f"ProbabilityModel: loaded from {path}")
        except Exception as e:
            log.error(f"ProbabilityModel: failed to load {path}: {e} — ML signal disabled")
        return inst


def build_training_set(snapshots) -> Tuple[List[List[float]], List[int]]:
    """
    snapshots: Iterable[bot.backtest.Snapshot], ταξινομημένα κατά ts.
    Για κάθε market: παίρνει τα features απ' το ΤΕΛΕΥΤΑΙΟ pre-resolution
    snapshot του, με label = 1 αν winner=="UP" αλλιώς 0. Markets χωρίς
    resolution event αγνοούνται (δεν έχουμε label).
    """
    from .backtest import BacktestMarketState  # local import: αποφυγή κυκλικού import

    last_pre_resolution: dict = {}
    X: List[List[float]] = []
    y: List[int] = []

    for snap in snapshots:
        slug = snap.market.get("slug")
        if not slug:
            continue
        if not snap.resolved:
            last_pre_resolution[slug] = snap
            continue
        prior = last_pre_resolution.get(slug)
        if prior is None or snap.winner not in ("UP", "DOWN"):
            continue
        feats = extract_features(BacktestMarketState(prior))
        if feats is None:
            continue
        X.append(feats.to_list())
        y.append(1 if snap.winner == "UP" else 0)

    return X, y
