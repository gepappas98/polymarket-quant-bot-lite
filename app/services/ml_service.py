from __future__ import annotations

import importlib
import math
import os
from pathlib import Path

from bot.backtest import BacktestMarketState, Snapshot
from bot.ml_dataset import DatasetUnavailable, load_real_dataset
from bot.ml_model import MODEL_PATH, ProbabilityModel, extract_features


def _features(samples):
    rows = []
    labels = []
    for sample in samples:
        snapshot = sample.snapshot
        state = BacktestMarketState(
            Snapshot(
                ts=sample.ts_ms / 1000,
                market={
                    "slug": sample.market_id,
                    "market_id": sample.market_id,
                    "condition_id": sample.condition_id,
                },
                up_bids=snapshot.get("up_bids", []),
                up_asks=snapshot.get("up_asks", []),
                down_bids=snapshot.get("down_bids", []),
                down_asks=snapshot.get("down_asks", []),
            )
        )
        features = extract_features(state)
        if features is not None:
            rows.append(features.to_list())
            labels.append(1 if sample.winner == "UP" else 0)
    return rows, labels


def _logloss(probabilities, labels):
    if not labels:
        return None
    return round(
        sum(-label * math.log(max(min(probability, 1 - 1e-15), 1e-15)) - (1 - label) * math.log(max(min(1 - probability, 1 - 1e-15), 1e-15)) for probability, label in zip(probabilities, labels)) / len(labels),
        6,
    )


def _brier(probabilities, labels):
    if not labels:
        return None
    return round(sum((probability - label) ** 2 for probability, label in zip(probabilities, labels)) / len(labels), 6)


def retrain_model(dataset_path=None, model_path=None, min_samples=20):
    try:
        importlib.import_module("xgboost")
    except ImportError:
        return {"status": "skipped", "reason": "xgboost not installed"}

    path = dataset_path or os.getenv("ML_DATASET_PATH")
    if not path:
        return {"status": "failed", "reason": "REAL Polymarket ML dataset is not configured; set ML_DATASET_PATH"}
    try:
        provenance, samples = load_real_dataset(path)
    except DatasetUnavailable as exc:
        return {"status": "failed", "reason": str(exc)}
    if len(samples) < min_samples:
        return {"status": "failed", "reason": "insufficient REAL labeled samples", "samples": len(samples)}
    if len(provenance.market_ids) < 3:
        return {"status": "failed", "reason": "at least 3 distinct resolved Polymarket markets are required", "markets": len(provenance.market_ids)}

    split_one = max(1, len(samples) * 60 // 100)
    split_two = max(split_one + 1, len(samples) * 80 // 100)
    if split_two >= len(samples):
        return {"status": "failed", "reason": "REAL dataset needs distinct train, validation, and test periods"}
    train_samples, validation_samples, test_samples = samples[:split_one], samples[split_one:split_two], samples[split_two:]
    partitions = [set(sample.market_id for sample in partition) for partition in (train_samples, validation_samples, test_samples)]
    if partitions[0] & partitions[1] or partitions[0] & partitions[2] or partitions[1] & partitions[2]:
        return {"status": "failed", "reason": "market groups overlap across chronological train/validation/test partitions"}

    X_train, y_train = _features(train_samples)
    X_validation, y_validation = _features(validation_samples)
    X_test, y_test = _features(test_samples)
    if not X_train or set(y_train) != {0, 1} or not X_validation or not X_test:
        return {"status": "failed", "reason": "REAL dataset partitions must contain both labels and valid L2 features"}

    model = ProbabilityModel()
    metadata = {
        **provenance.as_dict(),
        "training": {
            "train_samples": len(X_train),
            "validation_samples": len(X_validation),
            "test_samples": len(X_test),
            "split": "chronological_by_resolution_time_60_20_20",
            "preprocessing": "none_cross_market",
        },
    }
    model.train(X_train, y_train, metadata=metadata)
    probabilities = model._model.predict_proba(X_validation)[:, list(model._model.classes_).index(1)]
    test_probabilities = model._model.predict_proba(X_test)[:, list(model._model.classes_).index(1)]
    metadata["validation"] = {
        "logloss": _logloss(probabilities, y_validation),
        "brier": _brier(probabilities, y_validation),
    }
    metadata["test"] = {
        "logloss": _logloss(test_probabilities, y_test),
        "brier": _brier(test_probabilities, y_test),
    }
    model.metadata = metadata
    destination = Path(model_path or MODEL_PATH)
    model.save(destination)
    return {
        "status": "trained",
        "dataset_id": provenance.dataset_id,
        "samples": len(samples),
        "train_samples": len(X_train),
        "validation_samples": len(X_validation),
        "test_samples": len(X_test),
        "validation": metadata["validation"],
        "test": metadata["test"],
        "model_path": str(destination),
    }
