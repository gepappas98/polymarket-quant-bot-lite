import time

import pytest

from bot.config import cfg
from bot.ledger import LedgerEntry, ledger
from bot.portfolio_gates import LowProfitPairLock, max_drawdown_gate, session_pnl


@pytest.fixture(autouse=True)
def isolate_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "path", tmp_path / "trades.jsonl")
    ledger._entries.clear()
    yield
    ledger._entries.clear()


def _outcome(slug, pnl):
    ledger._entries.append(LedgerEntry(
        ts=time.time(), kind="outcome", market_slug=slug, pnl_usd=pnl,
        dry_run=True, status="closed",
    ))


class TestSessionPnl:
    def test_zero_with_no_outcomes(self):
        assert session_pnl() == 0

    def test_sums_all_outcome_pnl(self):
        _outcome("btc-1", 5.0)
        _outcome("btc-2", -2.0)
        _outcome("eth-1", 3.0)
        assert session_pnl() == pytest.approx(6.0)

    def test_ignores_non_outcome_entries(self):
        ledger._entries.append(LedgerEntry(
            ts=time.time(), kind="intent", market_slug="btc-1", size_usd=10,
            dry_run=True, status="open",
        ))
        _outcome("btc-1", 5.0)
        assert session_pnl() == pytest.approx(5.0)


class TestMaxDrawdownGate:
    def test_allowed_when_pnl_above_limit(self, monkeypatch):
        monkeypatch.setattr(cfg, "daily_loss_limit_usd", -200.0)
        _outcome("btc-1", -50.0)
        result = max_drawdown_gate()
        assert result.allowed is True

    def test_blocked_when_pnl_at_or_below_limit(self, monkeypatch):
        monkeypatch.setattr(cfg, "daily_loss_limit_usd", -200.0)
        _outcome("btc-1", -150.0)
        _outcome("btc-2", -60.0)  # cumulative -210
        result = max_drawdown_gate()
        assert result.allowed is False
        assert "drawdown" in result.reason.lower()

    def test_allowed_with_no_history(self, monkeypatch):
        monkeypatch.setattr(cfg, "daily_loss_limit_usd", -200.0)
        result = max_drawdown_gate()
        assert result.allowed is True


class TestLowProfitPairLock:
    def test_check_allows_unlocked_market(self):
        pl = LowProfitPairLock(lookback=3, loss_threshold_usd=0.0, lock_minutes=30)
        result = pl.check("btc-updown-5m-1")
        assert result.allowed is True

    def test_refresh_does_nothing_below_lookback_sample_size(self):
        pl = LowProfitPairLock(lookback=5, loss_threshold_usd=0.0, lock_minutes=30)
        _outcome("btc-updown-5m-2", -5.0)
        _outcome("btc-updown-5m-2", -5.0)  # only 2, need 5
        pl.refresh("btc-updown-5m-2")
        assert pl.check("btc-updown-5m-2").allowed is True

    def test_refresh_locks_after_enough_losing_outcomes(self):
        pl = LowProfitPairLock(lookback=3, loss_threshold_usd=0.0, lock_minutes=30)
        for _ in range(3):
            _outcome("btc-updown-5m-3", -5.0)
        pl.refresh("btc-updown-5m-3")
        result = pl.check("btc-updown-5m-3")
        assert result.allowed is False
        assert "pair lock" in result.reason.lower()

    def test_refresh_does_not_lock_when_recent_pnl_is_positive(self):
        pl = LowProfitPairLock(lookback=3, loss_threshold_usd=0.0, lock_minutes=30)
        _outcome("btc-updown-5m-4", 5.0)
        _outcome("btc-updown-5m-4", 5.0)
        _outcome("btc-updown-5m-4", -3.0)  # net +7, above threshold
        pl.refresh("btc-updown-5m-4")
        assert pl.check("btc-updown-5m-4").allowed is True

    def test_lock_expires_after_lock_minutes(self):
        pl = LowProfitPairLock(lookback=1, loss_threshold_usd=0.0, lock_minutes=-0.001)  # already expired
        _outcome("btc-updown-5m-5", -5.0)
        pl.refresh("btc-updown-5m-5")
        # lock_minutes negative => "until" is already in the past
        assert pl.check("btc-updown-5m-5").allowed is True

    def test_other_markets_are_unaffected(self):
        pl = LowProfitPairLock(lookback=2, loss_threshold_usd=0.0, lock_minutes=30)
        for _ in range(2):
            _outcome("btc-updown-5m-6", -5.0)
        pl.refresh("btc-updown-5m-6")
        assert pl.check("eth-updown-5m-1").allowed is True

    def test_status_lists_only_active_locks(self):
        pl = LowProfitPairLock(lookback=2, loss_threshold_usd=0.0, lock_minutes=30)
        for _ in range(2):
            _outcome("btc-updown-5m-7", -5.0)
        pl.refresh("btc-updown-5m-7")
        assert "btc-updown-5m-7" in pl.status()
