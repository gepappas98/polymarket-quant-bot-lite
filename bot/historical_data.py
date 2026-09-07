"""Historical market-data contracts and the REAL Polymarket recorder reader."""
from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence

REAL_HISTORICAL_SOURCE = "REAL_HISTORICAL_POLYMARKET"


class HistoricalDataUnavailable(RuntimeError):
    """Raised when a REAL historical replay cannot load its requested data."""


@dataclass(frozen=True)
class HistoricalL2Snapshot:
    market_id: str
    token_id: str
    timestamp_ms: int
    bids: tuple[dict, ...]
    asks: tuple[dict, ...]
    condition_id: str | None = None
    outcome: str | None = None
    event_timestamp_ms: int | None = None
    sequence_id: str | None = None
    event_type: str | None = None

    @property
    def timestamp(self) -> float:
        return self.timestamp_ms / 1000.0


class HistoricalMarketData(ABC):
    """Deterministic chronological source of complete L2 book states."""

    data_source = REAL_HISTORICAL_SOURCE

    @abstractmethod
    def snapshots(
        self,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        market_id: str | None = None,
        token_id: str | None = None,
    ) -> Iterable[HistoricalL2Snapshot]:
        raise NotImplementedError

    def require_snapshots(self, **filters) -> list[HistoricalL2Snapshot]:
        rows = list(self.snapshots(**filters))
        if not rows:
            raise HistoricalDataUnavailable(
                "REAL historical Polymarket data is unavailable for the requested market/token/time range; "
                "no synthetic or demo fallback is allowed"
            )
        return rows


class PolymarketHistoricalL2DataSource(HistoricalMarketData):
    """Read append-only snapshots written by ``bot.historical_recorder``."""

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)

    def snapshots(
        self,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        market_id: str | None = None,
        token_id: str | None = None,
    ) -> Iterator[HistoricalL2Snapshot]:
        if not Path(self.database_path).is_file():
            raise HistoricalDataUnavailable(
                f"REAL historical Polymarket database does not exist: {self.database_path}; "
                "synthetic/demo fallback is disabled"
            )
        query = [
            "SELECT market_id, condition_id, token_id, outcome, timestamp_ms, event_timestamp_ms, "
            "COALESCE(event_timestamp_ms, timestamp_ms) AS replay_timestamp_ms, bids_json, asks_json, sequence_id, event_type FROM l2_book_snapshots",
            "WHERE source = 'polymarket_clob' AND data_source = 'REAL'",
        ]
        params: list[object] = []
        if start_ms is not None:
            query.append("AND COALESCE(event_timestamp_ms, timestamp_ms) >= ?"); params.append(start_ms)
        if end_ms is not None:
            query.append("AND COALESCE(event_timestamp_ms, timestamp_ms) <= ?"); params.append(end_ms)
        if market_id is not None:
            query.append("AND market_id = ?"); params.append(market_id)
        if token_id is not None:
            query.append("AND token_id = ?"); params.append(token_id)
        query.append("ORDER BY COALESCE(event_timestamp_ms, timestamp_ms) ASC, id ASC")
        try:
            conn = sqlite3.connect(self.database_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(" ".join(query), params).fetchall()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise HistoricalDataUnavailable(f"cannot read REAL Polymarket historical database: {exc}") from exc
        for row in rows:
            try:
                bids = tuple(json.loads(row["bids_json"]))
                asks = tuple(json.loads(row["asks_json"]))
                if not isinstance(bids, tuple) or not isinstance(asks, tuple):
                    raise ValueError("book levels must be arrays")
                yield HistoricalL2Snapshot(
                    market_id=row["market_id"], token_id=row["token_id"], timestamp_ms=int(row["replay_timestamp_ms"]),
                    bids=bids, asks=asks, condition_id=row["condition_id"], outcome=row["outcome"],
                    event_timestamp_ms=row["event_timestamp_ms"], sequence_id=row["sequence_id"], event_type=row["event_type"],
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise HistoricalDataUnavailable(f"malformed REAL historical row for token {row['token_id']}: {exc}") from exc

    def coverage(self, **filters) -> dict:
        rows = self.require_snapshots(**filters)
        timestamps = [row.timestamp_ms for row in rows]
        return {
            "data_source": self.data_source,
            "rows": len(rows),
            "markets": sorted({row.market_id for row in rows}),
            "tokens": sorted({row.token_id for row in rows}),
            "start_ms": min(timestamps),
            "end_ms": max(timestamps),
            "duration_ms": max(timestamps) - min(timestamps),
            "quality_warnings": _quality_warnings(rows),
        }


def _quality_warnings(rows: Sequence[HistoricalL2Snapshot]) -> list[str]:
    warnings: list[str] = []
    if any(row.event_timestamp_ms is None for row in rows):
        warnings.append("some rows do not contain an exchange event timestamp")
    if any(not row.bids or not row.asks for row in rows):
        warnings.append("some snapshots have one-sided or empty depth")
    if any(row.outcome is None for row in rows):
        warnings.append("some rows do not contain outcome metadata")
    return warnings


__all__ = ["HistoricalDataUnavailable", "HistoricalL2Snapshot", "HistoricalMarketData", "PolymarketHistoricalL2DataSource", "REAL_HISTORICAL_SOURCE"]
