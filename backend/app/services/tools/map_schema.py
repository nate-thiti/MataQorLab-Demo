"""map_schema — normalize/infer semantic roles for setup sessions."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from app.services.domain_analytics import infer_semantic_roles
from app.services.tools.types import ToolResult

# Setup session column_mapping is authoritative for Phase 2.
# column_mappings_memory is a parallel store and is intentionally unused here.


def map_schema(
    *,
    column_mapping: Optional[Mapping[str, Any]] = None,
    suggested_mapping: Optional[Mapping[str, Any]] = None,
    columns: Optional[List[str]] = None,
    sample_rows: Optional[List[Dict[str, Any]]] = None,
) -> ToolResult:
    """Normalize setup mapping and report unresolved columns.

    Does not persist mappings, ask the user, or unify chat mapping memory.
    """
    source_mapping = {
        str(column): str(role).strip().lower()
        for column, role in (column_mapping or {}).items()
        if str(role or "").strip()
    }
    suggestions = {
        str(column): str(role).strip().lower()
        for column, role in (suggested_mapping or {}).items()
        if str(role or "").strip()
    }

    inferred: Dict[str, str] = {}
    if sample_rows and not source_mapping and not suggestions:
        frame = pd.DataFrame(sample_rows)
        role_to_column = infer_semantic_roles(frame)
        inferred = {str(column): role for role, column in role_to_column.items()}

    effective = dict(suggestions)
    effective.update(inferred)
    effective.update(source_mapping)

    available = list(columns or effective.keys())
    if sample_rows and not available:
        available = [str(c) for c in pd.DataFrame(sample_rows).columns]

    unresolved = [name for name in available if name not in effective or not effective.get(name)]
    findings = [
        {"column": name, "role": None, "confidence": None, "status": "unresolved"}
        for name in unresolved[:50]
    ]
    for column, role in list(effective.items())[:100]:
        findings.append({
            "column": column,
            "role": role,
            "confidence": 1.0 if column in source_mapping else 0.86,
            "status": "confirmed" if column in source_mapping else "suggested",
        })

    return ToolResult(
        tool="map_schema",
        status="completed",
        summary=(
            f"Mapped {len(effective)} columns"
            + (f"; {len(unresolved)} unresolved" if unresolved else "")
        ),
        findings=findings,
        artifacts={
            "column_mapping": effective,
            # Explicit: setup session mapping is source of truth when provided.
            "mapping_source": (
                "session" if source_mapping else "suggested" if suggestions else "inferred"
            ),
        },
        metadata={
            "mapped": len(effective),
            "unresolved": len(unresolved),
            "confirmed": len(source_mapping),
        },
        suggested_next_actions=["validate_data", "clean_data"],
        warnings=(
            [{"type": "unresolved_columns", "count": len(unresolved)}]
            if unresolved
            else []
        ),
    )
