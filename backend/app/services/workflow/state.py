"""Workflow step persistence for data_setup_sessions (Phase 3 / 4.5).

This module records what happened. Transition authorization lives in the
Workflow Engine. Production begin_step requires the atomic RPC.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from app.core.json_safety import to_json_safe
from app.core.supabase import get_supabase_client
from app.services.tools.types import ToolResult
from app.services.workflow.capability import (
    WorkflowPersistenceError,
    allow_begin_step_fallback,
)
from app.services.workflow.models import (
    ERROR_CODES,
    REUSABLE_STATUSES,
    SETUP_SEQUENCE,
    WorkflowStepStatus,
    WorkflowStepType,
)

logger = logging.getLogger("mataqorlab.workflow.state")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client(client: Any | None = None) -> Any:
    return client or get_supabase_client()


def _safe_error_message(exc: BaseException | str, *, limit: int = 500) -> str:
    text = str(exc or "").strip().replace("\n", " ")
    if not text:
        return "Step failed"
    # Avoid leaking stack frames / connection strings into user-readable columns.
    for marker in ("Traceback", "password=", "secret=", "Bearer ", "api_key"):
        if marker.lower() in text.lower():
            return "Step failed during execution"
    return text[:limit]


def tool_result_to_output(result: ToolResult) -> Dict[str, Any]:
    """Persist a compact ToolResult without dataset payloads."""
    payload = result.to_public_dict()
    return to_json_safe({
        "tool": payload.get("tool"),
        "status": payload.get("status"),
        "summary": payload.get("summary"),
        "findings": payload.get("findings") or [],
        "warnings": payload.get("warnings") or [],
        "artifacts": payload.get("artifacts") or {},
        "metadata": payload.get("metadata") or {},
        "suggested_next_actions": payload.get("suggested_next_actions") or [],
    })


def get_workflow_steps(
    session_id: str,
    *,
    client: Any | None = None,
) -> List[Dict[str, Any]]:
    response = (
        _client(client)
        .table("workflow_steps")
        .select("*")
        .eq("data_setup_session_id", session_id)
        .order("created_at")
        .execute()
    )
    return list(response.data or [])


def get_latest_step(
    session_id: str,
    step_type: str | WorkflowStepType,
    *,
    client: Any | None = None,
) -> Optional[Dict[str, Any]]:
    step = step_type.value if isinstance(step_type, WorkflowStepType) else str(step_type)
    response = (
        _client(client)
        .table("workflow_steps")
        .select("*")
        .eq("data_setup_session_id", session_id)
        .eq("step_type", step)
        .order("version", desc=True)
        .order("attempt", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def get_resume_state(
    session_id: str,
    *,
    client: Any | None = None,
) -> Dict[str, Any]:
    """Summarize latest status per step for resume decisions."""
    by_type: Dict[str, Dict[str, Any]] = {}
    for row in get_workflow_steps(session_id, client=client):
        step_type = str(row.get("step_type") or "")
        current = by_type.get(step_type)
        if current is None:
            by_type[step_type] = row
            continue
        key = (int(row.get("version") or 0), int(row.get("attempt") or 0))
        prev = (int(current.get("version") or 0), int(current.get("attempt") or 0))
        if key >= prev:
            by_type[step_type] = row

    next_step: Optional[str] = None
    last_failed: Optional[str] = None
    for step in SETUP_SEQUENCE:
        latest = by_type.get(step.value)
        if latest is None:
            next_step = next_step or step.value
            continue
        status = str(latest.get("status") or "")
        if status == WorkflowStepStatus.FAILED.value:
            last_failed = step.value
            next_step = next_step or step.value
        elif status not in REUSABLE_STATUSES:
            next_step = next_step or step.value

    return {
        "steps": by_type,
        "next_step": next_step,
        "last_failed_step": last_failed,
        "all_complete": next_step is None and bool(by_type),
    }


def update_session_summary(
    session_id: str,
    user_id: str,
    *,
    next_action: Optional[str] = None,
    last_failed_step: Optional[str] = None,
    client: Any | None = None,
) -> None:
    payload: Dict[str, Any] = {"updated_at": _now()}
    if next_action is not None:
        payload["next_action"] = next_action
    if last_failed_step is not None:
        payload["last_failed_step"] = last_failed_step
    try:
        _client(client).table("data_setup_sessions").update(payload).eq(
            "id", session_id
        ).eq("user_id", user_id).execute()
    except Exception as exc:
        # Additive columns may be missing until migration is applied.
        if not any(code in str(exc) for code in ("PGRST204", "42703")):
            raise
        logger.warning(
            "workflow_session_summary_skipped",
            extra={"error_code": "missing_summary_columns"},
        )


def begin_step(
    session_id: str,
    step_type: str | WorkflowStepType,
    *,
    input_payload: Optional[Mapping[str, Any]] = None,
    bump_version: bool = False,
    client: Any | None = None,
) -> Dict[str, Any]:
    """Atomically start or reclaim a step via RPC.

    Production fails closed when ``begin_workflow_step`` is unavailable.
    Python fallback is allowed only in explicit non-production / test mode.
    """
    step = step_type.value if isinstance(step_type, WorkflowStepType) else str(step_type)
    db = _client(client)
    safe_input = to_json_safe(dict(input_payload or {}))
    try:
        response = db.rpc(
            "begin_workflow_step",
            {
                "p_session_id": session_id,
                "p_step_type": step,
                "p_input": safe_input,
                "p_bump_version": bump_version,
            },
        ).execute()
        rows = response.data or []
        if rows:
            return rows[0]
        # RPC succeeded but returned no row (unknown session) — do not invent state
        # via race-prone fallback in production.
        if not allow_begin_step_fallback():
            raise WorkflowPersistenceError(
                "WORKFLOW_RPC_EMPTY: begin_workflow_step returned no row"
            )
    except WorkflowPersistenceError:
        raise
    except Exception as exc:
        if not allow_begin_step_fallback():
            logger.error(
                "begin_workflow_step_rpc_required",
                extra={"error_code": "WORKFLOW_RPC_UNAVAILABLE", "detail": str(exc)[:200]},
            )
            raise WorkflowPersistenceError(
                "WORKFLOW_RPC_UNAVAILABLE: begin_workflow_step is required; "
                "Python fallback is disabled in this environment"
            ) from exc
        logger.warning(
            "begin_workflow_step_rpc_fallback",
            extra={"error_code": "rpc_unavailable", "detail": str(exc)[:200]},
        )
        return _begin_step_fallback(
            session_id,
            step,
            input_payload=safe_input,
            bump_version=bump_version,
            client=db,
        )
    return _begin_step_fallback(
        session_id,
        step,
        input_payload=safe_input,
        bump_version=bump_version,
        client=db,
    )


def _begin_step_fallback(
    session_id: str,
    step_type: str,
    *,
    input_payload: Mapping[str, Any],
    bump_version: bool,
    client: Any,
) -> Dict[str, Any]:
    """Best-effort Python fallback for tests/dev only (not fully race-free)."""
    if not allow_begin_step_fallback():
        raise WorkflowPersistenceError(
            "WORKFLOW_RPC_UNAVAILABLE: begin_step fallback is disabled"
        )
    latest = get_latest_step(session_id, step_type, client=client)
    if latest and str(latest.get("status")) in REUSABLE_STATUSES and not bump_version:
        return latest
    if (
        latest
        and str(latest.get("status")) == WorkflowStepStatus.RUNNING.value
        and not bump_version
    ):
        return latest

    # Approved confirmation (ready): reclaim same row into running so the
    # confirmation fingerprint / audit metadata stay attached.
    if (
        latest
        and str(latest.get("status")) == WorkflowStepStatus.READY.value
        and not bump_version
    ):
        merged_input = dict(latest.get("input") or {})
        preserved = {
            key: merged_input[key]
            for key in ("confirmation_fingerprint", "reason_code")
            if key in merged_input
        }
        merged_input.update(dict(input_payload or {}))
        merged_input.update(preserved)
        updated = (
            client.table("workflow_steps")
            .update({
                "status": WorkflowStepStatus.RUNNING.value,
                "input": merged_input,
                "started_at": _now(),
                "updated_at": _now(),
                "requires_confirmation": False,
            })
            .eq("id", latest["id"])
            .execute()
        )
        rows = updated.data or []
        if rows:
            return rows[0]
        return {**latest, "status": WorkflowStepStatus.RUNNING.value, "input": merged_input}

    version = 1
    attempt = 1
    if latest:
        version = int(latest.get("version") or 1)
        attempt = int(latest.get("attempt") or 1)
        if bump_version:
            version += 1
            attempt = 1
        elif str(latest.get("status")) in {
            WorkflowStepStatus.FAILED.value,
            WorkflowStepStatus.STALE.value,
            WorkflowStepStatus.RUNNING.value,
            WorkflowStepStatus.AWAITING_USER.value,
        }:
            attempt += 1

    inserted = (
        client.table("workflow_steps")
        .insert({
            "data_setup_session_id": session_id,
            "step_type": step_type,
            "status": WorkflowStepStatus.RUNNING.value,
            "version": version,
            "attempt": attempt,
            "input": dict(input_payload),
            "started_at": _now(),
            "updated_at": _now(),
        })
        .execute()
    )
    rows = inserted.data or []
    if not rows:
        raise RuntimeError(f"Could not start workflow step {step_type}")
    return rows[0]


def complete_step(
    step_id: str,
    *,
    output: Mapping[str, Any] | ToolResult,
    reason: Optional[str] = None,
    client: Any | None = None,
) -> Dict[str, Any]:
    payload_output = (
        tool_result_to_output(output)
        if isinstance(output, ToolResult)
        else to_json_safe(dict(output))
    )
    response = (
        _client(client)
        .table("workflow_steps")
        .update({
            "status": WorkflowStepStatus.COMPLETED.value,
            "output": payload_output,
            "reason": (reason or None),
            "error_code": None,
            "error_message": None,
            "completed_at": _now(),
            "updated_at": _now(),
        })
        .eq("id", step_id)
        .execute()
    )
    return (response.data or [{}])[0]


def skip_step(
    step_id: str,
    *,
    reason: str,
    output: Optional[Mapping[str, Any] | ToolResult] = None,
    client: Any | None = None,
) -> Dict[str, Any]:
    payload_output: Dict[str, Any] = {}
    if isinstance(output, ToolResult):
        payload_output = tool_result_to_output(output)
    elif output:
        payload_output = to_json_safe(dict(output))
    response = (
        _client(client)
        .table("workflow_steps")
        .update({
            "status": WorkflowStepStatus.SKIPPED.value,
            "output": payload_output,
            "reason": reason[:2000],
            "completed_at": _now(),
            "updated_at": _now(),
        })
        .eq("id", step_id)
        .execute()
    )
    return (response.data or [{}])[0]


def fail_step(
    step_id: str,
    *,
    error: BaseException | str,
    error_code: Optional[str] = None,
    step_type: Optional[str | WorkflowStepType] = None,
    client: Any | None = None,
) -> Dict[str, Any]:
    code = error_code
    if not code and step_type is not None:
        key = step_type if isinstance(step_type, WorkflowStepType) else WorkflowStepType(str(step_type))
        code = ERROR_CODES.get(key, "STEP_EXECUTION_FAILED")
    response = (
        _client(client)
        .table("workflow_steps")
        .update({
            "status": WorkflowStepStatus.FAILED.value,
            "error_code": (code or "STEP_EXECUTION_FAILED")[:100],
            "error_message": _safe_error_message(error),
            "completed_at": _now(),
            "updated_at": _now(),
        })
        .eq("id", step_id)
        .execute()
    )
    return (response.data or [{}])[0]


def mark_step_awaiting_user(
    step_id: str,
    *,
    reason: str,
    output: Optional[Mapping[str, Any] | ToolResult] = None,
    client: Any | None = None,
) -> Dict[str, Any]:
    from app.services.workflow.transitions import assert_transition

    payload_output: Dict[str, Any] = {}
    if isinstance(output, ToolResult):
        payload_output = tool_result_to_output(output)
    elif output:
        payload_output = to_json_safe(dict(output))
    latest = (
        _client(client)
        .table("workflow_steps")
        .select("status")
        .eq("id", step_id)
        .limit(1)
        .execute()
    )
    current = ((latest.data or [{}])[0]).get("status")
    assert_transition(current, WorkflowStepStatus.AWAITING_USER.value)
    response = (
        _client(client)
        .table("workflow_steps")
        .update({
            "status": WorkflowStepStatus.AWAITING_USER.value,
            "requires_confirmation": True,
            "reason": reason[:2000],
            "output": payload_output,
            "updated_at": _now(),
        })
        .eq("id", step_id)
        .execute()
    )
    return (response.data or [{}])[0]


def mark_step_stale(
    step_id: str,
    *,
    reason: str,
    client: Any | None = None,
) -> Dict[str, Any]:
    from app.services.workflow.transitions import assert_transition

    latest = (
        _client(client)
        .table("workflow_steps")
        .select("status")
        .eq("id", step_id)
        .limit(1)
        .execute()
    )
    current = ((latest.data or [{}])[0]).get("status")
    assert_transition(current, WorkflowStepStatus.STALE.value)
    response = (
        _client(client)
        .table("workflow_steps")
        .update({
            "status": WorkflowStepStatus.STALE.value,
            "reason": reason[:2000],
            "updated_at": _now(),
        })
        .eq("id", step_id)
        .execute()
    )
    return (response.data or [{}])[0]


def mark_step_superseded(
    step_id: str,
    *,
    reason: str,
    client: Any | None = None,
) -> Dict[str, Any]:
    from app.services.workflow.transitions import assert_transition

    latest = (
        _client(client)
        .table("workflow_steps")
        .select("status")
        .eq("id", step_id)
        .limit(1)
        .execute()
    )
    current = ((latest.data or [{}])[0]).get("status")
    assert_transition(current, WorkflowStepStatus.SUPERSEDED.value)
    response = (
        _client(client)
        .table("workflow_steps")
        .update({
            "status": WorkflowStepStatus.SUPERSEDED.value,
            "reason": reason[:2000],
            "updated_at": _now(),
        })
        .eq("id", step_id)
        .execute()
    )
    return (response.data or [{}])[0]


def mark_step_ready(
    step_id: str,
    *,
    reason: Optional[str] = None,
    client: Any | None = None,
) -> Dict[str, Any]:
    from app.services.workflow.transitions import assert_transition

    latest = (
        _client(client)
        .table("workflow_steps")
        .select("status")
        .eq("id", step_id)
        .limit(1)
        .execute()
    )
    current = ((latest.data or [{}])[0]).get("status")
    assert_transition(current, WorkflowStepStatus.READY.value)
    payload: Dict[str, Any] = {
        "status": WorkflowStepStatus.READY.value,
        "requires_confirmation": False,
        "updated_at": _now(),
    }
    if reason is not None:
        payload["reason"] = reason[:2000]
    response = (
        _client(client)
        .table("workflow_steps")
        .update(payload)
        .eq("id", step_id)
        .execute()
    )
    return (response.data or [{}])[0]


def is_reusable(step: Optional[Mapping[str, Any]]) -> bool:
    if not step:
        return False
    return str(step.get("status") or "") in REUSABLE_STATUSES


def execute_persisted_tool_step(
    *,
    session_id: str,
    user_id: str,
    step_type: WorkflowStepType,
    input_payload: Optional[Mapping[str, Any]] = None,
    runner,
    client: Any | None = None,
    allow_reuse: bool = True,
    bump_version: bool = False,
):
    """Wrap a tool call with begin/complete/fail persistence.

    If the latest step is already completed/skipped and ``allow_reuse`` is True,
    returns ``(step_row, ToolResult|None, reused=True)`` without calling runner.

    ``runner`` must return a ``ToolResult`` (and may return extra values via a
    tuple ``(ToolResult, *extra)``).
    """
    db = _client(client)
    step_row = begin_step(
        session_id,
        step_type,
        input_payload=input_payload,
        bump_version=bump_version,
        client=db,
    )
    if allow_reuse and not bump_version and is_reusable(step_row):
        output = step_row.get("output") or {}
        reused_result = None
        if isinstance(output, dict) and output.get("tool"):
            try:
                reused_result = ToolResult(**{
                    key: output.get(key)
                    for key in (
                        "tool", "status", "summary", "findings", "warnings",
                        "artifacts", "metadata", "suggested_next_actions",
                    )
                    if key in output or key == "tool"
                })
            except Exception:
                reused_result = None
        update_session_summary(
            session_id,
            user_id,
            next_action=None,
            last_failed_step="",
            client=db,
        )
        return step_row, reused_result, True, ()

    # Fresh running claim — execute tool.
    if str(step_row.get("status")) != WorkflowStepStatus.RUNNING.value:
        # Another worker holds a fresh running claim; do not double-execute.
        raise RuntimeError(
            f"Workflow step {step_type.value} is already running elsewhere"
        )

    update_session_summary(
        session_id,
        user_id,
        next_action=step_type.value,
        last_failed_step="",
        client=db,
    )
    try:
        produced = runner()
        extras: tuple = ()
        if isinstance(produced, tuple):
            result, *extras = produced
        else:
            result = produced
        if not isinstance(result, ToolResult):
            raise TypeError("Persisted tool runner must return ToolResult")
        if result.status == "failed":
            fail_step(
                str(step_row["id"]),
                error=result.summary or "Tool reported failure",
                step_type=step_type,
                client=db,
            )
            update_session_summary(
                session_id,
                user_id,
                next_action=step_type.value,
                last_failed_step=step_type.value,
                client=db,
            )
            return step_row, result, False, tuple(extras)
        if result.status == "awaiting_user":
            mark_step_awaiting_user(
                str(step_row["id"]),
                reason=result.summary or "Awaiting user confirmation",
                output=result,
                client=db,
            )
            update_session_summary(
                session_id,
                user_id,
                next_action=step_type.value,
                client=db,
            )
            return step_row, result, False, tuple(extras)
        if result.status == "skipped":
            completed = skip_step(
                str(step_row["id"]),
                reason=result.summary or "Skipped",
                output=result,
                client=db,
            )
            return completed, result, False, tuple(extras)
        completed = complete_step(str(step_row["id"]), output=result, client=db)
        return completed, result, False, tuple(extras)
    except Exception as exc:
        fail_step(
            str(step_row["id"]),
            error=exc,
            step_type=step_type,
            client=db,
        )
        update_session_summary(
            session_id,
            user_id,
            next_action=step_type.value,
            last_failed_step=step_type.value,
            client=db,
        )
        raise
