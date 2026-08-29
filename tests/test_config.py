from bot.config import Config, _parse_asset_map


class TestParseAssetMap:
    def test_empty_string_returns_empty_dict(self):
        assert _parse_asset_map("") == {}

    def test_parses_multiple_assets(self):
        result = _parse_asset_map("BTC:150,ETH:100,SOL:50,XRP:50")
        assert result == {"BTC": 150.0, "ETH": 100.0, "SOL": 50.0, "XRP": 50.0}

    def test_uppercases_asset_names(self):
        result = _parse_asset_map("btc:150")
        assert result == {"BTC": 150.0}

    def test_ignores_malformed_entries(self):
        result = _parse_asset_map("BTC:150, garbage, ETH:not-a-number, SOL:50")
        assert result == {"BTC": 150.0, "SOL": 50.0}

    def test_tolerates_surrounding_whitespace(self):
        result = _parse_asset_map(" BTC : 150 , ETH : 100 ")
        assert result == {"BTC": 150.0, "ETH": 100.0}


class TestExposureCapFor:
    def test_falls_back_to_global_cap_when_no_override(self):
        cfg = Config(max_market_exposure_usd=150.0, max_market_exposure_by_asset={})
        assert cfg.exposure_cap_for("BTC") == 150.0

    def test_uses_per_asset_override_when_present(self):
        cfg = Config(
            max_market_exposure_usd=150.0,
            max_market_exposure_by_asset={"SOL": 50.0},
        )
        assert cfg.exposure_cap_for("SOL") == 50.0

    def test_lookup_is_case_insensitive(self):
        cfg = Config(
            max_market_exposure_usd=150.0,
            max_market_exposure_by_asset={"SOL": 50.0},
        )
        assert cfg.exposure_cap_for("sol") == 50.0

    def test_unlisted_asset_falls_back_even_with_other_overrides_present(self):
        cfg = Config(
            max_market_exposure_usd=150.0,
            max_market_exposure_by_asset={"SOL": 50.0, "XRP": 50.0},
        )
        assert cfg.exposure_cap_for("BTC") == 150.0
