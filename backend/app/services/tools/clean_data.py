"""clean_data — cleaning-profile rules (preview + full apply)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.services.data_cleaning import clean_dataframe
from app.services.data_setup import SETUP_PROFILES, preview_setup_rows
from app.services.dataset_engine import DatasetHandle
from app.services.etl_pipeline import normalize_recipe
from app.services.tools.types import ToolResult


def clean_data(
    *,
    mode: str = "preview",
    rows: Optional[Any] = None,
    handle: Optional[DatasetHandle] = None,
    mapping: Optional[Mapping[str, str]] = None,
    cleaning_profile: str = "standard",
    recipe: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Apply cleaning profile rules via the shared cleaning engines.

    mode:
      - preview: bounded sample path (``preview_setup_rows`` → ``clean_dataframe``)
      - apply: full ``DatasetHandle.apply_standard_clean``

    Does not publish datasets, mark sessions ready, or run analysis.
    """
    result, _handle = run_clean_data(
        mode=mode,
        rows=rows,
        handle=handle,
        mapping=mapping,
        cleaning_profile=cleaning_profile,
        recipe=recipe,
        retain_handle=False,
    )
    return result


def run_clean_data(
    *,
    mode: str = "preview",
    rows: Optional[Any] = None,
    handle: Optional[DatasetHandle] = None,
    mapping: Optional[Mapping[str, str]] = None,
    cleaning_profile: str = "standard",
    recipe: Optional[Dict[str, Any]] = None,
    retain_handle: bool = False,
) -> Tuple[ToolResult, Optional[DatasetHandle]]:
    profile = cleaning_profile if cleaning_profile in SETUP_PROFILES else "standard"
    column_mapping = {
        str(column): str(role).strip().lower()
        for column, role in (mapping or {}).items()
        if str(role or "").strip()
    }
    normalized = normalize_recipe({
        **(recipe or {}),
        "cleaning_profile": profile,
        "column_mapping": column_mapping or (recipe or {}).get("column_mapping") or {},
    })
    column_mapping = normalized.get("column_mapping") or column_mapping

    if mode == "preview":
        if rows is None:
            return (
                ToolResult(
                    tool="clean_data",
                    status="failed",
                    summary="preview mode requires sample rows",
                ),
                None,
            )
        preview = preview_setup_rows(
            rows,
            mapping=column_mapping,
            cleaning_profile=profile,
            recipe=normalized,
        )
        findings = _findings_from_report(preview.get("cleaning_report") or preview)
        for item in preview.get("invalid_date_issues") or []:
            findings.append({
                "type": "invalid_dates",
                "column": item.get("column"),
                "count": item.get("count"),
            })
        return (
            ToolResult(
                tool="clean_data",
                status="completed",
                summary=(
                    f"Cleaning preview: {preview.get('rows_before')} → "
                    f"{preview.get('rows_after')} rows"
                ),
                findings=findings,
                artifacts={
                    "preview_result": preview,
                    "cleaning_profile": profile,
                },
                metadata={
                    "mode": "preview",
                    "rows_before": preview.get("rows_before"),
                    "rows_after": preview.get("rows_after"),
                    "cleaning_profile": profile,
                },
                suggested_next_actions=["validate_data", "map_schema"],
            ),
            None,
        )

    if mode != "apply":
        return (
            ToolResult(
                tool="clean_data",
                status="failed",
                summary=f"Unsupported clean_data mode: {mode}",
            ),
            None,
        )

    if handle is None:
        return (
            ToolResult(
                tool="clean_data",
                status="failed",
                summary="apply mode requires a DatasetHandle",
            ),
            None,
        )

    # Shared rule path with preview: apply_standard_clean → clean_dataframe /
    # clean_handle_duckdb (+ recipe apply). Preview uses clean_dataframe directly
    # via preview_setup_rows; apply uses the same engines through the handle API.
    _notes, cleaned = handle.apply_standard_clean(
        column_mapping, profile, normalized
    )
    report = dict(cleaned._cleaning_report or {})
    findings = _findings_from_report(report)
    result = ToolResult(
        tool="clean_data",
        status="completed",
        summary=(
            f"Cleaning completed: {report.get('rows_before')} → "
            f"{report.get('rows_after')} rows"
        ),
        findings=findings,
        artifacts={
            "cleaning_profile": profile,
            "cleaning_report": {
                key: report.get(key)
                for key in (
                    "profile",
                    "engine",
                    "rows_before",
                    "rows_after",
                    "dropped_empty_rows",
                    "dropped_duplicates",
                    "dropped_columns",
                    "invalid_dates",
                    "quality_score",
                )
                if key in report
            },
        },
        metadata={
            "mode": "apply",
            "rows_before": report.get("rows_before"),
            "rows_after": report.get("rows_after") or cleaned.row_count(),
            "columns": len(cleaned.column_names()),
            "cleaning_profile": profile,
            "engine": report.get("engine"),
        },
        suggested_next_actions=["validate_data", "finalize"],
    )
    return result, (cleaned if retain_handle else None)


def _findings_from_report(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    duplicates = int(report.get("dropped_duplicates") or 0)
    if duplicates:
        findings.append({"type": "duplicate_rows_removed", "count": duplicates})
    empty_rows = int(report.get("dropped_empty_rows") or 0)
    if empty_rows:
        findings.append({"type": "empty_rows_removed", "count": empty_rows})
    for column, count in (report.get("invalid_dates") or {}).items():
        findings.append({
            "type": "invalid_dates",
            "column": str(column),
            "count": int(count or 0),
        })
    for column in report.get("dropped_columns") or []:
        findings.append({"type": "empty_column_removed", "column": str(column)})
    return findings


# Re-export for tests asserting shared preview path uses clean_dataframe.
_SHARED_PREVIEW_ENGINE = clean_dataframe
