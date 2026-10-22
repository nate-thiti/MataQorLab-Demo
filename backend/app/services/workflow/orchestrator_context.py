"""AI-safe workflow context builder (Phase 4.5) — no LLM calls.

Produces a compact structure for a future orchestrator. Excludes credentials,
signed URLs, tracebacks, dataset samples, and service-role metadata.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional, Set

from app.services.workflow.models import WorkflowDecision, WorkflowPlan

# Field / substring deny-list for orchestrator payloads.
_SENSITIVE_KEY_FRAGMENTS: Set[str] = {
    "password",
    "token",
    "secret",
    "service_role",
    "signed_url",
    "traceback",
    "raw_dataframe",
    "api_key",
    "authorization",
    "bearer",
    "connection_string",
    "private_key",
}

_MAX_CONTEXT_CHARS = 8_000


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key or "").lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                continue
            cleaned = _sanitize(item, depth=depth + 1)
            if cleaned is not None:
                out[str(key)] = cleaned
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth=depth + 1) for item in value[:40]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > 500:
            return value[:500] + "…"
        return value
    return str(value)[:200]


def build_orchestrator_workflow_context(
    plan: WorkflowPlan | Mapping[str, Any],
) -> Dict[str, Any]:
    """Compact LLM-facing workflow context derived from WorkflowPlan."""
    if isinstance(plan, WorkflowPlan):
        data = plan.model_dump()
    else:
        data = dict(plan)

    steps_compact: Dict[str, str] = {}
    for item in data.get("steps") or []:
        if isinstance(item, Mapping):
            step_type = str(item.get("step_type") or item.get("step") or "")
            status = str(item.get("status") or "pending")
            if step_type:
                steps_compact[step_type] = status

    next_action = data.get("next_action")
    if isinstance(next_action, WorkflowDecision):
        next_action = next_action.model_dump()
    next_safe = None
    if isinstance(next_action, Mapping):
        next_safe = {
            "action": next_action.get("action"),
            "step_type": next_action.get("step_type"),
            "reason": next_action.get("reason"),
            "error_code": next_action.get("error_code"),
        }
        meta = next_action.get("metadata") or {}
        if isinstance(meta, Mapping):
            # Keep only small non-sensitive metadata keys.
            slim = {
                k: v
                for k, v in meta.items()
                if k in {"profile", "reason_code", "missing", "confirmation_fingerprint"}
                and not _is_sensitive_key(str(k))
            }
            if slim:
                next_safe["metadata"] = _sanitize(slim)

    awaiting = data.get("awaiting_user")
    awaiting_safe = _sanitize(awaiting) if awaiting else None

    context = {
        "session_id": data.get("session_id"),
        "status": data.get("status"),
        "current_step": data.get("current_step"),
        "next_action": next_safe,
        "steps": steps_compact,
        "blockers": _sanitize(data.get("blockers") or []),
        "awaiting_user": awaiting_safe,
        "last_failed_step": data.get("last_failed_step"),
    }
    serialized = json.dumps(context, ensure_ascii=False, default=str)
    if len(serialized) > _MAX_CONTEXT_CHARS:
        context["truncated"] = True
        context["blockers"] = (context.get("blockers") or [])[:5]
        if context.get("awaiting_user") and isinstance(context["awaiting_user"], dict):
            context["awaiting_user"] = {
                k: context["awaiting_user"].get(k)
                for k in ("step_type", "reason", "reason_code")
                if k in context["awaiting_user"]
            }
    return context
