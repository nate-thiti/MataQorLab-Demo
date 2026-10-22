"""Controller Working Memory — backend-truth only."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, Field

from app.services.orchestrator.capabilities import (
    AICapability,
    build_capability_catalog,
    capability_summary,
)
from app.services.orchestrator.unresolved import (
    UnresolvedDecision,
    resolve_unresolved_decisions,
    select_one_decision,
)
from app.services.etl_pipeline import normalize_data_contract
from app.services.orchestrator.decision_identity import (
    decision_context_fingerprint,
    is_decision_confirmed,
)


class ControllerWorkingMemory(BaseModel):
    mode: Literal["setup", "analysis"]
    source_summary: Dict[str, Any] = Field(default_factory=dict)
    workflow_summary: Dict[str, Any] = Field(default_factory=dict)
    confirmed_context: Dict[str, Any] = Field(default_factory=dict)
    mapping_summary: Dict[str, Any] = Field(default_factory=dict)
    data_quality_summary: Dict[str, Any] = Field(default_factory=dict)
    latest_results: List[Dict[str, Any]] = Field(default_factory=list)
    unresolved_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    active_decision: Optional[Dict[str, Any]] = None
    available_capabilities: List[Dict[str, Any]] = Field(default_factory=list)
    recent_worklog_stamps: List[Dict[str, Any]] = Field(default_factory=list)
    user_question: Optional[str] = None


def _confirmed_context(session: Mapping[str, Any]) -> Dict[str, Any]:
    progress = session.get("processing_progress") or {}
    confirmed_raw = progress.get("confirmed_decisions") if isinstance(progress, Mapping) else {}
    out: Dict[str, Any] = {}
    if isinstance(confirmed_raw, Mapping):
        for key, entry in confirmed_raw.items():
            if not isinstance(entry, Mapping):
                continue
            if str(entry.get("source") or "") != "user_confirmed":
                continue
            if entry.get("value") is None and entry.get("value") is not False:
                continue
            fp = str(entry.get("fingerprint") or "")
            if fp and fp != decision_context_fingerprint(session, str(key)):
                continue
            out[str(key)] = {
                "value": entry.get("value"),
                "source": "user_confirmed",
                "fingerprint": fp or None,
                "version": entry.get("version"),
            }

    recipe = session.get("cleaning_recipe") or {}
    contract_raw = recipe.get("data_contract") if isinstance(recipe, Mapping) else {}
    contract = normalize_data_contract(contract_raw)
    for key in (
        "row_grain",
        "business_purpose",
        "data_owner",
        "metric_definition",
        "period_status",
    ):
        if key in out:
            continue
        val = contract.get(key) or (contract_raw or {}).get(key)
        if val and is_decision_confirmed(session, key if key != "metric_definition" else "primary_metric"):
            out[key] = {"value": val, "source": "user_confirmed"}
    if "return_policy" not in out and is_decision_confirmed(session, "return_policy"):
        policy = (contract_raw or {}).get("return_policy") if isinstance(contract_raw, Mapping) else None
        out["return_policy"] = {
            "value": policy.get("value") if isinstance(policy, Mapping) else policy,
            "source": "user_confirmed",
        }
    if "mapping_confirmed" not in out and is_decision_confirmed(session, "mapping_confirmed"):
        out["mapping_confirmed"] = {"value": True, "source": "user_confirmed"}
    if "business_context_reviewed" not in out and is_decision_confirmed(session, "business_context_reviewed"):
        out["business_context_reviewed"] = {"value": True, "source": "user_confirmed"}
    return out


def _progress_stamps(session: Mapping[str, Any]) -> List[Dict[str, Any]]:
    progress = session.get("processing_progress") or {}
    if not isinstance(progress, Mapping):
        return []
    stamps = progress.get("worklog_stamps") or []
    return [dict(s) for s in stamps if isinstance(s, Mapping)][-20:]


def _active_decision(session: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    progress = session.get("processing_progress") or {}
    if not isinstance(progress, Mapping):
        return None
    active = progress.get("active_decision")
    return dict(active) if isinstance(active, Mapping) else None


def build_working_memory(
    *,
    session: Mapping[str, Any],
    workflow_plan: Optional[Mapping[str, Any]] = None,
    source_summary: Optional[Mapping[str, Any]] = None,
    last_tool_summary: Optional[Mapping[str, Any]] = None,
    user_question: Optional[str] = None,
    user_tier: str = "free",
    include_contract_decisions: bool = True,
) -> ControllerWorkingMemory:
    ready = str(session.get("status") or "") == "ready"
    mode: Literal["setup", "analysis"] = "analysis" if ready else "setup"
    capabilities = build_capability_catalog(
        session=session,
        workflow_plan=workflow_plan,
        user_tier=user_tier,
        user_question=user_question,
    )
    decisions: List[UnresolvedDecision] = []
    if mode == "setup" and include_contract_decisions:
        decisions = resolve_unresolved_decisions(session)

    latest: List[Dict[str, Any]] = []
    if last_tool_summary:
        latest.append(dict(last_tool_summary))

    mapping = dict(session.get("column_mapping") or {})
    scan = session.get("scan_result") or {}
    quality = {
        "row_count": scan.get("row_count") if isinstance(scan, Mapping) else None,
        "column_count": (
            scan.get("column_count")
            if isinstance(scan, Mapping)
            else None
        ),
        "duplicate_estimate": (
            scan.get("duplicate_estimate")
            if isinstance(scan, Mapping)
            else None
        ),
    }

    plan = workflow_plan or {}
    return ControllerWorkingMemory(
        mode=mode,
        source_summary=dict(source_summary or {}),
        workflow_summary={
            "status": plan.get("status") or session.get("status"),
            "current_step": plan.get("current_step"),
            "next_action": plan.get("next_action"),
            "awaiting_user": plan.get("awaiting_user"),
            "ready_for_analysis": ready,
        },
        confirmed_context=_confirmed_context(session),
        mapping_summary={
            "mapped_columns": len(mapping),
            "roles": sorted({str(v) for v in mapping.values() if v})[:30],
        },
        data_quality_summary=quality,
        latest_results=latest,
        unresolved_decisions=[d.model_dump() for d in decisions[:12]],
        active_decision=_active_decision(session),
        available_capabilities=capability_summary(capabilities),
        recent_worklog_stamps=_progress_stamps(session),
        user_question=user_question,
    )


def next_unresolved(memory: ControllerWorkingMemory) -> Optional[UnresolvedDecision]:
    items = [UnresolvedDecision(**d) for d in memory.unresolved_decisions]
    return select_one_decision(items)


def memory_for_prompt(memory: ControllerWorkingMemory) -> Dict[str, Any]:
    """Compact prompt-safe view — no secrets/paths."""
    available = [
        c for c in memory.available_capabilities if c.get("available")
    ]
    unavailable = [
        {"id": c.get("capability_id"), "reason": c.get("unavailable_reason")}
        for c in memory.available_capabilities
        if not c.get("available")
    ][:12]
    top = memory.unresolved_decisions[:1]
    return {
        "mode": memory.mode,
        "source_summary": memory.source_summary,
        "workflow_summary": memory.workflow_summary,
        "confirmed_context": memory.confirmed_context,
        "mapping_summary": memory.mapping_summary,
        "data_quality_summary": memory.data_quality_summary,
        "latest_results": memory.latest_results[:2],
        "active_decision": memory.active_decision,
        "next_unresolved_decision": top[0] if top else None,
        "unresolved_count": len(memory.unresolved_decisions),
        "available_capabilities": available,
        "unavailable_capabilities": unavailable,
        "recent_worklog_stamps": memory.recent_worklog_stamps[-5:],
        "user_question": memory.user_question,
    }
