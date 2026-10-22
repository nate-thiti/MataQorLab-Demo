"""Build bounded orchestrator LLM context from WorkflowEngine + session."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from app.services.workflow.engine import WorkflowEngine
from app.services.workflow.orchestrator_context import build_orchestrator_workflow_context


def _compact_scan_summary(session: Mapping[str, Any]) -> Dict[str, Any]:
    scan = session.get("scan_result") or {}
    if not isinstance(scan, dict):
        return {}
    columns = scan.get("columns") or []
    col_summaries = []
    for col in list(columns)[:40]:
        if not isinstance(col, dict):
            continue
        col_summaries.append({
            "name": col.get("name"),
            "inferred_type": col.get("inferred_type") or col.get("dtype"),
            "missing_pct": col.get("missing_pct") or col.get("null_pct"),
            "needs_review": col.get("needs_review"),
            "role": col.get("suggested_role") or col.get("role"),
        })
    return {
        "row_count": scan.get("row_count"),
        "column_count": scan.get("column_count") or len(columns),
        "suggested_domain": scan.get("suggested_domain"),
        "date_range": scan.get("date_range"),
        "duplicate_estimate": scan.get("duplicate_estimate") or scan.get("duplicate_rows"),
        "columns": col_summaries,
        "cleaning_profile": session.get("cleaning_profile"),
        "source_type": session.get("source_type"),
        "source_label": (session.get("source_ref") or {}).get("file_name")
        if isinstance(session.get("source_ref"), dict)
        else None,
    }


def _contract_summary(session: Mapping[str, Any]) -> Dict[str, Any]:
    recipe = session.get("cleaning_recipe") or {}
    contract = recipe.get("data_contract") if isinstance(recipe, dict) else {}
    if not isinstance(contract, dict):
        return {}
    return {
        "row_grain": contract.get("row_grain"),
        "mapping_confirmed": contract.get("mapping_confirmed"),
        "business_context_reviewed": contract.get("business_context_reviewed"),
        "return_policy": contract.get("return_policy"),
        "requires_confirmation": contract.get("requires_confirmation"),
    }


def _recent_turns(messages: Optional[List[Mapping[str, Any]]]) -> List[Dict[str, str]]:
    turns: List[Dict[str, str]] = []
    for msg in list(messages or [])[-8:]:
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        turns.append({"role": role, "content": content[:800]})
    return turns


def build_orchestrator_llm_context(
    *,
    engine: WorkflowEngine,
    session_id: str,
    session: Mapping[str, Any],
    user_id: str,
    messages: Optional[List[Mapping[str, Any]]] = None,
    last_tool_summary: Optional[Mapping[str, Any]] = None,
    plan: Any | None = None,
) -> Dict[str, Any]:
    if plan is None:
        plan = engine.get_workflow_plan(
            session_id, session=session, user_id=user_id, as_model=True
        )
    workflow_ctx = build_orchestrator_workflow_context(plan)
    return {
        "workflow": workflow_ctx,
        "plan": plan,
        "source_summary": _compact_scan_summary(session),
        "data_contract": _contract_summary(session),
        "recent_turns": _recent_turns(messages),
        "last_tool_summary": dict(last_tool_summary or {}),
        "session_status": session.get("status"),
        "cleaning_profile": session.get("cleaning_profile"),
    }
