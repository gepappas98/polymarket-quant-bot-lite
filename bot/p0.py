from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .execution import ArbPair, PaperPosition


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: str


class ExitPolicy:
    def __init__(self, take_profit: float = 0.10, stop_loss: float = 0.10):
        self.take_profit = take_profit
        self.stop_loss = stop_loss

    def decide(self, position: PaperPosition, mark_price: float) -> ExitDecision:
        if mark_price >= position.avg_price * (1 + self.take_profit):
            return ExitDecision(True, "TAKE_PROFIT")
        if mark_price <= position.avg_price * (1 - self.stop_loss):
            return ExitDecision(True, "STOP_LOSS")
        return ExitDecision(False, "HOLD")


@dataclass(frozen=True)
class Settlement:
    market: str
    side: str
    shares: float
    payout_usd: float
    realized_pnl: float


def settle(position: PaperPosition, winning_side: str, payout_per_share: float = 1.0) -> Settlement:
    payout = position.shares * payout_per_share if position.side == winning_side else 0.0
    return Settlement(position.market, position.side, position.shares, payout, payout - position.shares * position.avg_price)


class ArbitrageScanner:
    def __init__(self, min_edge: float = 0.0):
        self.min_edge = min_edge

    def scan(self, market: str, up_cost: float, down_cost: float) -> Optional[ArbPair]:
        pair = ArbPair(market, up_cost, down_cost)
        return pair if pair.net_edge >= self.min_edge and pair.executable else None

    def scan_many(self, rows: Sequence[tuple[str, float, float]]) -> list[ArbPair]:
        return [pair for pair in (self.scan(*row) for row in rows) if pair is not None]
