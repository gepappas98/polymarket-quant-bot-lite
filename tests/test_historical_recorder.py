import json
import time

from bot.historical_recorder import HistoricalRecorder, SnapshotStore, TokenMetadata
from bot.recorder_service import RecorderService


class FakeRest:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def fetch_book(self, token_id):
        self.calls.append(token_id)
        return self.payload


def make(tmp_path, stale=45):
    store = SnapshotStore(tmp_path / "history.db")
    rest = FakeRest({"timestamp": "1700000000123", "hash": "rest-hash", "bids": [{"price": "0.40", "size": "3"}], "asks": [{"price": "0.60", "size": "4"}]})
    recorder = HistoricalRecorder([TokenMetadata("tok", "market", "condition", "Yes")], store, rest, stale_after_seconds=stale)
    return recorder, store, rest


def rows(store):
    return store.conn.execute("select * from l2_book_snapshots order by id").fetchall()


def test_initial_snapshot_and_exact_timestamp(tmp_path):
    recorder, store, _ = make(tmp_path)
    recorder.handle_message({"event_type": "book", "market": "condition", "asset_id": "tok", "timestamp": "1700000000123", "hash": "h1", "bids": [{"price": "0.44", "size": "10"}], "asks": [{"price": "0.45", "size": "8"}]})
    row = rows(store)[0]
    assert row["event_timestamp_ms"] == 1700000000123
    assert row["best_bid"] == "0.44" and row["best_ask"] == "0.45"
    assert row["source"] == "polymarket_clob" and row["data_source"] == "REAL"


def test_price_changes_partial_depth_and_delete(tmp_path):
    recorder, store, _ = make(tmp_path)
    recorder.handle_message({"event_type": "book", "asset_id": "tok", "timestamp": "1000", "hash": "s", "bids": [{"price": "0.40", "size": "3"}, {"price": "0.39", "size": "2"}], "asks": [{"price": "0.60", "size": "4"}]})
    recorder.handle_message({"event_type": "price_change", "timestamp": "2000", "price_changes": [{"asset_id": "tok", "price": "0.40", "size": "5", "side": "BUY", "hash": "c1"}]})
    recorder.handle_message({"event_type": "price_change", "timestamp": "3000", "price_changes": [{"asset_id": "tok", "price": "0.60", "size": "0", "side": "SELL", "hash": "c2"}]})
    assert json.loads(rows(store)[1]["bids_json"])[0] == {"price": "0.40", "size": "5"}
    assert json.loads(rows(store)[2]["asks_json"]) == []
    assert recorder.metrics.events_persisted == 3


def test_reconnect_service_subscribes_and_reconciles(tmp_path):
    recorder, store, rest = make(tmp_path)
    service = RecorderService(recorder)
    assert json.loads(service.subscription())["assets_ids"] == ["tok"]
    recorder.reconcile("tok")
    assert rest.calls == ["tok"]
    assert rows(store)[0]["event_type"] == "rest_reconciliation"


def test_stale_book_is_detected(tmp_path):
    recorder, store, _ = make(tmp_path, stale=0.001)
    recorder.handle_message({"event_type": "book", "asset_id": "tok", "hash": "s", "bids": [], "asks": []})
    time.sleep(0.01)
    assert recorder.mark_stale() == ["tok"]
    assert recorder.metrics.stale_periods == 1


def test_duplicate_event_is_dropped(tmp_path):
    recorder, store, _ = make(tmp_path)
    event = {"event_type": "book", "asset_id": "tok", "hash": "same", "bids": [], "asks": []}
    recorder.handle_message(event)
    recorder.handle_message(event)
    assert len(rows(store)) == 1
    assert recorder.metrics.dropped_events == 1


def test_malformed_event_is_dropped_without_inventing_values(tmp_path):
    recorder, store, _ = make(tmp_path)
    recorder.handle_message('{"event_type":"price_change","price_changes":[{"asset_id":"tok","price":"not-a-price","size":"4","side":"BUY"}]}')
    recorder.handle_message("not-json")
    assert rows(store) == []
    assert recorder.metrics.dropped_events == 2


def test_list_framed_initial_dump_is_processed(tmp_path):
    recorder, store, _ = make(tmp_path)
    recorder.handle_message(json.dumps([{"event_type": "book", "asset_id": "tok", "timestamp": "1700000004000", "hash": "list-book", "bids": [{"price": "0.41", "size": "1"}], "asks": []}]))
    assert len(rows(store)) == 1
    assert rows(store)[0]["event_timestamp_ms"] == 1700000004000
