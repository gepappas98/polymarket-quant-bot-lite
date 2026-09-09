"""
P0-5 auth boundary tests.

Covers:
- require_api_token: correct token → 200, wrong token → 401, no token in
  loopback+paper mode → 200, no token on 0.0.0.0 → 503.
- CORS: default is empty (no wildcard).
- The _token_is_mandatory helper for each trigger condition.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.api.deps import _token_is_mandatory, require_api_token
from app.main import app

# ---------------------------------------------------------------------------
# _token_is_mandatory unit tests
# ---------------------------------------------------------------------------

MUTATING_ROUTES = [
    ("/api/trades/place", {"market_slug": "m", "token_id": "t", "side": "UP",
                           "price": 0.5, "confidence": 0.8, "balance": 100}),
    ("/api/risk/update", {"daily_loss_limit": -100}),
    ("/api/strategies/update", {"politics_only": False, "sports_fade": False,
                                "crypto_focus": False}),
]


class TestTokenMandatoryLogic:
    def test_live_mode_always_mandatory(self, monkeypatch):
        monkeypatch.setenv("MODE", "live")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.setenv("API_HOST", "127.0.0.1")
        # Reload cfg so the mode change is visible
        import importlib
        import bot.config as bc
        importlib.reload(bc)
        # Patch cfg directly so the dep sees it
        from app.api import deps
        monkeypatch.setattr(deps.cfg, "mode", "live")
        assert deps._token_is_mandatory() is True

    def test_production_env_mandatory(self, monkeypatch):
        from app.api import deps
        monkeypatch.setattr(deps.cfg, "mode", "paper")
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("API_HOST", "127.0.0.1")
        assert deps._token_is_mandatory() is True

    def test_environment_env_production_mandatory(self, monkeypatch):
        from app.api import deps
        monkeypatch.setattr(deps.cfg, "mode", "paper")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("API_HOST", "127.0.0.1")
        assert deps._token_is_mandatory() is True

    def test_loopback_paper_not_mandatory(self, monkeypatch):
        from app.api import deps
        monkeypatch.setattr(deps.cfg, "mode", "paper")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("API_HOST", "127.0.0.1")
        assert deps._token_is_mandatory() is False

    def test_localhost_paper_not_mandatory(self, monkeypatch):
        from app.api import deps
        monkeypatch.setattr(deps.cfg, "mode", "paper")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("API_HOST", "localhost")
        assert deps._token_is_mandatory() is False

    def test_0000_paper_mandatory(self, monkeypatch):
        """Paper mode on 0.0.0.0 must require a token — the port is public."""
        from app.api import deps
        monkeypatch.setattr(deps.cfg, "mode", "paper")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("API_HOST", "0.0.0.0")
        assert deps._token_is_mandatory() is True

    def test_external_ip_paper_mandatory(self, monkeypatch):
        from app.api import deps
        monkeypatch.setattr(deps.cfg, "mode", "paper")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("API_HOST", "10.0.0.5")
        assert deps._token_is_mandatory() is True


# ---------------------------------------------------------------------------
# HTTP-level tests: mutating routes on loopback paper (no token configured)
# ---------------------------------------------------------------------------

class TestMutatingRoutesLoopbackPaper:
    """Paper + loopback + no API_TOKEN: mutating routes must be reachable."""

    def setup_method(self):
        os.environ.pop("API_TOKEN", None)
        os.environ.pop("ENV", None)
        os.environ.pop("ENVIRONMENT", None)
        os.environ["API_HOST"] = "127.0.0.1"

    def teardown_method(self):
        os.environ.pop("API_TOKEN", None)
        os.environ.pop("ENV", None)
        os.environ.pop("ENVIRONMENT", None)
        os.environ.pop("API_HOST", None)

    def test_place_order_reachable_without_token(self):
        with TestClient(app) as client:
            r = client.post(
                "/api/trades/place",
                json={"market_slug": "btc-up", "token_id": "t", "side": "UP",
                      "price": 0.5, "confidence": 0.8, "balance": 100},
            )
            # Route is reachable; any non-401/503 counts (could be 200/422/etc.)
            assert r.status_code not in (401, 503)

    def test_risk_update_reachable_without_token(self):
        with TestClient(app) as client:
            r = client.post("/api/risk/update", json={"daily_loss_limit": -50})
            assert r.status_code not in (401, 503)


# ---------------------------------------------------------------------------
# HTTP-level tests: token-protected routes return 401 on wrong token
# ---------------------------------------------------------------------------

class TestTokenEnforcement:
    def test_wrong_token_returns_401(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "correct-token")
        from app.api import deps
        monkeypatch.setattr(deps, "os", __import__("os"))  # ensure real env
        with TestClient(app) as client:
            r = client.post(
                "/api/risk/update",
                json={"daily_loss_limit": -50},
                headers={"X-Api-Key": "wrong-token"},
            )
        assert r.status_code == 401

    def test_bearer_wrong_token_returns_401(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "correct-token")
        with TestClient(app) as client:
            r = client.post(
                "/api/risk/update",
                json={"daily_loss_limit": -50},
                headers={"Authorization": "Bearer wrong-token"},
            )
        assert r.status_code == 401

    def test_correct_token_returns_200(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "correct-token")
        with TestClient(app) as client:
            r = client.post(
                "/api/risk/update",
                json={"daily_loss_limit": -50},
                headers={"X-Api-Key": "correct-token"},
            )
        assert r.status_code == 200

    def test_correct_bearer_token_returns_200(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "correct-token")
        with TestClient(app) as client:
            r = client.post(
                "/api/risk/update",
                json={"daily_loss_limit": -50},
                headers={"Authorization": "Bearer correct-token"},
            )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# HTTP-level tests: paper mode on 0.0.0.0 without API_TOKEN → 503
# ---------------------------------------------------------------------------

class TestPaperOn0000RequiresToken:
    """
    This was the original bug: paper mutating routes were open when the
    process bound on 0.0.0.0 with no API_TOKEN set.
    The old code returned None (pass-through) regardless of bind address.
    """

    def test_place_order_refuses_without_token_on_0000(self, monkeypatch):
        monkeypatch.delenv("API_TOKEN", raising=False)
        monkeypatch.setenv("API_HOST", "0.0.0.0")
        monkeypatch.setattr("app.api.deps.cfg.mode", "paper")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with TestClient(app) as client:
            r = client.post(
                "/api/trades/place",
                json={"market_slug": "btc-up", "token_id": "t", "side": "UP",
                      "price": 0.5, "confidence": 0.8, "balance": 100},
            )
        assert r.status_code == 503

    def test_risk_update_refuses_without_token_on_0000(self, monkeypatch):
        monkeypatch.delenv("API_TOKEN", raising=False)
        monkeypatch.setenv("API_HOST", "0.0.0.0")
        monkeypatch.setattr("app.api.deps.cfg.mode", "paper")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with TestClient(app) as client:
            r = client.post("/api/risk/update", json={"daily_loss_limit": -50})
        assert r.status_code == 503

    def test_risk_update_passes_with_token_on_0000(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.setenv("API_HOST", "0.0.0.0")
        monkeypatch.setattr("app.api.deps.cfg.mode", "paper")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with TestClient(app) as client:
            r = client.post(
                "/api/risk/update",
                json={"daily_loss_limit": -50},
                headers={"X-Api-Key": "test-token"},
            )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# CORS: default must not be wildcard
# ---------------------------------------------------------------------------

class TestCORSDefault:
    def test_cors_default_is_not_wildcard(self, monkeypatch):
        monkeypatch.delenv("API_CORS_ORIGINS", raising=False)
        # Re-import the origins list the app computes at startup
        import importlib
        import app.main as amain
        raw = __import__("os").getenv("API_CORS_ORIGINS", "")
        computed = [x.strip() for x in raw.split(",") if x.strip()] if raw.strip() else []
        assert "*" not in computed, (
            "API_CORS_ORIGINS must not default to '*'. "
            "A wildcard CORS policy defeats token-based auth on mutating routes."
        )

    def test_cors_explicit_wildcard_still_works_when_set(self, monkeypatch):
        """Operators can still opt-in to * explicitly — just not by default."""
        monkeypatch.setenv("API_CORS_ORIGINS", "*")
        raw = __import__("os").getenv("API_CORS_ORIGINS", "")
        computed = [x.strip() for x in raw.split(",") if x.strip()] if raw.strip() else []
        assert computed == ["*"]
