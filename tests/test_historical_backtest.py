import pytest

from bot.backtest import run_real_backtest
from bot.historical_data import HistoricalDataUnavailable, PolymarketHistoricalL2DataSource
from bot.historical_recorder import HistoricalRecorder, SnapshotStore, TokenMetadata


def write_history(tmp_path):
    store = SnapshotStore(tmp_path / "history.db")
    recorder = HistoricalRecorder([TokenMetadata("tok", "market", "condition", "Yes")], store, object())
    recorder.handle_message({"event_type": "book", "asset_id": "tok", "timestamp": "1700000002000", "hash": "h2", "bids": [{"price": "0.40", "size": "10"}], "asks": [{"price": "0.50", "size": "10"}]})
    recorder.handle_message({"event_type": "price_change", "asset_id": "tok", "timestamp": "1700000001000", "price_changes": [{"asset_id": "tok", "price": "0.49", "size": "5", "side": "SELL", "hash": "h1"}]})
    store.close()
    return tmp_path / "history.db"


def test_real_source_fails_closed_when_database_is_missing(tmp_path):
    source = PolymarketHistoricalL2DataSource(tmp_path / "missing.db")
    with pytest.raises(HistoricalDataUnavailable, match="synthetic/demo fallback is disabled"):
        source.require_snapshots()


def test_real_source_replays_event_time_chronologically(tmp_path):
    source = PolymarketHistoricalL2DataSource(write_history(tmp_path))
    rows = source.require_snapshots(market_id="market", token_id="tok")
    assert [row.timestamp_ms for row in rows] == [1700000001000, 1700000002000]
    assert rows[0].asks[0] == {"price": "0.49", "size": "5"}
    assert source.coverage(market_id="market")["data_source"] == "REAL_HISTORICAL_POLYMARKET"


def test_real_backtest_result_declares_real_data_and_paper_execution(tmp_path, monkeypatch):
    source = PolymarketHistoricalL2DataSource(write_history(tmp_path))
    class EmptyRegistry:
        def evaluate_all(self, state):
            return []
    monkeypatch.setattr("bot.backtest.load_all", lambda strategy: EmptyRegistry())
    result = run_real_backtest(source, market_id="market", token_id="tok")
    assert result.data_source == "REAL_HISTORICAL_POLYMARKET"
    assert result.execution_mode == "PAPER_SIMULATION"
    assert result.data_coverage["rows"] == 2
    assert "Historical market data is real; executions are simulated." in result.summary()
