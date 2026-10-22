"""Structured logging for chat analytics pipeline (observability)."""
import json
import logging
from typing import Any

logger = logging.getLogger("chat_pipeline")


def log_pipeline_event(event: str, **fields: Any) -> None:
    payload = {k: v for k, v in fields.items() if v is not None}
    logger.info("%s %s", event, json.dumps(payload, default=str, ensure_ascii=False))
