import importlib
import os
from pathlib import Path

from app.services.preprocessing_service import clean_price_series
from bot.backtest import load_snapshots
from bot.ml_model import MODEL_PATH, ProbabilityModel, build_training_set


def retrain_model(snapshots_path=None, model_path=None, min_samples=20):
    try:
        importlib.import_module("xgboost")
    except ImportError:
        return {"status": "skipped", "reason": "xgboost not installed"}
    path = snapshots_path or os.getenv("SNAPSHOTS_PATH")
    if not path:
        return {"status": "skipped", "reason": "snapshots path not configured"}
    X, y = build_training_set(load_snapshots(path))
    if len(X) < min_samples:
        return {"status": "skipped", "reason": "insufficient samples", "samples": len(X)}
    replaced = 0
    if X:
        columns = []
        for j in range(len(X[0])):
            original = [row[j] for row in X]
            cleaned = clean_price_series(original, window=20)
            replaced += sum(a != b for a, b in zip(original, cleaned))
            columns.append(cleaned)
        X = [[columns[j][i] for j in range(len(columns))] for i in range(len(X))]
    model = ProbabilityModel()
    model.train(X, y)
    destination = Path(model_path or MODEL_PATH)
    model.save(destination)
    return {"status": "trained", "samples": len(X), "outliers_replaced": replaced, "model_path": str(destination)}
