"""Centralized step dependency graph (Phase 4).

Logical graph (not a fixed list index):

```text
inspect
   ↓
prepare
  ↙   ↘
clean  map
  \\    /
   validate
      ↓
   finalize
```

Runtime planning still walks a compatibility sequence
(inspect → prepare → map → validate → clean → finalize) because validate
does not require clean, and clean does not require validate. Both must be
valid before finalize.
"""
from __future__ import annotations

from typing import Dict, Set

from app.services.workflow.models import WorkflowStepType

STEP_DEPENDENCIES: Dict[str, Set[str]] = {
    WorkflowStepType.INSPECT.value: set(),
    WorkflowStepType.PREPARE.value: {WorkflowStepType.INSPECT.value},
    # Mapping can use scan metadata; prepare is not a hard dependency.
    WorkflowStepType.MAP.value: {WorkflowStepType.INSPECT.value},
    WorkflowStepType.CLEAN.value: {WorkflowStepType.PREPARE.value},
    WorkflowStepType.VALIDATE.value: {
        WorkflowStepType.PREPARE.value,
        WorkflowStepType.MAP.value,
    },
    WorkflowStepType.FINALIZE.value: {
        WorkflowStepType.CLEAN.value,
        WorkflowStepType.VALIDATE.value,
    },
}


def _build_dependents(deps: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    result: Dict[str, Set[str]] = {step: set() for step in deps}
    for step, requires in deps.items():
        for parent in requires:
            result.setdefault(parent, set()).add(step)
    return result


STEP_DEPENDENTS: Dict[str, Set[str]] = _build_dependents(STEP_DEPENDENCIES)

# When this step's inputs change, which dependents become stale.
INVALIDATION_TARGETS: Dict[str, Set[str]] = {
    WorkflowStepType.INSPECT.value: {
        WorkflowStepType.PREPARE.value,
        WorkflowStepType.MAP.value,
        WorkflowStepType.CLEAN.value,
        WorkflowStepType.VALIDATE.value,
        WorkflowStepType.FINALIZE.value,
    },
    WorkflowStepType.PREPARE.value: {
        WorkflowStepType.CLEAN.value,
        WorkflowStepType.VALIDATE.value,
        WorkflowStepType.FINALIZE.value,
    },
    WorkflowStepType.MAP.value: {
        WorkflowStepType.VALIDATE.value,
        WorkflowStepType.FINALIZE.value,
        # clean uses mapping for type coercion hints but artifact can remain;
        # finalize reapplies mapping coercion — do not force clean stale.
    },
    WorkflowStepType.CLEAN.value: {
        WorkflowStepType.FINALIZE.value,
    },
    WorkflowStepType.VALIDATE.value: {
        WorkflowStepType.FINALIZE.value,
    },
    WorkflowStepType.FINALIZE.value: set(),
}


def requires(step_type: str) -> Set[str]:
    return set(STEP_DEPENDENCIES.get(str(step_type), set()))


def dependents(step_type: str) -> Set[str]:
    return set(STEP_DEPENDENTS.get(str(step_type), set()))


def invalidation_targets(step_type: str) -> Set[str]:
    return set(INVALIDATION_TARGETS.get(str(step_type), set()))
