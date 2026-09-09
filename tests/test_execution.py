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
    assert report.filled_usd == pytest.approx(5)
    assert report.vwap == pytest.approx(.49)
    assert report.residual_usd == pytest.approx(20)
    assert report.fees_usd == pytest.approx(.005)
    assert report.slippage_usd == pytest.approx(0)
    assert order.state is OrderState.PARTIAL


def test_paper_engine_empty_eligible_depth_does_not_synthesize_a_fill():
    order = Order("m", "UP", "BUY", 10, 0.49)
    book = OrderBook.from_levels([], [{"price": .50, "shares": 100}])
    report = PaperFillEngine().execute(order, book)
    assert report.fills == ()
    assert report.filled_usd == pytest.approx(0)
    assert report.residual_usd == pytest.approx(10)
    assert report.vwap is None
    assert order.state is OrderState.OPEN


def test_sell_limit_consumes_only_bids_at_or_above_limit():
    order = Order("m", "UP", "SELL", 15, 0.51)
    book = OrderBook.from_levels(
        [{"price": .52, "shares": 5/.52}, {"price": .51, "shares": 5/.51}, {"price": .50, "shares": 20}],
        [],
    )
    report = PaperFillEngine().execute(order, book)
    assert report.filled_usd == pytest.approx(10)
    assert report.residual_usd == pytest.approx(5)
    assert report.vwap == pytest.approx(10 / (5/.52 + 5/.51))
    assert report.slippage_usd == pytest.approx(-5/.52 * .01)
    assert order.state is OrderState.PARTIAL


def test_live_gtc_limit_and_paper_engine_share_eligible_price_contract():
    # LiveExecutor sends intent.price as the GTC price. Paper uses the same
    # value as Order.limit_price and therefore cannot consume .50/.51 behind
    # a BUY limit of .49 on the same book.
    intent_limit = 0.49
    order = Order("m", "UP", "BUY", 15, intent_limit)
    book = OrderBook.from_levels([], [{"price": .49, "shares": 5/.49}, {"price": .50, "shares": 20}])
    report = PaperFillEngine().execute(order, book)
    assert intent_limit == order.limit_price
    assert [fill.price for fill in report.fills] == [.49]
    assert report.residual_usd == pytest.approx(10)


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
