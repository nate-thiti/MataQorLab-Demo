"""inspect_source — lightweight non-destructive source inspection."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from app.services.data_setup import build_scan_result, load_setup_handle
from app.services.tools.types import ToolResult


def inspect_source(
    *,
    user_id: str,
    source_type: str,
    source_ref: Mapping[str, Any],
    source_label: Optional[str] = None,
    row_count: Optional[int] = None,
    row_count_exact: bool = False,
    existing_scan: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Load a bounded sample and return scan metadata.

    Does not clean, publish, analyze, or mark a session ready.
    Reuses ``load_setup_handle`` + ``build_scan_result``.
    """
    if isinstance(existing_scan, dict) and existing_scan.get("columns"):
        return ToolResult(
            tool="inspect_source",
            status="skipped",
            summary="Reused existing scan_result from session",
            artifacts={"scan_result": existing_scan},
            metadata={
                "rows": existing_scan.get("row_count"),
                "columns": existing_scan.get("column_count"),
                "source_type": existing_scan.get("source_type") or source_type,
                "reused": True,
            },
            suggested_next_actions=["prepare_data"],
        )

    handle = load_setup_handle(user_id, source_type, source_ref, sample_only=True)
    sample = handle.to_pandas(limit=200)
    label = (
        source_label
        or str(source_ref.get("file_name") or source_ref.get("table_name") or source_type)
    )
    scan = build_scan_result(
        sample.to_dict(orient="records"),
        source_type=source_type,
        source_label=label,
        row_count=row_count if row_count is not None else handle.row_count(),
        row_count_exact=row_count_exact,
    )
    findings = [
        {
            "type": "column_needs_review",
            "column": col.get("name"),
            "role": col.get("suggested_role") or None,
            "confidence": col.get("role_confidence"),
        }
        for col in (scan.get("columns") or [])
        if col.get("needs_review")
    ]
    return ToolResult(
        tool="inspect_source",
        status="completed",
        summary=(
            f"Inspected {scan.get('source_label')}: "
            f"{scan.get('row_count')} rows, {scan.get('column_count')} columns"
        ),
        findings=findings[:50],
        artifacts={
            "scan_result": scan,
            "source_fingerprint": scan.get("source_fingerprint"),
        },
        metadata={
            "rows": scan.get("row_count"),
            "columns": scan.get("column_count"),
            "sample_rows": scan.get("sample_rows"),
            "source_type": source_type,
            "suggested_domain": scan.get("suggested_domain"),
        },
        suggested_next_actions=["prepare_data", "map_schema"],
    )
