"""prepare_data — structural source readiness (no cleaning-profile rules)."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from app.services.data_setup import _materialize_source_handle, _safe_text, load_setup_handle
from app.services.dataset_engine import DatasetHandle
from app.services.dataset_loader import load_handle_from_storage
from app.services.tools.types import ToolResult


def prepare_data(
    *,
    user_id: str,
    source_type: str,
    source_ref: Mapping[str, Any],
    session_id: Optional[str] = None,
    dataset_key: Optional[str] = None,
) -> ToolResult:
    """Ensure a durable raw source identity exists for downstream tools.

    Ownership:
    - load full source
    - materialize non-file sources to a raw parquet snapshot
    - return dataset_key + shape metadata

    Does NOT apply cleaning profiles, mapping coercion, contract transforms,
    publish, or mark session ready.
    """
    result, _handle = run_prepare_data(
        user_id=user_id,
        source_type=source_type,
        source_ref=source_ref,
        session_id=session_id,
        dataset_key=dataset_key,
        retain_handle=False,
    )
    return result


def run_prepare_data(
    *,
    user_id: str,
    source_type: str,
    source_ref: Mapping[str, Any],
    session_id: Optional[str] = None,
    dataset_key: Optional[str] = None,
    retain_handle: bool = False,
) -> Tuple[ToolResult, Optional[DatasetHandle]]:
    resolved_key = _safe_text(dataset_key or source_ref.get("file_name"), 500)
    handle: Optional[DatasetHandle] = None

    if source_type == "file":
        if not resolved_key:
            return (
                ToolResult(
                    tool="prepare_data",
                    status="failed",
                    summary="Source file name is missing",
                ),
                None,
            )
        handle = load_handle_from_storage(user_id, resolved_key, None)
        if handle is None:
            return (
                ToolResult(
                    tool="prepare_data",
                    status="failed",
                    summary="Unsupported tabular file",
                ),
                None,
            )
    else:
        handle = load_setup_handle(user_id, source_type, source_ref, sample_only=False)
        if not session_id:
            return (
                ToolResult(
                    tool="prepare_data",
                    status="failed",
                    summary="session_id is required to materialize non-file sources",
                ),
                None,
            )
        resolved_key = _materialize_source_handle(user_id, session_id, handle)

    rows = handle.row_count()
    cols = len(handle.column_names())
    result = ToolResult(
        tool="prepare_data",
        status="completed",
        summary=f"Source prepared for processing ({rows} rows, {cols} columns)",
        artifacts={
            "dataset_key": resolved_key,
            "materialized": source_type != "file",
        },
        metadata={
            "rows": rows,
            "columns": cols,
            "source_type": source_type,
        },
        suggested_next_actions=["map_schema", "clean_data"],
    )
    return result, (handle if retain_handle else None)
