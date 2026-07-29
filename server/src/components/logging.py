from __future__ import annotations

import json
import logging
import sys

from src.components.config import get_settings

# Structured logging: JSON lines in production (easy to ship/parse), plain text in dev.
_EXTRA_KEYS = ("method", "path", "status", "duration_ms", "account", "org")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k in _EXTRA_KEYS:
            if (v := getattr(record, k, None)) is not None:
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Install a single stdout handler on the root logger. JSON in prod, plain in dev.
    Idempotent — safe to call more than once."""
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_dev:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())
    # Tame the noisiest third parties unless we're explicitly debugging.
    for noisy in ("neo4j", "httpx", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))
