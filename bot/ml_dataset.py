"""Validated, provenance-bearing datasets for supervised Polymarket ML training."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REAL_SOURCE = "REAL_HISTORICAL_POLYMARKET"
REAL_LABEL_SOURCE = "POLYMARKET_RESOLUTION"
DATASET_SCHEMA_VERSION = 1


class DatasetUnavailable(RuntimeError):
    """Raised when a real training dataset is unavailable or invalid."""


@dataclass(frozen=True)
class DatasetProvenance:
    dataset_id: str
    source: str
    label_source: str
    created_at: str
    market_ids: tuple[str, ...]
    time_range: tuple[int, int]
    feature_version: str
    label_version: str
    sample_count: int
    schema_version: int = DATASET_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "source": self.source,
            "label_source": self.label_source,
            "created_at": self.created_at,
            "market_ids": list(self.market_ids),
            "time_range": {"start_ms": self.time_range[0], "end_ms": self.time_range[1]},
            "feature_version": self.feature_version,
            "label_version": self.label_version,
            "sample_count": self.sample_count,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class RealTrainingSample:
    ts_ms: int
    market_id: str
    condition_id: str
    winner: str
    resolved_at_ms: int
    snapshot: dict[str, Any]


def _required_string(raw: dict[str, Any], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise DatasetUnavailable(f"REAL dataset is missing {name}")
    return value.strip()


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DatasetUnavailable(f"REAL Polymarket ML dataset does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetUnavailable(f"cannot read REAL Polymarket ML dataset: {exc}") from exc
    if not isinstance(payload, dict):
        raise DatasetUnavailable("REAL Polymarket ML dataset must be a JSON object")
    return payload


def load_real_dataset(path: str | Path) -> tuple[DatasetProvenance, list[RealTrainingSample]]:
    dataset_path = Path(path)
    payload = _load_payload(dataset_path)
    if payload.get("source") != REAL_SOURCE:
        raise DatasetUnavailable("production ML training requires source=REAL_HISTORICAL_POLYMARKET")
    if payload.get("label_source") != REAL_LABEL_SOURCE:
        raise DatasetUnavailable("production ML training requires label_source=POLYMARKET_RESOLUTION")
    if payload.get("schema_version") != DATASET_SCHEMA_VERSION:
        raise DatasetUnavailable("unsupported REAL Polymarket ML dataset schema")

    rows = payload.get("samples")
    if not isinstance(rows, list) or not rows:
        raise DatasetUnavailable("REAL Polymarket ML dataset contains no samples")
    samples: list[RealTrainingSample] = []
    seen_labels: set[tuple[str, int]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DatasetUnavailable(f"dataset sample {index} is not an object")
        try:
            ts_ms = int(row["ts_ms"])
            resolved_at_ms = int(row["resolved_at_ms"])
            market_id = _required_string(row, "market_id")
            condition_id = _required_string(row, "condition_id")
            winner = str(row["winner"]).upper()
            snapshot = row["snapshot"]
        except (KeyError, TypeError, ValueError) as exc:
            raise DatasetUnavailable(f"dataset sample {index} is malformed") from exc
        if winner not in {"UP", "DOWN"}:
            raise DatasetUnavailable(f"dataset sample {index} has an invalid Polymarket resolution")
        if ts_ms >= resolved_at_ms:
            raise DatasetUnavailable(f"dataset sample {index} contains a post-resolution feature")
        if not isinstance(snapshot, dict):
            raise DatasetUnavailable(f"dataset sample {index} has no book snapshot")
        label_key = (market_id, resolved_at_ms)
        if label_key in seen_labels:
            raise DatasetUnavailable(f"duplicate resolution label for market {market_id}")
        seen_labels.add(label_key)
        samples.append(RealTrainingSample(ts_ms, market_id, condition_id, winner, resolved_at_ms, snapshot))

    samples.sort(key=lambda sample: (sample.resolved_at_ms, sample.ts_ms, sample.market_id))
    declared_count = payload.get("sample_count")
    if declared_count != len(samples):
        raise DatasetUnavailable("dataset sample_count does not match samples")
    market_ids = tuple(sorted({sample.market_id for sample in samples}))
    time_range = (min(sample.ts_ms for sample in samples), max(sample.ts_ms for sample in samples))
    declared_markets = tuple(sorted(str(value) for value in payload.get("market_ids", [])))
    if declared_markets != market_ids:
        raise DatasetUnavailable("dataset market_ids do not match samples")
    raw_range = payload.get("time_range")
    if not isinstance(raw_range, dict) or (int(raw_range.get("start_ms", -1)), int(raw_range.get("end_ms", -1))) != time_range:
        raise DatasetUnavailable("dataset time_range does not match samples")
    created_at = _required_string(payload, "created_at")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetUnavailable("dataset created_at is not an ISO timestamp") from exc
    provenance = DatasetProvenance(
        dataset_id=_required_string(payload, "dataset_id"),
        source=REAL_SOURCE,
        label_source=REAL_LABEL_SOURCE,
        created_at=created_at,
        market_ids=market_ids,
        time_range=time_range,
        feature_version=_required_string(payload, "feature_version"),
        label_version=_required_string(payload, "label_version"),
        sample_count=len(samples),
    )
    return provenance, samples


def dataset_id_for(path: str | Path) -> str:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"{Path(path).name}:{digest[:16]}"


def new_dataset_manifest(samples: Iterable[RealTrainingSample], *, feature_version: str, label_version: str, dataset_id: str) -> dict[str, Any]:
    rows = list(samples)
    if not rows:
        raise DatasetUnavailable("cannot create an empty REAL Polymarket dataset")
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "source": REAL_SOURCE,
        "label_source": REAL_LABEL_SOURCE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "market_ids": sorted({row.market_id for row in rows}),
        "time_range": {"start_ms": min(row.ts_ms for row in rows), "end_ms": max(row.ts_ms for row in rows)},
        "feature_version": feature_version,
        "label_version": label_version,
        "sample_count": len(rows),
        "samples": [
            {
                "ts_ms": row.ts_ms,
                "market_id": row.market_id,
                "condition_id": row.condition_id,
                "winner": row.winner,
                "resolved_at_ms": row.resolved_at_ms,
                "snapshot": row.snapshot,
            }
            for row in rows
        ],
    }
