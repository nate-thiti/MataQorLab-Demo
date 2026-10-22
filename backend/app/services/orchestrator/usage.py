"""Orchestrator LLM usage tracking — reuses profile token quota accounting."""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Mapping, Optional

from app.services.quota_service import record_token_usage
from app.services.workflow.events import emit_workflow_event

logger = logging.getLogger("mataqorlab.orchestrator.usage")

USAGE_TYPE_WORKFLOW_ORCHESTRATOR = "workflow_orchestrator"

_settled_lock = threading.Lock()
_settled_keys: set[str] = set()


def extract_usage_from_response(response: Any) -> Dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, Mapping):
        usage = response.get("usage")
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt = int(getattr(usage, "prompt_tokens", None) or (usage.get("prompt_tokens") if isinstance(usage, Mapping) else 0) or 0)
    completion = int(
        getattr(usage, "completion_tokens", None)
        or (usage.get("completion_tokens") if isinstance(usage, Mapping) else 0)
        or 0
    )
    total = int(
        getattr(usage, "total_tokens", None)
        or (usage.get("total_tokens") if isinstance(usage, Mapping) else 0)
        or (prompt + completion)
    )
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def summarize_calls(calls: List[Mapping[str, Any]]) -> Dict[str, Any]:
    prompt = sum(int(c.get("prompt_tokens") or 0) for c in calls)
    completion = sum(int(c.get("completion_tokens") or 0) for c in calls)
    total = sum(int(c.get("total_tokens") or 0) for c in calls)
    return {
        "usage_type": USAGE_TYPE_WORKFLOW_ORCHESTRATOR,
        "llm_calls": len(calls),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "calls": list(calls),
    }


def was_usage_settled(settlement_key: str) -> bool:
    if not settlement_key:
        return False
    with _settled_lock:
        return settlement_key in _settled_keys


def mark_usage_settled(settlement_key: str) -> bool:
    """Return True if this is the first settle for the key (idempotent)."""
    if not settlement_key:
        return True
    with _settled_lock:
        if settlement_key in _settled_keys:
            return False
        _settled_keys.add(settlement_key)
        # Bound memory for long-running workers.
        if len(_settled_keys) > 5000:
            _settled_keys.clear()
            _settled_keys.add(settlement_key)
        return True


def reset_usage_settlements_for_tests() -> None:
    with _settled_lock:
        _settled_keys.clear()


async def settle_orchestrator_usage(
    *,
    user_id: str,
    session_id: Optional[str],
    calls: List[Mapping[str, Any]],
    settlement_key: Optional[str] = None,
    decision_type: Optional[str] = None,
    prompt_version: Optional[str] = None,
    client: Any = None,
) -> Dict[str, Any]:
    """Persist quota via existing increment_profile_tokens; attach session audit."""
    summary = summarize_calls(calls)
    key = str(settlement_key or "").strip()
    if key and not mark_usage_settled(key):
        logger.info(
            "orchestrator_usage_idempotent_skip",
            extra={
                "session_id": session_id,
                "settlement_key": key,
                "usage_type": USAGE_TYPE_WORKFLOW_ORCHESTRATOR,
            },
        )
        return {**summary, "settled": False, "idempotent_skip": True}

    total = int(summary["total_tokens"] or 0)
    if total > 0:
        await record_token_usage(
            user_id,
            total,
            usage_type=USAGE_TYPE_WORKFLOW_ORCHESTRATOR,
            metadata={
                "session_id": session_id,
                "llm_calls": summary["llm_calls"],
                "decision_type": decision_type,
                "prompt_version": prompt_version,
                "settlement_key": key or None,
            },
        )

    for call in calls:
        emit_workflow_event(
            "llm_call_completed",
            session_id=str(session_id or "unknown"),
            decision_type=decision_type,
            reason_code=str(call.get("kind") or "decision"),
            metadata={
                "usage_type": USAGE_TYPE_WORKFLOW_ORCHESTRATOR,
                "model": call.get("model"),
                "prompt_tokens": call.get("prompt_tokens"),
                "completion_tokens": call.get("completion_tokens"),
                "total_tokens": call.get("total_tokens"),
                "fallback": bool(call.get("fallback")),
                "repair_attempt": bool(call.get("repair_attempt")),
                "prompt_version": prompt_version,
            },
        )

    if client is not None and session_id:
        try:
            _accumulate_session_usage(client, session_id, user_id, summary)
        except Exception as exc:
            # Usage ledger failure must not corrupt workflow state.
            logger.warning(
                "orchestrator_session_usage_persist_failed",
                extra={"session_id": session_id, "error": str(exc)[:200]},
            )

    return {**summary, "settled": True, "idempotent_skip": False}


def _accumulate_session_usage(
    client: Any,
    session_id: str,
    user_id: str,
    summary: Mapping[str, Any],
) -> None:
    row = (
        client.table("data_setup_sessions")
        .select("processing_progress")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    current = {}
    if row.data:
        current = dict((row.data[0] or {}).get("processing_progress") or {})
    prior = dict(current.get("orchestrator_usage") or {})
    merged = {
        "usage_type": USAGE_TYPE_WORKFLOW_ORCHESTRATOR,
        "llm_calls": int(prior.get("llm_calls") or 0) + int(summary.get("llm_calls") or 0),
        "prompt_tokens": int(prior.get("prompt_tokens") or 0)
        + int(summary.get("prompt_tokens") or 0),
        "completion_tokens": int(prior.get("completion_tokens") or 0)
        + int(summary.get("completion_tokens") or 0),
        "total_tokens": int(prior.get("total_tokens") or 0)
        + int(summary.get("total_tokens") or 0),
    }
    # Keep a bounded recent call list for ops (not a full billing ledger).
    recent = list(prior.get("recent_calls") or [])
    recent.extend(list(summary.get("calls") or []))
    merged["recent_calls"] = recent[-20:]
    current["orchestrator_usage"] = merged
    client.table("data_setup_sessions").update({
        "processing_progress": current,
    }).eq("id", session_id).eq("user_id", user_id).execute()
