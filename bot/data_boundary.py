"""Explicit data and execution boundary used by worker status payloads.

These values describe provenance, not profitability or authorization. Real
market data may be consumed by paper execution, but paper fills never become
real fills.
"""
from __future__ import annotations

from enum import Enum


class DataSource(str, Enum):
    REAL = "REAL"
    PAPER = "PAPER"
    DEMO = "DEMO"
    MOCK = "MOCK"


class ExecutionMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    DEMO = "DEMO"
    MOCK = "MOCK"


def worker_boundary(*, execution_mode: str, market_data_source: DataSource = DataSource.REAL) -> dict:
    """Return explicit provenance metadata for a worker status response."""
    mode = str(execution_mode or ExecutionMode.PAPER).upper()
    is_simulated = mode != ExecutionMode.LIVE
    return {
        "data_source": DataSource.REAL.value,
        "execution_mode": mode,
        "market_data_source": market_data_source.value,
        "is_simulated": is_simulated,
    }


def demo_boundary() -> dict:
    return {
        "data_source": DataSource.DEMO.value,
        "execution_mode": ExecutionMode.DEMO.value,
        "market_data_source": DataSource.DEMO.value,
        "is_simulated": True,
    }
