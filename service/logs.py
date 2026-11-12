"""JSON-lines logging. One JSON object per line, timestamps in UTC with 'Z'."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from itertools import count
from pathlib import Path

_ids = count(1)
_lock = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _next_line_id() -> str:
    with _lock:
        return f"L{next(_ids)}"


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, version: str):
        super().__init__()
        self.service = service
        self.version = version

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "id": _next_line_id(),
            "ts": utc_now(),
            "level": record.levelname,
            "service": self.service,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            entry.update(extra)
        if record.exc_info:
            exc_type, exc, _ = record.exc_info
            entry["exc_type"] = exc_type.__name__ if exc_type else None
            entry["exc"] = str(exc)
        return json.dumps(entry, default=str)


def setup(log_file: Path, service: str, version: str) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("checkout")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(JsonFormatter(service, version))
    logger.addHandler(handler)
    return logger


def log(logger: logging.Logger, level: int, msg: str, exc_info=None, **fields) -> None:
    logger.log(level, msg, exc_info=exc_info, extra={"fields": fields})
