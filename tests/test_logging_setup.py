import json
import logging

from bot.logging_setup import JsonFormatter


def _make_record(msg="hello", level=logging.INFO, **extra):
    record = logging.LogRecord(
        name="test.logger", level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


class TestJsonFormatter:
    def test_output_is_valid_json(self):
        record = _make_record("hello world")
        formatted = JsonFormatter().format(record)
        parsed = json.loads(formatted)  # must not raise
        assert parsed["message"] == "hello world"

    def test_includes_level_and_logger_name(self):
        record = _make_record("test", level=logging.WARNING)
        parsed = json.loads(JsonFormatter().format(record))
        assert parsed["level"] == "WARNING"
        assert parsed["logger"] == "test.logger"

    def test_includes_a_timestamp(self):
        record = _make_record("test")
        parsed = json.loads(JsonFormatter().format(record))
        assert "ts" in parsed
        assert isinstance(parsed["ts"], (int, float))

    def test_passes_through_extra_fields(self):
        record = _make_record("gate blocked", slug="btc-updown-5m-1", allowed=False)
        parsed = json.loads(JsonFormatter().format(record))
        assert parsed["slug"] == "btc-updown-5m-1"
        assert parsed["allowed"] is False

    def test_does_not_leak_internal_logrecord_attributes(self):
        record = _make_record("test")
        parsed = json.loads(JsonFormatter().format(record))
        # These are LogRecord internals, not meant to appear in the payload.
        assert "pathname" not in parsed
        assert "lineno" not in parsed
        assert "msg" not in parsed
