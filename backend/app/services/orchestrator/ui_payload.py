"""Safe UI-facing orchestration payload (Phase 6)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from app.services.orchestrator.decision_models import OrchestratorResult
from app.services.orchestrator.answer_apply import validate_active_decision_completeness

_STEP_ORDER = ("inspect", "prepare", "clean", "map", "validate", "finalize")


def _safe_findings(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in list(raw or [])[:20]:
        if not isinstance(item, Mapping):
            continue
        out.append({
            "type": item.get("type"),
            "count": item.get("count"),
            "column": item.get("column"),
            "status": item.get("status"),
        })
    return out


def build_tool_result_view(engine_result: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not engine_result:
        return None
    step = str(
        engine_result.get("step")
        or engine_result.get("step_type")
        or ""
    ).strip()
    status = str(engine_result.get("status") or "").strip()
    if not step and not status:
        return None
    blocked_meta = {
        "path", "storage_path", "storage_key", "secret_path", "traceback",
        "credential", "credentials", "token", "uri", "url",
    }
    safe_meta = {}
    for k, v in dict(engine_result.get("metadata") or {}).items():
        key = str(k).lower()
        if key in blocked_meta or any(part in key for part in ("path", "secret", "token", "credential")):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            safe_meta[k] = v
    return {
        "step_type": step or None,
        "status": status or None,
        "summary": (str(engine_result.get("summary") or "")[:400] or None),
        "findings": _safe_findings(engine_result.get("findings")),
        "warnings": _safe_findings(engine_result.get("warnings")),
        "metadata": safe_meta,
    }


def build_workflow_progress(
    workflow_plan: Optional[Mapping[str, Any]],
    *,
    session: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not workflow_plan:
        return None
    steps_raw = workflow_plan.get("steps") or []
    by_type: Dict[str, Mapping[str, Any]] = {}
    for item in steps_raw:
        if not isinstance(item, Mapping):
            continue
        step_type = str(item.get("step_type") or item.get("step") or "")
        if step_type:
            by_type[step_type] = item
    steps_out: List[Dict[str, Any]] = []
    for step_type in _STEP_ORDER:
        item = by_type.get(step_type) or {}
        status = str(item.get("status") or "pending")
        steps_out.append({
            "step_type": step_type,
            "status": status,
            "version": item.get("version"),
            "attempt": item.get("attempt"),
            "summary": item.get("latest_summary") or item.get("summary"),
            "retryable": bool(item.get("retryable")),
            "requires_confirmation": bool(item.get("requires_confirmation")),
            "stale_reason": item.get("stale_reason"),
        })
    session_status = str((session or {}).get("status") or workflow_plan.get("status") or "")
    return {
        "session_id": workflow_plan.get("session_id") or (session or {}).get("id"),
        "status": session_status or workflow_plan.get("status"),
        "current_step": workflow_plan.get("current_step"),
        "steps": steps_out,
        "ready_for_analysis": session_status == "ready",
    }


def build_source_summary(session: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not session:
        return None
    scan = session.get("scan_result") or {}
    source_ref = session.get("source_ref") or {}
    label = None
    if isinstance(source_ref, Mapping):
        label = source_ref.get("file_name") or source_ref.get("label")
    return {
        "name": label or session.get("output_file"),
        "source_type": session.get("source_type"),
        "row_count": scan.get("row_count") if isinstance(scan, Mapping) else None,
        "column_count": (
            scan.get("column_count")
            if isinstance(scan, Mapping)
            else None
        ) or (
            len(scan.get("columns") or [])
            if isinstance(scan, Mapping)
            else None
        ),
        "date_range": scan.get("date_range") if isinstance(scan, Mapping) else None,
        "cleaning_profile": session.get("cleaning_profile"),
    }


def build_assurance_summary(session: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not session:
        return None
    recipe = session.get("cleaning_recipe") or {}
    contract = recipe.get("data_contract") if isinstance(recipe, Mapping) else {}
    contract = contract if isinstance(contract, Mapping) else {}
    ready = str(session.get("status") or "") == "ready"
    return {
        "computation": "verified" if ready else "pending",
        "data_readiness": "ready" if ready else "pending",
        "business_context": (
            "confirmed"
            if contract.get("business_context_reviewed")
            else "pending"
        ),
        "mapping_confirmed": bool(contract.get("mapping_confirmed")),
    }


def _session_active_decision(
    session: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not session or not isinstance(session.get("processing_progress"), Mapping):
        return None
    raw = session["processing_progress"].get("active_decision")
    if not isinstance(raw, Mapping):
        return None
    key = str(raw.get("decision_key") or "").strip()
    if not key:
        return None
    opts = list(raw.get("options") or [])
    free_text = raw.get("free_text_allowed")
    if free_text is None:
        free_text = not opts
    payload = {
        "decision_key": key,
        "status": str(raw.get("status") or "pending"),
        "question": raw.get("question"),
        "options": opts,
        "expected_input": raw.get("expected_input")
        or ("single_choice" if opts else "free_text"),
        "free_text_allowed": bool(free_text),
        "step_type": raw.get("step_type"),
        "reason_code": raw.get("reason_code"),
        "context": raw.get("context"),
    }
    ok, err = validate_active_decision_completeness(payload)
    if not ok:
        return None
    return payload


def _resolved_decision_key_from_audit(
    result: OrchestratorResult,
) -> Optional[str]:
    actions = (result.audit or {}).get("actions") or []
    for action in reversed(list(actions)):
        if not isinstance(action, Mapping):
            continue
        if str(action.get("decision_type") or "") == "collect_input_applied":
            key = str(action.get("decision_key") or "").strip()
            if key:
                return key
    return None


def _reconcile_awaiting_user(
    *,
    result: OrchestratorResult,
    session: Optional[Mapping[str, Any]],
    active_decision: Optional[Dict[str, Any]],
    workflow: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    decision_type = getattr(result.decision, "type", None)
    plan_awaiting = None
    if isinstance(result.workflow_plan, Mapping):
        plan_awaiting = result.workflow_plan.get("awaiting_user")
    if isinstance(workflow, Mapping):
        plan_awaiting = plan_awaiting or workflow.get("awaiting_user")

    if active_decision and str(active_decision.get("status") or "") == "pending":
        base = dict(plan_awaiting) if isinstance(plan_awaiting, Mapping) else {}
        return {
            **base,
            "decision_key": active_decision.get("decision_key"),
            "question": active_decision.get("question") or base.get("question"),
            "options": active_decision.get("options") or base.get("options") or [],
            "expected_input": active_decision.get("expected_input"),
            "free_text_allowed": active_decision.get("free_text_allowed", True),
            "step_type": active_decision.get("step_type") or base.get("step_type"),
            "reason_code": active_decision.get("reason_code") or base.get("reason_code"),
            "context": active_decision.get("context") or base.get("context"),
        }

    if decision_type == "ask_user" and result.awaiting_user:
        return dict(result.awaiting_user)

    return None


def _poll_recommended(
    *,
    session: Optional[Mapping[str, Any]],
    workflow: Optional[Dict[str, Any]],
    active_decision: Optional[Dict[str, Any]],
) -> bool:
    if not session:
        return False
    status = str(session.get("status") or "")
    if status in {"ready", "failed", "cancelled", "awaiting_answers"}:
        if active_decision and str(active_decision.get("status") or "") == "pending":
            return False
        if status == "awaiting_answers":
            return False
    progress = session.get("processing_progress") or {}
    stage = str(progress.get("stage") or "")
    if stage in {"worker_claimed", "external_async", "async_job"}:
        return True
    steps = list((workflow or {}).get("steps") or [])
    if any(str(s.get("status") or "") == "running" for s in steps if isinstance(s, Mapping)):
        return status == "processing"
    return False


def _controller_activity(
    *,
    workflow: Optional[Dict[str, Any]],
    result: OrchestratorResult,
    stop_reason: Optional[str] = None,
) -> Optional[str]:
    if stop_reason == "awaiting_user":
        return "awaiting_user"
    if stop_reason == "ready":
        return "ready"
    steps = list((workflow or {}).get("steps") or [])
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        if str(step.get("status") or "") == "running":
            return str(step.get("step_type") or step.get("step") or "running")
    engine = result.engine_result or {}
    if isinstance(engine, Mapping) and engine.get("step"):
        return str(engine.get("step"))
    return None


def build_orchestration_ui_payload(
    result: OrchestratorResult,
    *,
    session: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    workflow = build_workflow_progress(result.workflow_plan, session=session)
    tool_result = build_tool_result_view(result.engine_result)
    decision_type = getattr(result.decision, "type", None)
    stamps = list(result.worklog_stamps or [])
    active_decision = _session_active_decision(session)
    # A just-persisted decision may not be visible in the immediate session
    # refresh yet. The current ask_user result is authoritative for this turn,
    # so surface a transient complete decision instead of leaving the UI with
    # an unanswerable question. Never apply this fallback to respond/tool turns.
    if active_decision is None and decision_type == "ask_user" and result.awaiting_user:
        current_ask = dict(result.awaiting_user)
        current_options = list(current_ask.get("options") or result.options or [])
        active_decision = {
            "decision_key": current_ask.get("decision_key")
            or current_ask.get("context_key")
            or "confirmation",
            "status": "pending",
            "question": current_ask.get("question"),
            "options": current_options,
            "expected_input": current_ask.get("expected_input")
            or ("option_or_text" if current_options else "free_text"),
            "free_text_allowed": current_ask.get("free_text_allowed", True),
            "step_type": current_ask.get("step_type"),
            "reason_code": current_ask.get("reason_code") or current_ask.get("reason"),
            "context": current_ask.get("context"),
        }
    incomplete_active_decision = None
    if session and isinstance(session.get("processing_progress"), Mapping):
        raw_ad = session["processing_progress"].get("active_decision")
        if isinstance(raw_ad, Mapping) and str(raw_ad.get("status") or "pending") == "pending":
            ok, err = validate_active_decision_completeness(raw_ad)
            if not ok:
                incomplete_active_decision = err
                active_decision = None
    awaiting = _reconcile_awaiting_user(
        result=result,
        session=session,
        active_decision=active_decision,
        workflow=workflow,
    )
    resolved_decision_key = _resolved_decision_key_from_audit(result)
    if session and isinstance(session.get("processing_progress"), Mapping):
        progress_resolved = session["processing_progress"].get("resolved_decision_key")
        if progress_resolved and not resolved_decision_key:
            resolved_decision_key = str(progress_resolved)
    stop_reason = (result.audit or {}).get("stop_reason")
    performance = (result.audit or {}).get("performance")
    continuation_available = bool((result.audit or {}).get("continuation_available"))
    if session and isinstance(session.get("processing_progress"), Mapping):
        persisted = session["processing_progress"].get("worklog_stamps") or []
        if isinstance(persisted, list) and not stamps:
            stamps = [dict(s) for s in persisted if isinstance(s, Mapping)][-8:]
    poll = _poll_recommended(
        session=session,
        workflow=workflow,
        active_decision=active_decision,
    )
    return {
        "session_id": str(session.get("id") or "") if session else None,
        "session_status": session.get("status") if session else None,
        "updated_at": session.get("updated_at") if session else None,
        "decision_type": decision_type,
        "step_type": getattr(result.decision, "step_type", None),
        "options": result.options,
        "active_decision": active_decision,
        "incomplete_active_decision": incomplete_active_decision,
        "resolved_decision_key": resolved_decision_key,
        "awaiting_user": awaiting,
        "workflow": workflow,
        "workflow_plan": result.workflow_plan,  # backward compatible
        "tool_result": tool_result,
        "engine_result": result.engine_result,  # backward compatible
        "source": build_source_summary(session),
        "assurance": build_assurance_summary(session),
        "ready_for_analysis": bool((workflow or {}).get("ready_for_analysis")),
        "prompt_version": result.prompt_version,
        "worklog_stamps": stamps,
        "working_memory": result.working_memory,
        "poll_recommended": poll,
        "controller_activity": _controller_activity(
            workflow=workflow,
            result=result,
            stop_reason=str(stop_reason) if stop_reason else None,
        ),
        "stop_reason": stop_reason,
        "continuation_available": continuation_available,
        "performance": performance,
        "audit": {
            "prompt_version": result.prompt_version,
            "actions": (result.audit or {}).get("actions"),
            "stop_reason": stop_reason,
            "continuation_available": continuation_available,
        },
    }
