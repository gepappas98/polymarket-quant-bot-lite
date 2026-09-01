import pytest
from app.services.sizing_service import calculate_kelly_size
from bot.config import cfg


def test_kelly_math_and_caps(monkeypatch):
    result = calculate_kelly_size(.6, 2, "crypto", 100, 1, 1)
    assert result.raw_kelly == pytest.approx(.2)
    assert result.f_value == pytest.approx(20)
    scaled = calculate_kelly_size(.6, 2, "crypto", 100, .5, 1)
    assert scaled.f_value == pytest.approx(10)
    capped = calculate_kelly_size(.6, 2, "crypto", 100, 1, .05)
    assert capped.capped_by == "max_pct"
    assert calculate_kelly_size(.5, 1, "crypto", 100, 1, .5).suggested_amount == 0
    monkeypatch.setattr(cfg, "max_order_usd", 5)
    assert calculate_kelly_size(.9, 2, "crypto", 1000, 1, 1).capped_by == "max_order_usd"


def test_variance_cap(monkeypatch):
    monkeypatch.setattr(cfg, "max_order_usd", 1000)
    result = calculate_kelly_size(.8, 2, "crypto", 100, 1, 1, variance=100)
    assert result.capped_by == "variance"
    assert result.f_value < 60
