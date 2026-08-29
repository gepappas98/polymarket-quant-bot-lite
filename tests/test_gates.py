import os
import time

import pytest

from bot.gates import CooldownLock, GateResult, gate_intent, is_live_trading_allowed
from bot.config import cfg


class TestLiveTradingGate:
    def test_defaults_to_blocked_in_paper_mode(self, monkeypatch):
        monkeypatch.setenv("MODE", "paper")
        result = is_live_trading_allowed()
        assert result.allowed is False
        assert "not live" in result.reason.lower()

    def test_blocked_without_confirm_phrase(self, monkeypatch):
        monkeypatch.setenv("MODE", "live")
        monkeypatch.delenv("LIVE_TRADING_CONFIRM", raising=False)
        monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0xabc")
        result = is_live_trading_allowed()
        assert result.allowed is False
        assert "LIVE_TRADING_CONFIRM" in result.reason

    def test_blocked_with_wrong_confirm_phrase(self, monkeypatch):
        monkeypatch.setenv("MODE", "live")
        monkeypatch.setenv("LIVE_TRADING_CONFIRM", "yes please")
        monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0xabc")
        result = is_live_trading_allowed()
        assert result.allowed is False

    def test_blocked_without_private_key(self, monkeypatch):
        monkeypatch.setenv("MODE", "live")
        monkeypatch.setenv("LIVE_TRADING_CONFIRM", "I_UNDERSTAND_THE_RISK")
        monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)
        monkeypatch.setattr(cfg, "private_key", "")
        result = is_live_trading_allowed()
        assert result.allowed is False
        assert "PRIVATE_KEY" in result.reason

    def test_allowed_when_all_three_conditions_met(self, monkeypatch):
        monkeypatch.setenv("MODE", "live")
        monkeypatch.setenv("LIVE_TRADING_CONFIRM", "I_UNDERSTAND_THE_RISK")
        monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0xabc")
        result = is_live_trading_allowed()
        assert result.allowed is True

    def test_fails_closed_never_raises(self, monkeypatch):
        """Whatever the env holds, this must return a GateResult, never throw."""
        monkeypatch.setenv("MODE", "live")
        result = is_live_trading_allowed()
        assert isinstance(result, GateResult)


class TestCooldownLock:
    def test_first_admission_is_allowed(self):
        cd = CooldownLock(minutes=5)
        result = cd.check_and_lock("btc-updown-5m-123")
        assert result.allowed is True

    def test_second_admission_within_window_is_blocked(self):
        cd = CooldownLock(minutes=5)
        cd.check_and_lock("btc-updown-5m-123")
        result = cd.check_and_lock("btc-updown-5m-123")
        assert result.allowed is False
        assert "cooldown" in result.reason.lower()

    def test_different_markets_do_not_share_a_lock(self):
        cd = CooldownLock(minutes=5)
        cd.check_and_lock("btc-updown-5m-123")
        result = cd.check_and_lock("eth-updown-5m-999")
        assert result.allowed is True

    def test_clear_releases_the_lock_immediately(self):
        cd = CooldownLock(minutes=5)
        cd.check_and_lock("btc-updown-5m-123")
        cd.clear("btc-updown-5m-123")
        result = cd.check_and_lock("btc-updown-5m-123")
        assert result.allowed is True

    def test_status_only_lists_active_locks(self):
        cd = CooldownLock(minutes=5)
        cd.check_and_lock("btc-updown-5m-123")
        assert "btc-updown-5m-123" in cd.status()
        cd.clear("btc-updown-5m-123")
        assert "btc-updown-5m-123" not in cd.status()

    def test_get_until_returns_none_when_not_locked(self):
        cd = CooldownLock(minutes=5)
        assert cd.get_until("never-locked-slug") is None

    def test_get_until_returns_future_timestamp_when_locked(self):
        cd = CooldownLock(minutes=5)
        before = time.time()
        cd.check_and_lock("btc-updown-5m-123")
        until = cd.get_until("btc-updown-5m-123")
        assert until is not None
        assert until > before


class TestGateIntent:
    def test_rejects_zero_or_negative_size(self, monkeypatch):
        monkeypatch.setattr(cfg, "mode", "paper")
        result = gate_intent("btc-updown-5m-1", size_usd=0)
        assert result.allowed is False

    def test_rejects_size_above_max_order(self, monkeypatch):
        monkeypatch.setattr(cfg, "mode", "paper")
        monkeypatch.setattr(cfg, "max_order_usd", 25.0)
        result = gate_intent("btc-updown-5m-2", size_usd=1000)
        assert result.allowed is False

    def test_accepts_reasonable_size_first_time(self, monkeypatch):
        monkeypatch.setattr(cfg, "mode", "paper")
        monkeypatch.setattr(cfg, "max_order_usd", 25.0)
        result = gate_intent("btc-updown-5m-3", size_usd=10)
        assert result.allowed is True

    def test_second_call_same_market_hits_cooldown(self, monkeypatch):
        monkeypatch.setattr(cfg, "mode", "paper")
        monkeypatch.setattr(cfg, "max_order_usd", 25.0)
        slug = "btc-updown-5m-4"
        first = gate_intent(slug, size_usd=10)
        second = gate_intent(slug, size_usd=10)
        assert first.allowed is True
        assert second.allowed is False

    def test_arb_leg_uses_shorter_cooldown_and_restores_original(self, monkeypatch):
        from bot.gates import cooldown

        monkeypatch.setattr(cfg, "mode", "paper")
        monkeypatch.setattr(cfg, "max_order_usd", 25.0)
        original_minutes = cooldown.minutes
        result = gate_intent("btc-updown-5m-5", size_usd=10, is_arb=True)
        assert result.allowed is True
        # Global cooldown setting must be restored after the arb-specific tweak.
        assert cooldown.minutes == original_minutes

    def test_live_mode_defers_to_live_trading_gate(self, monkeypatch):
        monkeypatch.setattr(cfg, "mode", "live")
        monkeypatch.setenv("MODE", "live")
        monkeypatch.delenv("LIVE_TRADING_CONFIRM", raising=False)
        result = gate_intent("btc-updown-5m-6", size_usd=10)
        assert result.allowed is False
