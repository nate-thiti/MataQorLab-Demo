"""Canonical setup step registry enforced by the Workflow Engine.

``STEP_REGISTRY`` is the authoritative product registry (Phase 4 / 4.5).

Legacy ``TOOL_HANDLERS`` / ``get_tool`` are compatibility views only.
Do **not** use them for new setup orchestration or future AI tool routing —
route through ``WorkflowEngine.execute_step`` / ``run_until_idle`` instead.
"""
from __future__ import annotations

import warnings
from typing import Any, Callable, Dict

from app.services.workflow.models import WorkflowStepType


class UnknownStepError(KeyError):
    def __init__(self, step_type: str):
        self.step_type = step_type
        super().__init__(f"UNKNOWN_STEP: {step_type}")


def _import_handlers() -> Dict[str, Callable[..., Any]]:
    from app.services.tools.clean_data import clean_data, run_clean_data
    from app.services.tools.finalize import finalize_data_setup
    from app.services.tools.inspect_source import inspect_source
    from app.services.tools.map_schema import map_schema
    from app.services.tools.prepare_data import prepare_data, run_prepare_data
    from app.services.tools.validate_data import validate_data

    return {
        "inspect_source": inspect_source,
        "prepare_data": prepare_data,
        "run_prepare_data": run_prepare_data,
        "clean_data": clean_data,
        "run_clean_data": run_clean_data,
        "map_schema": map_schema,
        "validate_data": validate_data,
        "finalize": finalize_data_setup,
    }


def _step_registry() -> Dict[str, Dict[str, Any]]:
    """Canonical step_type → handler metadata. Single source of truth."""
    handlers = _import_handlers()
    return {
        WorkflowStepType.INSPECT.value: {
            "tool_name": "inspect_source",
            "handler": handlers["inspect_source"],
            "requires_confirmation": False,
            "skippable": False,
        },
        WorkflowStepType.PREPARE.value: {
            "tool_name": "prepare_data",
            "handler": handlers["run_prepare_data"],
            "requires_confirmation": False,
            "skippable": False,
        },
        WorkflowStepType.MAP.value: {
            "tool_name": "map_schema",
            "handler": handlers["map_schema"],
            "requires_confirmation": False,
            "skippable": True,
        },
        WorkflowStepType.VALIDATE.value: {
            "tool_name": "validate_data",
            "handler": handlers["validate_data"],
            "requires_confirmation": False,
            "skippable": False,
        },
        WorkflowStepType.CLEAN.value: {
            "tool_name": "clean_data",
            "handler": handlers["run_clean_data"],
            "requires_confirmation": False,  # runtime policy may override
            "skippable": True,
        },
        WorkflowStepType.FINALIZE.value: {
            "tool_name": "finalize",
            "handler": handlers["finalize"],
            "requires_confirmation": False,
            "skippable": False,
        },
    }


def _legacy_tool_handlers() -> Dict[str, Callable[..., Any]]:
    """Compatibility view derived from STEP_REGISTRY (+ alias wrappers).

    Deprecated for product orchestration. Prefer STEP_REGISTRY / WorkflowEngine.
    """
    handlers = _import_handlers()
    # Keep alias names used by Phase 2 unit tests; derived from same imports.
    return dict(handlers)


def __getattr__(name: str):
    if name == "STEP_REGISTRY":
        return _step_registry()
    if name == "TOOL_HANDLERS":
        warnings.warn(
            "TOOL_HANDLERS is legacy; use STEP_REGISTRY / WorkflowEngine for "
            "setup orchestration. Direct tool lookup is test/compat only.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _legacy_tool_handlers()
    raise AttributeError(name)


def get_tool(name: str) -> Callable[..., Any]:
    """Legacy lookup by tool function name. Not for AI/product orchestration."""
    warnings.warn(
        "get_tool is legacy; route setup work through WorkflowEngine.execute_step",
        DeprecationWarning,
        stacklevel=2,
    )
    handler = _legacy_tool_handlers().get(name)
    if handler is None:
        raise KeyError(f"Unknown tool: {name}")
    return handler


def get_step_entry(step_type: str) -> Dict[str, Any]:
    entry = _step_registry().get(str(step_type))
    if entry is None:
        raise UnknownStepError(str(step_type))
    return entry


def resolve_step_type(step_or_tool: str) -> str:
    """Map step id or tool name to canonical step_type. Fail closed."""
    key = str(step_or_tool or "").strip()
    registry = _step_registry()
    if key in registry:
        return key
    for step_type, entry in registry.items():
        if entry.get("tool_name") == key:
            return step_type
    raise UnknownStepError(key)
