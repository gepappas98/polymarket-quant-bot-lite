"""
Structured logging — closes the ROADMAP's "Structured logging (JSON)" item.

Set LOG_FORMAT=json to emit one JSON object per log line (easy to ship to
Loki/CloudWatch/Datadog etc.). Default stays human-readable text so local
`python -m bot.main` runs look the same as before.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Allow callers to attach structured fields: log.info("msg", extra={"slug": "..."})
        for key, value in record.__dict__.items():
            if key in (
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "taskName",
            ):
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str, fmt: str) -> None:
    """Call once at startup instead of logging.basicConfig()."""
    handler = logging.StreamHandler()
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
        ))
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)
