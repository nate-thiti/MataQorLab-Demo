"""Phase 2 independent setup tool wrappers."""

from app.services.tools.clean_data import clean_data, run_clean_data
from app.services.tools.inspect_source import inspect_source
from app.services.tools.map_schema import map_schema
from app.services.tools.prepare_data import prepare_data, run_prepare_data
from app.services.tools.registry import get_tool
from app.services.tools.types import ToolResult
from app.services.tools.validate_data import validate_data

__all__ = [
    "ToolResult",
    "TOOL_HANDLERS",
    "STEP_REGISTRY",
    "get_tool",
    "inspect_source",
    "prepare_data",
    "run_prepare_data",
    "clean_data",
    "run_clean_data",
    "map_schema",
    "validate_data",
    "finalize_data_setup",
]


def __getattr__(name: str):
    if name in {"TOOL_HANDLERS", "STEP_REGISTRY"}:
        from app.services.tools import registry as tool_registry

        return getattr(tool_registry, name)
    if name == "finalize_data_setup":
        from app.services.tools.finalize import finalize_data_setup

        return finalize_data_setup
    raise AttributeError(name)
