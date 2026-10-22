"""
Token-efficient dataset metadata for LLM context (no raw row previews).
"""
from typing import Optional

from app.services.dataset_engine import DatasetHandle


def build_dataset_metadata(
    row_count: int,
    col_count: int,
    column_profile: str,
    quality_notes: Optional[str] = None,
    sql_executed: Optional[str] = None,
    is_large: bool = False,
    extra_notes: Optional[str] = None,
) -> str:
    engine = "DuckDB (full dataset, SQL analytics)" if is_large else "Pandas (full dataset)"
    lines = [
        f"Rows: {row_count:,} | Columns: {col_count}",
        f"Analytics engine: {engine}",
        "Raw row preview: omitted — use <calculated_metrics> and <column_profile> for full-dataset stats.",
    ]
    if sql_executed:
        lines.append(f"SQL executed: {sql_executed}")
    if quality_notes:
        lines.append(f"Quality notes: {quality_notes}")
    if extra_notes:
        lines.append(extra_notes)
    if column_profile:
        lines.append(f"\nColumn profile (full dataset):\n{column_profile}")
    return "\n".join(lines)


def metadata_from_handle(
    handle: DatasetHandle,
    quality_notes: Optional[str] = None,
    sql_executed: Optional[str] = None,
    extra_notes: Optional[str] = None,
) -> str:
    profile = ""
    try:
        profile = handle.profile_columns()
    except Exception as e:
        print(f"metadata_from_handle profile failed: {e}")
    return build_dataset_metadata(
        row_count=handle.row_count(),
        col_count=len(handle.column_names()),
        column_profile=profile,
        quality_notes=quality_notes,
        sql_executed=sql_executed,
        is_large=handle.is_large,
        extra_notes=extra_notes,
    )
