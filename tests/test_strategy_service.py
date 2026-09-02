from app.utils.categories import category_for_slug
from app.services.strategy_service import ActiveStrategies, should_ignore_market


def test_categories():
    assert category_for_slug("btc-up-or-down-5m") == "crypto"
    assert category_for_slug("presidential-election") == "politics"
    assert category_for_slug("nba-finals") == "sports"
    assert category_for_slug("weather-tomorrow") == "other"


def test_strategy_flags():
    assert should_ignore_market("btc-up-or-down", None, ActiveStrategies()) is False
    assert should_ignore_market("btc-up-or-down", None, ActiveStrategies(politics_only=True))
    assert should_ignore_market("nba-match", None, ActiveStrategies(sports_fade=True))
    assert should_ignore_market("president-vote", None, ActiveStrategies(crypto_focus=True))
