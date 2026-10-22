"""Map OpenAI SDK / OpenRouter errors to stream-friendly payloads."""
from __future__ import annotations

import logging
from typing import Any, Dict

import openai

logger = logging.getLogger(__name__)


def _openrouter_message(exc: openai.APIStatusError) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    message = error.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return str(exc)


def stream_error_payload(exc: Exception) -> Dict[str, Any]:
    """Build SSE error event dict with a useful code + detail for the frontend."""
    if isinstance(exc, openai.RateLimitError):
        return {"type": "error", "code": "rate_limit", "detail": "rate_limited"}

    if isinstance(exc, openai.APIStatusError):
        detail = _openrouter_message(exc)
        status = exc.status_code or 502
        logger.warning("LLM API error status=%s detail=%s", status, detail)

        if status == 402:
            return {"type": "error", "code": "llm_credits", "detail": detail}
        if status == 404:
            return {"type": "error", "code": "provider_unavailable", "detail": detail}
        if status == 429:
            return {"type": "error", "code": "rate_limit", "detail": detail}
        if status in (502, 503, 504):
            return {"type": "error", "code": "server_error", "detail": detail}
        return {"type": "error", "code": "server_error", "detail": detail}

    logger.exception("Unexpected LLM stream error")
    return {"type": "error", "code": "server_error", "detail": "error"}
