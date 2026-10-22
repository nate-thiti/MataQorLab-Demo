"""AI-safe capability catalog — availability decided by backend state only."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, Field

from app.services.tools.registry import STEP_REGISTRY
from app.services.web_search import web_search_enabled
from app.services.workflow.models import SETUP_SEQUENCE

CapabilityCategory = Literal["data_setup", "analytics", "external_context"]


class AICapability(BaseModel):
    capability_id: str
    category: CapabilityCategory
    name: str
    description: str
    purpose: str = ""
    available: bool = False
    unavailable_reason: Optional[str] = None
    requires_user_context: List[str] = Field(default_factory=list)
    possible_outputs: List[str] = Field(default_factory=list)
    authority: str


_SETUP_META: Dict[str, Dict[str, str]] = {
    "inspect": {
        "name": "Source Inspect",
        "description": "Inspect source structure and bounded profile.",
        "purpose": "Understand columns, types, and basic data quality signals.",
    },
    "prepare": {
        "name": "Prepare Data",
        "description": "Materialize a prepared dataset artifact for downstream steps.",
        "purpose": "Create a stable working dataset for mapping/cleaning.",
    },
    "map": {
        "name": "Schema Mapping",
        "description": "Infer or refine semantic column roles.",
        "purpose": "Assign analytical meaning to columns.",
    },
    "validate": {
        "name": "Validate Readiness",
        "description": "Check data-contract and mapping readiness.",
        "purpose": "Surface blockers as structured decisions, not user checklists.",
    },
    "clean": {
        "name": "Data Cleaning",
        "description": "Apply the approved cleaning policy.",
        "purpose": "Deterministically clean the prepared dataset.",
    },
    "finalize": {
        "name": "Finalize Dataset",
        "description": "Publish a ready Dataset Version for analysis.",
        "purpose": "Mark the setup session ready for analytics.",
    },
}

_ANALYTICS_META: List[Dict[str, str]] = [
    {
        "capability_id": "query_data",
        "name": "Query Data",
        "description": "Answer a deterministic question using the ready dataset (DuckDB).",
        "purpose": "Governed analytical query via question_analytics.",
        "authority": "question_analytics",
    },
    {
        "capability_id": "calculate_metrics",
        "name": "Calculate Metrics",
        "description": "Compute domain KPIs and summary metrics.",
        "purpose": "Deterministic KPI computation over the ready dataset.",
        "authority": "analytics_service",
    },
    {
        "capability_id": "domain_analysis",
        "name": "Domain Analysis",
        "description": "Infer domain roles and domain-specific analytics.",
        "purpose": "domain_analytics over the ready dataset.",
        "authority": "domain_analytics",
    },
    {
        "capability_id": "generate_findings",
        "name": "Generate Findings",
        "description": "Produce structured analytical findings from query results.",
        "purpose": "Surface findings without inventing numbers.",
        "authority": "question_analytics",
    },
    {
        "capability_id": "evaluate_assurance",
        "name": "Evaluate Assurance",
        "description": "Build computation / readiness / business-context assurance layers.",
        "purpose": "decision_assurance packet for analysis answers.",
        "authority": "decision_assurance",
    },
]


def _next_executable_steps(workflow_plan: Optional[Mapping[str, Any]]) -> set[str]:
    if not workflow_plan:
        return set()
    next_action = workflow_plan.get("next_action") or {}
    action = str(next_action.get("action") or "")
    step = str(next_action.get("step_type") or "").strip().lower()
    if action in {"execute", "retry"} and step:
        return {step}
    # Also allow pending steps that are next_action.execute candidates by status.
    allowed: set[str] = set()
    for item in list(workflow_plan.get("steps") or []):
        if not isinstance(item, Mapping):
            continue
        st = str(item.get("step_type") or item.get("step") or "")
        status = str(item.get("status") or "")
        if status in {"pending", "stale", "failed"} and st:
            # Only surface the first pending in SETUP_SEQUENCE as available.
            allowed.add(st)
            break
    return allowed


def build_capability_catalog(
    *,
    session: Mapping[str, Any],
    workflow_plan: Optional[Mapping[str, Any]] = None,
    user_tier: str = "free",
    user_question: Optional[str] = None,
) -> List[AICapability]:
    """Backend-authoritative availability view for the AI Toolbox Controller."""
    status = str(session.get("status") or "")
    ready = status == "ready"
    mode_setup = not ready
    executable = _next_executable_steps(workflow_plan) if mode_setup else set()
    awaiting = bool((workflow_plan or {}).get("awaiting_user"))

    caps: List[AICapability] = []
    registry = STEP_REGISTRY
    for step in SETUP_SEQUENCE:
        step_id = step.value
        meta = _SETUP_META.get(step_id, {})
        entry = registry.get(step_id) or {}
        available = False
        reason = None
        if ready:
            reason = "dataset_ready_setup_inactive"
        elif awaiting and step_id not in executable:
            reason = "awaiting_user"
        elif step_id in executable:
            available = True
        else:
            reason = "dependency_or_not_next"
        caps.append(AICapability(
            capability_id=step_id,
            category="data_setup",
            name=meta.get("name") or step_id,
            description=meta.get("description") or "",
            purpose=meta.get("purpose") or "",
            available=available,
            unavailable_reason=reason,
            requires_user_context=[],
            possible_outputs=["tool_result", "awaiting_user", "worklog_stamp"],
            authority=str(entry.get("authority") or "workflow_engine"),
        ))

    # Analytics / web_search are never executable by this controller.
    # After setup is ready, chat routes to the analysis agent instead.
    for meta in _ANALYTICS_META:
        caps.append(AICapability(
            capability_id=meta["capability_id"],
            category="analytics",
            name=meta["name"],
            description=meta["description"],
            purpose=meta["purpose"],
            available=False,
            unavailable_reason=(
                "handled_by_analysis_agent" if ready else "dataset_not_ready"
            ),
            possible_outputs=["analytics_result", "worklog_stamp", "assurance"],
            authority=meta["authority"],
        ))

    web_reason = "dataset_not_ready"
    if ready:
        if not web_search_enabled(user_tier):
            web_reason = "plan_not_eligible"
        else:
            # Setup controller never executes web_search; analysis agent owns it.
            web_reason = "handled_by_analysis_agent"
    caps.append(AICapability(
        capability_id="web_search",
        category="external_context",
        name="Web Search",
        description="Search external/current context via DuckDuckGo when eligible.",
        purpose="Provide external context separate from dataset-derived computation.",
        available=False,
        unavailable_reason=web_reason,
        possible_outputs=["web_sources", "worklog_stamp"],
        authority="analysis_external_context",
    ))
    return caps


def available_capability_ids(capabilities: List[AICapability]) -> List[str]:
    return [c.capability_id for c in capabilities if c.available]


def capability_summary(capabilities: List[AICapability]) -> List[Dict[str, Any]]:
    return [c.model_dump() for c in capabilities]
