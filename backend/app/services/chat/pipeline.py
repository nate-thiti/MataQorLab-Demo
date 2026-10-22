"""Pipeline helpers — status events, engine metadata, insight injection."""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.pipeline_log import log_pipeline_event
from app.services.dataset_engine import DatasetHandle

_CONNECTION_MENTION_RE = re.compile(r"^@[\w.\-]+(?:-[\w.]+)?\s+", re.UNICODE)


def strip_connection_mention(text: str) -> str:
    """Remove leading @connection or @connection-table prefix from chat text."""
    return _CONNECTION_MENTION_RE.sub("", (text or "").strip()).strip()


def is_ingest_error_message(content: Optional[str]) -> bool:
    """True when ingest returned a failure string instead of dataset metadata."""
    if not content:
        return False
    text = content.strip()
    if text.startswith("Error:"):
        return True
    if text.startswith("Warning:") and "no tables" in text.lower():
        return True
    return False


def question_hint(question: str, max_len: int = 80) -> str:
    q = strip_connection_mention(question)
    if len(q) <= max_len:
        return q
    return q[: max_len - 1] + "…"


async def emit_status(
    on_status: Optional[Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]]],
    stage: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    payload = detail or {}
    if stage in ("analytics", "merging", "agent_step", "web_search", "web_search_done", "analyzing_done", "agent_plan"):
        log_pipeline_event("pipeline_stage", stage=stage, **payload)
    if on_status is not None:
        await on_status(stage, payload)


def engine_detail(handle: DatasetHandle) -> Dict[str, Any]:
    return {
        "engine": "duckdb" if handle.is_large else "pandas",
        "rows": handle.row_count(),
        "cols": len(handle.column_names()),
    }


def should_cache_analytics(
    file_attachment_name: Optional[str], connection_id: Optional[str]
) -> bool:
    return bool(file_attachment_name or connection_id)


def inject_insight_into_file_content(file_content: str, insight: str) -> str:
    if not insight:
        return file_content
    return file_content + insight
