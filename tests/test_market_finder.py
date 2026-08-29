import json
from unittest.mock import MagicMock, patch

import pytest

from bot.market_finder import (
    current_window_start,
    fetch_market_by_slug,
    fetch_resolution,
    parse_event,
    slug_candidates,
)


class TestWindowMath:
    def test_current_window_start_is_aligned_to_window_size(self):
        start = current_window_start(5)
        assert start % (5 * 60) == 0

    def test_different_window_sizes_align_independently(self):
        s5 = current_window_start(5)
        s15 = current_window_start(15)
        assert s5 % 300 == 0
        assert s15 % 900 == 0


class TestSlugCandidates:
    def test_returns_multiple_pattern_variants(self):
        candidates = slug_candidates("BTC", 5, 1735689600)
        assert len(candidates) >= 3

    def test_lowercases_the_asset(self):
        candidates = slug_candidates("BTC", 5, 1735689600)
        assert all("btc" in c for c in candidates)
        assert all("BTC" not in c for c in candidates)

    def test_includes_the_window_timestamp(self):
        ts = 1735689600
        candidates = slug_candidates("eth", 15, ts)
        assert all(str(ts) in c for c in candidates)


class TestParseEvent:
    def _base_market(self, **overrides):
        market = {
            "clobTokenIds": json.dumps(["111", "222"]),
            "outcomes": json.dumps(["Up", "Down"]),
            "conditionId": "0xcondition",
            "question": "Will BTC be up?",
            "endDate": "2026-01-01T00:05:00Z",
            "active": True,
            "closed": False,
            "acceptingOrders": True,
        }
        market.update(overrides)
        return market

    def test_parses_up_down_token_ids_in_order(self):
        event = {"slug": "btc-updown-5m-1", "markets": [self._base_market()]}
        result = parse_event(event)
        assert result["up_token_id"] == "111"
        assert result["down_token_id"] == "222"

    def test_handles_reversed_outcome_order(self):
        market = self._base_market(
            clobTokenIds=json.dumps(["111", "222"]),
            outcomes=json.dumps(["Down", "Up"]),
        )
        event = {"slug": "btc-updown-5m-1", "markets": [market]}
        result = parse_event(event)
        # Outcomes list says index 0 = Down, index 1 = Up — tokens should follow.
        assert result["up_token_id"] == "222"
        assert result["down_token_id"] == "111"

    def test_returns_none_when_no_markets(self):
        assert parse_event({"slug": "x", "markets": []}) is None

    def test_returns_none_when_fewer_than_two_token_ids(self):
        market = self._base_market(clobTokenIds=json.dumps(["111"]))
        event = {"slug": "x", "markets": [market]}
        assert parse_event(event) is None

    def test_returns_none_on_malformed_token_ids_json(self):
        market = self._base_market(clobTokenIds="not valid json")
        event = {"slug": "x", "markets": [market]}
        assert parse_event(event) is None

    def test_active_is_false_when_market_closed(self):
        market = self._base_market(closed=True)
        event = {"slug": "x", "markets": [market]}
        result = parse_event(event)
        assert result["active"] is False

    def test_accepts_list_form_outcomes_not_just_json_string(self):
        market = self._base_market(outcomes=["Up", "Down"])  # already a list
        event = {"slug": "x", "markets": [market]}
        result = parse_event(event)
        assert result["up_token_id"] == "111"


class TestFetchMarketBySlug:
    @patch("bot.market_finder.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        mock_get.side_effect = Exception("network down")
        assert fetch_market_by_slug("btc-updown-5m-1") is None

    @patch("bot.market_finder.requests.get")
    def test_returns_none_when_no_events_found(self, mock_get):
        resp = MagicMock()
        resp.json.return_value = []
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp
        assert fetch_market_by_slug("btc-updown-5m-1") is None

    @patch("bot.market_finder.requests.get")
    def test_parses_first_matching_event(self, mock_get):
        market = {
            "clobTokenIds": json.dumps(["111", "222"]),
            "outcomes": json.dumps(["Up", "Down"]),
            "active": True,
            "closed": False,
            "acceptingOrders": True,
        }
        resp = MagicMock()
        resp.json.return_value = [{"slug": "btc-updown-5m-1", "markets": [market]}]
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp
        result = fetch_market_by_slug("btc-updown-5m-1")
        assert result["slug"] == "btc-updown-5m-1"


class TestFetchResolution:
    @patch("bot.market_finder.requests.get")
    def test_reports_unresolved_when_market_still_open(self, mock_get):
        resp = MagicMock()
        resp.json.return_value = [{"markets": [{"closed": False}]}]
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp
        result = fetch_resolution("btc-updown-5m-1")
        assert result == {"resolved": False, "winner": None}

    @patch("bot.market_finder.requests.get")
    def test_declares_up_winner_from_outcome_prices(self, mock_get):
        market = {
            "closed": True,
            "outcomes": json.dumps(["Up", "Down"]),
            "outcomePrices": json.dumps(["1", "0"]),
        }
        resp = MagicMock()
        resp.json.return_value = [{"markets": [market]}]
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp
        result = fetch_resolution("btc-updown-5m-1")
        assert result == {"resolved": True, "winner": "UP"}

    @patch("bot.market_finder.requests.get")
    def test_declares_down_winner_from_outcome_prices(self, mock_get):
        market = {
            "closed": True,
            "outcomes": json.dumps(["Up", "Down"]),
            "outcomePrices": json.dumps(["0", "1"]),
        }
        resp = MagicMock()
        resp.json.return_value = [{"markets": [market]}]
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp
        result = fetch_resolution("btc-updown-5m-1")
        assert result == {"resolved": True, "winner": "DOWN"}

    @patch("bot.market_finder.requests.get")
    def test_resolved_but_no_prices_yet_returns_unknown_winner(self, mock_get):
        market = {"closed": True, "outcomes": json.dumps(["Up", "Down"]), "outcomePrices": None}
        resp = MagicMock()
        resp.json.return_value = [{"markets": [market]}]
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp
        result = fetch_resolution("btc-updown-5m-1")
        assert result == {"resolved": True, "winner": None}

    @patch("bot.market_finder.requests.get")
    def test_returns_none_on_fetch_failure_not_false(self, mock_get):
        """A failed fetch must be distinguishable from 'confirmed not resolved'."""
        mock_get.side_effect = Exception("timeout")
        result = fetch_resolution("btc-updown-5m-1")
        assert result is None
