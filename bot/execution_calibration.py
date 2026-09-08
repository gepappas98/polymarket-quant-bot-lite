"""Conservative paper-execution calibration from REAL Polymarket L2 observations."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Sequence

from .historical_data import HistoricalL2Snapshot

CALIBRATION_VERSION = "real-l2-calibration-v1"


@dataclass(frozen=True)
class CalibrationResult:
    fill_model_version: str
    calibration_dataset: str
    assumptions: tuple[str, ...]
    maker_fill_assumption: float
    maker_fill_range: tuple[float, float]
    latency_assumption: float
    latency_range: tuple[float, float]
    fee_model: str
    slippage_model: str
    sample_count: int
    train_count: int
    out_of_sample_count: int
    train_metrics: dict[str, float]
    out_of_sample_metrics: dict[str, float]
    observed_fill_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "fill_model_version": self.fill_model_version,
            "calibration_dataset": self.calibration_dataset,
            "assumptions": list(self.assumptions),
            "maker_fill_assumption": self.maker_fill_assumption,
            "maker_fill_range": list(self.maker_fill_range),
            "latency_assumption": self.latency_assumption,
            "latency_range": list(self.latency_range),
            "fee_model": self.fee_model,
            "slippage_model": self.slippage_model,
            "sample_count": self.sample_count,
            "train_count": self.train_count,
            "out_of_sample_count": self.out_of_sample_count,
            "train_metrics": self.train_metrics,
            "out_of_sample_metrics": self.out_of_sample_metrics,
            "observed_fill_count": self.observed_fill_count,
        }


def _mid(row: HistoricalL2Snapshot) -> float | None:
    bids = [float(level["price"]) for level in row.bids if float(level.get("size", 0)) > 0]
    asks = [float(level["price"]) for level in row.asks if float(level.get("size", 0)) > 0]
    if not bids or not asks:
        return None
    return (max(bids) + min(asks)) / 2


def _spread(row: HistoricalL2Snapshot) -> float | None:
    bids = [float(level["price"]) for level in row.bids if float(level.get("size", 0)) > 0]
    asks = [float(level["price"]) for level in row.asks if float(level.get("size", 0)) > 0]
    if not bids or not asks:
        return None
    return min(asks) - max(bids)


def _depth(row: HistoricalL2Snapshot) -> float:
    return sum(float(level.get("price", 0)) * float(level.get("size", 0)) for level in (*row.bids, *row.asks))


def _intervals(rows: Sequence[HistoricalL2Snapshot]) -> list[float]:
    by_token: dict[str, list[int]] = {}
    for row in rows:
        by_token.setdefault(row.token_id, []).append(row.timestamp_ms)
    result: list[float] = []
    for timestamps in by_token.values():
        result.extend((b - a) / 1000 for a, b in zip(timestamps, timestamps[1:]) if b > a)
    return result


def _metrics(rows: Sequence[HistoricalL2Snapshot]) -> dict[str, float]:
    mids = [_mid(row) for row in rows]
    valid_mids = [value for value in mids if value is not None and value > 0]
    spreads = [_spread(row) for row in rows]
    valid_spreads = [value for value in spreads if value is not None and value >= 0]
    depths = [_depth(row) for row in rows if _depth(row) > 0]
    moves = [abs(b - a) / a for a, b in zip(valid_mids, valid_mids[1:]) if a > 0]
    return {
        "valid_book_rate": len(valid_mids) / len(rows) if rows else 0.0,
        "median_spread_bps": median(valid_spreads) * 10_000 / median(valid_mids) if valid_spreads and valid_mids else 0.0,
        "median_displayed_depth_usd": median(depths) if depths else 0.0,
        "median_abs_mid_move_bps": median(moves) * 10_000 if moves else 0.0,
    }


def _touch_through_proxy(rows: Sequence[HistoricalL2Snapshot]) -> float:
    """Estimate quote interaction from visible L2 changes; never call this a fill rate."""
    if len(rows) < 2:
        return 0.0
    eligible = 0
    moved_through = 0
    for current, following in zip(rows, rows[1:]):
        current_mid, following_mid = _mid(current), _mid(following)
        current_spread = _spread(current)
        if current_mid is None or following_mid is None or current_spread is None:
            continue
        eligible += 1
        if abs(following_mid - current_mid) >= max(current_spread / 2, 0.0001):
            moved_through += 1
    return moved_through / eligible if eligible else 0.0


def _dataset_id(rows: Sequence[HistoricalL2Snapshot]) -> str:
    if not rows:
        return "REAL_HISTORICAL_POLYMARKET:none"
    raw = "|".join(f"{row.market_id}:{row.token_id}:{row.timestamp_ms}" for row in rows)
    return f"REAL_HISTORICAL_POLYMARKET:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def calibrate_real_l2(
    rows: Iterable[HistoricalL2Snapshot],
    *,
    fee_bps: float,
    slippage_bps: float,
    dataset_id: str | None = None,
) -> CalibrationResult:
    ordered = sorted(rows, key=lambda row: (row.timestamp_ms, row.token_id))
    if not ordered:
        raise ValueError("REAL execution calibration requires at least one Polymarket L2 observation")
    train_count = max(1, math.floor(len(ordered) * 0.7))
    if len(ordered) > 1:
        train_count = min(train_count, len(ordered) - 1)
    train, out_of_sample = ordered[:train_count], ordered[train_count:]
    train_proxy = _touch_through_proxy(train)
    oos_proxy = _touch_through_proxy(out_of_sample)
    intervals = _intervals(train)
    latency = median(intervals) if intervals else 0.0
    latency_upper = max(latency, max(intervals, default=0.0))
    lower = round(max(0.01, min(0.25, train_proxy * 0.25)), 4)
    upper = round(max(lower, min(0.50, train_proxy * 0.75)), 4)
    assumption = round((lower + upper) / 2, 4)
    return CalibrationResult(
        fill_model_version=CALIBRATION_VERSION,
        calibration_dataset=dataset_id or _dataset_id(ordered),
        assumptions=(
            "L2-only touch-through is a proxy for maker interaction, not an observed fill.",
            "Exact queue position is unavailable and is not modeled.",
            "Train uses the first 70% of chronological observations; the final 30% is out-of-sample.",
            "Observed trade/cancel/order-latency records are not present in the recorder schema; snapshot intervals are not network latency.",
        ),
        maker_fill_assumption=assumption,
        maker_fill_range=(lower, upper),
        latency_assumption=round(latency, 4),
        latency_range=(0.0, round(latency_upper, 4)),
        fee_model=f"configured_paper_fee_bps:{fee_bps:g}",
        slippage_model=f"configured_paper_slippage_bps:{slippage_bps:g}; observed spread/depth reported in metrics",
        sample_count=len(ordered),
        train_count=len(train),
        out_of_sample_count=len(out_of_sample),
        train_metrics=_metrics(train) | {"touch_through_proxy_rate": round(train_proxy, 6)},
        out_of_sample_metrics=_metrics(out_of_sample) | {"touch_through_proxy_rate": round(oos_proxy, 6)},
    )


__all__ = ["CALIBRATION_VERSION", "CalibrationResult", "calibrate_real_l2"]
