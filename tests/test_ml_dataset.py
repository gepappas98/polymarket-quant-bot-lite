import json

import pytest

from bot.backtest import Snapshot
from bot.ml_dataset import DatasetUnavailable, load_real_dataset
from bot.ml_model import build_training_set


def sample_payload(**overrides):
    rows = [
        {
            "ts_ms": 100,
            "market_id": "m1",
            "condition_id": "c1",
            "winner": "UP",
            "resolved_at_ms": 200,
            "snapshot": {"up_bids": [{"price": "0.4", "size": "2"}], "up_asks": [{"price": "0.5", "size": "2"}], "down_bids": [{"price": "0.4", "size": "2"}], "down_asks": [{"price": "0.5", "size": "2"}]},
        },
        {
            "ts_ms": 300,
            "market_id": "m2",
            "condition_id": "c2",
            "winner": "DOWN",
            "resolved_at_ms": 400,
            "snapshot": {"up_bids": [{"price": "0.4", "size": "2"}], "up_asks": [{"price": "0.5", "size": "2"}], "down_bids": [{"price": "0.4", "size": "2"}], "down_asks": [{"price": "0.5", "size": "2"}]},
        },
    ]
    payload = {
        "schema_version": 1,
        "dataset_id": "real-test",
        "source": "REAL_HISTORICAL_POLYMARKET",
        "label_source": "POLYMARKET_RESOLUTION",
        "created_at": "2026-01-01T00:00:00+00:00",
        "market_ids": ["m1", "m2"],
        "time_range": {"start_ms": 100, "end_ms": 300},
        "feature_version": "book-v1",
        "label_version": "resolution-v1",
        "sample_count": 2,
        "samples": rows,
    }
    payload.update(overrides)
    return payload


def test_real_dataset_loads_and_sorts_samples(tmp_path):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(sample_payload()), encoding="utf-8")
    provenance, samples = load_real_dataset(path)
    assert provenance.source == "REAL_HISTORICAL_POLYMARKET"
    assert [sample.market_id for sample in samples] == ["m1", "m2"]


@pytest.mark.parametrize("field,value", [("source", "MOCK"), ("label_source", "SIMULATED_FILL")])
def test_non_real_provenance_is_rejected(tmp_path, field, value):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(sample_payload(**{field: value})), encoding="utf-8")
    with pytest.raises(DatasetUnavailable, match="REAL"):
        load_real_dataset(path)


def test_legacy_snapshot_training_is_rejected():
    with pytest.raises(ValueError, match="REAL_HISTORICAL_POLYMARKET"):
        build_training_set([Snapshot(ts=1, market={"slug": "synthetic"}, resolved=True, winner="UP")])


def test_post_resolution_features_are_rejected(tmp_path):
    payload = sample_payload()
    payload["samples"][0]["ts_ms"] = 200
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DatasetUnavailable, match="post-resolution"):
        load_real_dataset(path)
