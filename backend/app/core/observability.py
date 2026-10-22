"""Structured logging and correlation context shared by API and workers."""
from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

_correlation_id = contextvars.ContextVar("correlation_id", default=None)
_job_id = contextvars.ContextVar("job_id", default=None)
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def normalize_correlation_id(value: str | None) -> str | None:
    candidate = str(value or "").strip()
    return candidate if _SAFE_ID.fullmatch(candidate) else None


def correlation_id() -> str | None:
    return _correlation_id.get()


def bind_correlation_id(value: str | None):
    return _correlation_id.set(normalize_correlation_id(value))


def reset_correlation_id(token: contextvars.Token) -> None:
    _correlation_id.reset(token)


def bind_job_id(value: str | None):
    return _job_id.set(normalize_correlation_id(value))


def reset_job_id(token: contextvars.Token) -> None:
    _job_id.reset(token)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        current_correlation_id = correlation_id()
        current_job_id = _job_id.get()
        if current_correlation_id:
            payload["correlation_id"] = current_correlation_id
        if current_job_id:
            payload["job_id"] = current_job_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = _json_value(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    """Configure one process-wide handler; safe to call more than once."""
    root = logging.getLogger()
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)
    if getattr(root, "_mataqorlab_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root._mataqorlab_configured = True  # type: ignore[attr-defined]

