"""Workflow step enums, decisions, and constants."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, FrozenSet, Literal, Optional

from pydantic import BaseModel, Field


class WorkflowStepType(str, Enum):
    INSPECT = "inspect"
    PREPARE = "prepare"
    MAP = "map"
    VALIDATE = "validate"
    CLEAN = "clean"
    FINALIZE = "finalize"


class WorkflowStepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    AWAITING_USER = "awaiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STALE = "stale"
    SUPERSEDED = "superseded"


class WorkflowErrorCode(str, Enum):
    DEPENDENCY_NOT_SATISFIED = "DEPENDENCY_NOT_SATISFIED"
    STEP_ALREADY_RUNNING = "STEP_ALREADY_RUNNING"
    STEP_AWAITING_USER = "STEP_AWAITING_USER"
    STEP_NOT_RETRYABLE = "STEP_NOT_RETRYABLE"
    UNKNOWN_STEP = "UNKNOWN_STEP"
    STALE_DEPENDENCY = "STALE_DEPENDENCY"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    SKIP_NOT_ALLOWED = "SKIP_NOT_ALLOWED"
    MAX_ACTIONS_EXCEEDED = "MAX_ACTIONS_EXCEEDED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFIRMATION_REJECTED = "CONFIRMATION_REJECTED"
    CONFIRMATION_STALE = "CONFIRMATION_STALE"
    WORKFLOW_RPC_UNAVAILABLE = "WORKFLOW_RPC_UNAVAILABLE"


class WorkflowDecision(BaseModel):
    """Deterministic backend workflow decision — not an LLM schema."""

    action: Literal[
        "execute",
        "reuse",
        "retry",
        "skip",
        "blocked",
        "awaiting_user",
        "complete",
    ]
    step_type: Optional[str] = None
    reason: str
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConfirmationDecision(BaseModel):
    """Deterministic confirmation evaluation — not an LLM judgment."""

    required: bool
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    confirmation_fingerprint: Optional[str] = None


class WorkflowPlanStep(BaseModel):
    step_type: str
    status: str
    version: Optional[int] = None
    attempt: Optional[int] = None
    reusable: bool = False
    retryable: bool = False
    requires_confirmation: bool = False
    stale_reason: Optional[str] = None
    latest_summary: Optional[str] = None


class WorkflowPlan(BaseModel):
    """Stable internal plan contract for resume / future AI orchestrator."""

    session_id: str
    status: str
    current_step: Optional[str] = None
    next_action: Optional[WorkflowDecision] = None
    steps: list[WorkflowPlanStep] = Field(default_factory=list)
    blockers: list[Dict[str, Any]] = Field(default_factory=list)
    awaiting_user: Optional[Dict[str, Any]] = None
    last_failed_step: Optional[str] = None


# Compatibility planning order (not a DB constraint / not sole dependency truth).
SETUP_SEQUENCE: tuple[WorkflowStepType, ...] = (
    WorkflowStepType.INSPECT,
    WorkflowStepType.PREPARE,
    WorkflowStepType.MAP,
    WorkflowStepType.VALIDATE,
    WorkflowStepType.CLEAN,
    WorkflowStepType.FINALIZE,
)

TERMINAL_SUCCESS: FrozenSet[str] = frozenset({
    WorkflowStepStatus.COMPLETED.value,
    WorkflowStepStatus.SKIPPED.value,
})

REUSABLE_STATUSES: FrozenSet[str] = frozenset({
    WorkflowStepStatus.COMPLETED.value,
    WorkflowStepStatus.SKIPPED.value,
})

ERROR_CODES = {
    WorkflowStepType.INSPECT: "INSPECT_EXECUTION_FAILED",
    WorkflowStepType.PREPARE: "PREPARE_EXECUTION_FAILED",
    WorkflowStepType.MAP: "MAP_EXECUTION_FAILED",
    WorkflowStepType.VALIDATE: "VALIDATE_EXECUTION_FAILED",
    WorkflowStepType.CLEAN: "CLEANING_EXECUTION_FAILED",
    WorkflowStepType.FINALIZE: "FINALIZE_EXECUTION_FAILED",
}

# Semantics:
# stale = result cannot currently be trusted (dependency/input changed)
# superseded = newer valid logical version replaced this result
MAX_ENGINE_ACTIONS = 20
