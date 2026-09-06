import pytest

from bot.execution import (
    ExecutionError,
    ManualClock,
    Order,
    OrderBook,
    OrderState,
    PaperAccount,
    PaperFillEngine,
)


def test_lifecycle_requires_confirmed_fill_before_filled():
    order = Order("m", "UP", "BUY", 25, 0.49)
    order.transition(OrderState.SUBMITTED)
    order.transition(OrderState.OPEN)
    assert order.state is OrderState.OPEN
    with pytest.raises(ExecutionError):
        order.transition(OrderState.FILLED)


def test_paper_engine_consumes_depth_and_aggregates_vwap():
    order = Order("m", "UP", "BUY", 25, 0.49)
    book = OrderBook.from_levels([], [{"price": .49, "shares": 5/.49}, {"price": .50, "shares": 10/.50}, {"price": .51, "shares": 10/.51}])
    report = PaperFillEngine(fee_bps=10).execute(order, book)
    assert report.filled_usd == pytest.approx(25)
    assert report.vwap == pytest.approx(25 / (5/.49 + 10/.50 + 10/.51))
    assert report.residual_usd == pytest.approx(0)
    assert report.fees_usd == pytest.approx(.025)
    assert order.state is OrderState.FILLED


def test_paper_account_buy_sell_realizes_pnl():
    account = PaperAccount(starting_bankroll=100, cash=100)
    buy = Order("m", "UP", "BUY", 10, .5)
    buy_report = PaperFillEngine().execute(buy, OrderBook.from_levels([], [{"price": .5, "shares": 20}]))
    account.buy("m", "UP", buy_report)
    sell = Order("m", "UP", "SELL", 12, .6)
    sell_report = PaperFillEngine().execute(sell, OrderBook.from_levels([{"price": .6, "shares": 20}], []))
    assert account.sell("m", "UP", sell_report) == pytest.approx(2)
    assert account.realized_pnl == pytest.approx(2)


def test_manual_clock_is_deterministic():
    clock = ManualClock(100)
    clock.advance(2.5)
    assert clock.now() == 102.5
