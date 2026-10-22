"""Workflow persistence (Phase 3) + Workflow Engine (Phase 4)."""

from app.services.workflow.artifacts import (
    cleaned_artifact_name,
    load_cleaned_artifact,
    persist_cleaned_handle,
)
from app.services.workflow.dependencies import (
    STEP_DEPENDENCIES,
    STEP_DEPENDENTS,
    invalidation_targets,
    requires,
)
from app.services.workflow.models import (
    SETUP_SEQUENCE,
    ConfirmationDecision,
    WorkflowDecision,
    WorkflowErrorCode,
    WorkflowPlan,
    WorkflowPlanStep,
    WorkflowStepStatus,
    WorkflowStepType,
)
from app.services.workflow.policies import (
    SKIP_ALLOWED,
    build_step_fingerprint,
    can_skip,
    evaluate_confirmation_requirement,
)
from app.services.workflow.state import (
    begin_step,
    complete_step,
    execute_persisted_tool_step,
    fail_step,
    get_latest_step,
    get_resume_state,
    get_workflow_steps,
    is_reusable,
    mark_step_awaiting_user,
    mark_step_ready,
    mark_step_stale,
    mark_step_superseded,
    skip_step,
    tool_result_to_output,
    update_session_summary,
)
from app.services.workflow.transitions import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    assert_transition,
    can_transition,
)

__all__ = [
    "WorkflowEngine",
    "get_workflow_engine",
    "WorkflowDecision",
    "WorkflowErrorCode",
    "WorkflowPlan",
    "WorkflowPlanStep",
    "ConfirmationDecision",
    "WorkflowStepStatus",
    "WorkflowStepType",
    "SETUP_SEQUENCE",
    "STEP_DEPENDENCIES",
    "STEP_DEPENDENTS",
    "SKIP_ALLOWED",
    "ALLOWED_TRANSITIONS",
    "InvalidTransitionError",
    "assert_transition",
    "can_transition",
    "requires",
    "invalidation_targets",
    "can_skip",
    "build_step_fingerprint",
    "evaluate_confirmation_requirement",
    "begin_step",
    "complete_step",
    "fail_step",
    "skip_step",
    "mark_step_awaiting_user",
    "mark_step_ready",
    "mark_step_stale",
    "mark_step_superseded",
    "get_workflow_steps",
    "get_latest_step",
    "get_resume_state",
    "is_reusable",
    "execute_persisted_tool_step",
    "tool_result_to_output",
    "update_session_summary",
    "persist_cleaned_handle",
    "load_cleaned_artifact",
    "cleaned_artifact_name",
]


def __getattr__(name: str):
    if name in {"WorkflowEngine", "get_workflow_engine"}:
        from app.services.workflow.engine import WorkflowEngine, get_workflow_engine

        return {
            "WorkflowEngine": WorkflowEngine,
            "get_workflow_engine": get_workflow_engine,
        }[name]
    raise AttributeError(name)
