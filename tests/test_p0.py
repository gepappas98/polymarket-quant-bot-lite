import pytest

from bot.execution import PaperPosition
from bot.p0 import ArbitrageScanner, ExitPolicy, settle


def test_exit_policy_take_profit_and_stop_loss():
    position = PaperPosition("m", "UP", 10, .50)
    assert ExitPolicy(take_profit=.1).decide(position, .56).reason == "TAKE_PROFIT"
    assert ExitPolicy(stop_loss=.1).decide(position, .44).reason == "STOP_LOSS"


def test_settlement_realized_pnl():
    result = settle(PaperPosition("m", "UP", 10, .50), "UP")
    assert result.payout_usd == 10
    assert result.realized_pnl == 5


def test_arbitrage_scanner_requires_positive_edge():
    scanner = ArbitrageScanner(min_edge=.01)
    assert scanner.scan("m", .48, .48).net_edge == pytest.approx(.04)
    assert scanner.scan("m", .5, .51) is None
