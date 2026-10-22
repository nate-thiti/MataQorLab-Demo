"""Allowed workflow step status transitions (Phase 4)."""
from __future__ import annotations

from typing import Dict, Set

from app.services.workflow.models import WorkflowStepStatus

# completed → running is NOT allowed; use new attempt/version via begin_step.
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    WorkflowStepStatus.PENDING.value: {
        WorkflowStepStatus.READY.value,
        WorkflowStepStatus.RUNNING.value,
        WorkflowStepStatus.SKIPPED.value,
    },
    WorkflowStepStatus.READY.value: {
        WorkflowStepStatus.RUNNING.value,
        WorkflowStepStatus.AWAITING_USER.value,
        WorkflowStepStatus.SKIPPED.value,
        WorkflowStepStatus.STALE.value,
    },
    WorkflowStepStatus.RUNNING.value: {
        WorkflowStepStatus.COMPLETED.value,
        WorkflowStepStatus.FAILED.value,
        WorkflowStepStatus.AWAITING_USER.value,
        WorkflowStepStatus.SKIPPED.value,
    },
    WorkflowStepStatus.AWAITING_USER.value: {
        WorkflowStepStatus.READY.value,
        WorkflowStepStatus.RUNNING.value,
        WorkflowStepStatus.FAILED.value,
        WorkflowStepStatus.SKIPPED.value,
        WorkflowStepStatus.STALE.value,
        WorkflowStepStatus.SUPERSEDED.value,
    },
    WorkflowStepStatus.FAILED.value: {
        WorkflowStepStatus.READY.value,
        WorkflowStepStatus.RUNNING.value,  # retry attempt via begin_step
        WorkflowStepStatus.SUPERSEDED.value,
    },
    WorkflowStepStatus.COMPLETED.value: {
        WorkflowStepStatus.STALE.value,
        WorkflowStepStatus.SUPERSEDED.value,
    },
    WorkflowStepStatus.SKIPPED.value: {
        WorkflowStepStatus.STALE.value,
        WorkflowStepStatus.SUPERSEDED.value,
        WorkflowStepStatus.READY.value,
    },
    WorkflowStepStatus.STALE.value: {
        WorkflowStepStatus.READY.value,
        WorkflowStepStatus.RUNNING.value,  # new attempt/version
        WorkflowStepStatus.SUPERSEDED.value,
    },
    WorkflowStepStatus.SUPERSEDED.value: set(),
}


class InvalidTransitionError(ValueError):
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"INVALID_TRANSITION: {from_status} → {to_status}"
        )


def can_transition(from_status: str | None, to_status: str) -> bool:
    current = str(from_status or WorkflowStepStatus.PENDING.value)
    target = str(to_status)
    if current == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(from_status: str | None, to_status: str) -> None:
    if not can_transition(from_status, to_status):
        raise InvalidTransitionError(str(from_status or "pending"), str(to_status))
