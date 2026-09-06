from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence
import time
import uuid


class OrderState(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


_TERMINAL = {OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED}
_ALLOWED = {
    OrderState.NEW: {OrderState.SUBMITTED, OrderState.REJECTED},
    OrderState.SUBMITTED: {OrderState.OPEN, OrderState.PARTIAL, OrderState.CANCEL_REQUESTED, OrderState.REJECTED},
    OrderState.OPEN: {OrderState.PARTIAL, OrderState.CANCEL_REQUESTED},
    OrderState.PARTIAL: {OrderState.PARTIAL, OrderState.CANCEL_REQUESTED},
    OrderState.CANCEL_REQUESTED: {OrderState.CANCELLED, OrderState.PARTIAL, OrderState.FILLED},
    OrderState.FILLED: set(), OrderState.CANCELLED: set(), OrderState.REJECTED: set(),
}


class ExecutionError(ValueError):
    pass


class Clock:
    def now(self) -> float:
        return time.time()


class ManualClock(Clock):
    def __init__(self, value: float = 0.0):
        self.value = value

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass(frozen=True)
class Fill:
    order_id: str
    shares: float
    price: float
    fee_usd: float = 0.0
    ts: float = field(default_factory=time.time)


@dataclass
class Order:
    market: str
    side: str
    action: str
    requested_usd: float
    limit_price: float
    order_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: OrderState = OrderState.NEW
    fills: list[Fill] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def filled_shares(self) -> float:
        return sum(fill.shares for fill in self.fills)

    @property
    def filled_usd(self) -> float:
        return sum(fill.shares * fill.price for fill in self.fills)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.requested_usd - self.filled_usd)

    @property
    def vwap(self) -> Optional[float]:
        return self.filled_usd / self.filled_shares if self.filled_shares else None

    def transition(self, state: OrderState) -> None:
        if state not in _ALLOWED[self.state]:
            raise ExecutionError(f"invalid order transition {self.state.value} -> {state.value}")
        self.state = state

    def add_fill(self, fill: Fill) -> None:
        if fill.order_id != self.order_id or fill.shares <= 0 or fill.price <= 0:
            raise ExecutionError("invalid fill")
        if self.state in _TERMINAL and self.state != OrderState.FILLED:
            raise ExecutionError("cannot fill a cancelled or rejected order")
        self.fills.append(fill)
        target = OrderState.FILLED if self.remaining_usd <= 1e-9 else OrderState.PARTIAL
        if self.state == OrderState.NEW:
            self.transition(OrderState.SUBMITTED)
        if target is OrderState.PARTIAL and self.state not in {OrderState.SUBMITTED, OrderState.OPEN, OrderState.PARTIAL}:
            raise ExecutionError(f"invalid partial fill state {self.state.value}")
        if target is OrderState.FILLED and self.state not in {OrderState.SUBMITTED, OrderState.OPEN, OrderState.PARTIAL}:
            raise ExecutionError(f"invalid filled state {self.state.value}")
        self.state = target


@dataclass(frozen=True)
class BookLevel:
    price: float
    shares: float


@dataclass(frozen=True)
class OrderBook:
    bids: tuple[BookLevel, ...] = ()
    asks: tuple[BookLevel, ...] = ()

    @classmethod
    def from_levels(cls, bids: Sequence[Mapping[str, float]], asks: Sequence[Mapping[str, float]]) -> "OrderBook":
        return cls(tuple(BookLevel(float(x["price"]), float(x["shares"])) for x in bids), tuple(BookLevel(float(x["price"]), float(x["shares"])) for x in asks))


@dataclass(frozen=True)
class ExecutionReport:
    fills: tuple[Fill, ...]
    requested_usd: float
    filled_usd: float
    residual_usd: float
    vwap: Optional[float]
    fees_usd: float
    slippage_usd: float


class PaperFillEngine:
    def __init__(self, fee_bps: float = 0.0, slippage_bps: float = 0.0):
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    def execute(self, order: Order, book: OrderBook) -> ExecutionReport:
        levels = book.asks if order.action.upper() == "BUY" else book.bids
        remaining = order.requested_usd
        fills: list[Fill] = []
        for level in levels:
            if remaining <= 1e-9:
                break
            if level.price <= 0 or level.shares <= 0:
                continue
            notional = min(remaining, level.price * level.shares)
            shares = notional / level.price
            fee = notional * self.fee_bps / 10_000
            fill = Fill(order.order_id, shares, level.price, fee)
            order.add_fill(fill)
            fills.append(fill)
            remaining -= notional
        if not fills and order.state == OrderState.NEW:
            order.transition(OrderState.SUBMITTED)
            order.transition(OrderState.OPEN)
        vwap = order.vwap
        slippage = sum(fill.shares * abs(fill.price - order.limit_price) for fill in fills)
        slippage += order.filled_usd * self.slippage_bps / 10_000
        return ExecutionReport(tuple(fills), order.requested_usd, order.filled_usd, order.remaining_usd, vwap, sum(x.fee_usd for x in fills), slippage)


@dataclass
class PaperPosition:
    market: str
    side: str
    shares: float
    avg_price: float


@dataclass
class PaperAccount:
    starting_bankroll: float = 10_000.0
    cash: float = 10_000.0
    daily_loss_limit: float = 500.0
    realized_pnl: float = 0.0
    positions: dict[tuple[str, str], PaperPosition] = field(default_factory=dict)
    trades: list[dict] = field(default_factory=list)

    def buy(self, market: str, side: str, report: ExecutionReport) -> None:
        if report.filled_usd > self.cash + 1e-9:
            raise ExecutionError("insufficient paper cash")
        self.cash -= report.filled_usd + report.fees_usd
        key = (market, side)
        previous = self.positions.get(key)
        shares = sum(fill.shares for fill in report.fills)
        if shares:
            total_cost = (previous.shares * previous.avg_price if previous else 0.0) + report.filled_usd
            total_shares = (previous.shares if previous else 0.0) + shares
            self.positions[key] = PaperPosition(market, side, total_shares, total_cost / total_shares)
        self.trades.append({"action": "BUY", "market": market, "side": side, "shares": shares, "price": report.vwap, "fees": report.fees_usd})

    def sell(self, market: str, side: str, report: ExecutionReport) -> float:
        key = (market, side)
        position = self.positions.get(key)
        shares = sum(fill.shares for fill in report.fills)
        if not position or shares <= 0 or shares > position.shares + 1e-9:
            raise ExecutionError("insufficient paper position")
        proceeds = report.filled_usd
        pnl = proceeds - shares * position.avg_price - report.fees_usd
        self.cash += proceeds - report.fees_usd
        self.realized_pnl += pnl
        position.shares -= shares
        if position.shares <= 1e-9:
            del self.positions[key]
        self.trades.append({"action": "SELL", "market": market, "side": side, "shares": shares, "price": report.vwap, "fees": report.fees_usd, "realized_pnl": pnl})
        return pnl

    def risk_check(self, requested_usd: float) -> tuple[bool, str]:
        if requested_usd <= 0:
            return False, "order size must be positive"
        if requested_usd > self.cash:
            return False, "insufficient paper cash"
        if self.realized_pnl <= -abs(self.daily_loss_limit):
            return False, "daily loss limit reached"
        return True, "ok"


@dataclass(frozen=True)
class ArbPair:
    market: str
    up_cost: float
    down_cost: float

    @property
    def net_edge(self) -> float:
        return 1.0 - self.up_cost - self.down_cost

    @property
    def executable(self) -> bool:
        return self.net_edge > 0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["ArbPair", "BookLevel", "Clock", "ExecutionError", "ExecutionReport", "Fill", "ManualClock", "Order", "OrderBook", "OrderState", "PaperAccount", "PaperFillEngine", "PaperPosition"]
