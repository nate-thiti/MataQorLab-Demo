"""
Unified analytics entry — used by chat, Excel export, and legacy normalize API.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from app.services.analytics_cache import base_cache_key, get_base_analytics, set_base_analytics
from app.services.dataset_engine import DatasetHandle
from app.services.domain_analytics import compute_domain_kpis_duckdb, infer_dataset_type
from app.services.duckdb_extended_analytics import append_extended_duckdb_analytics


def _should_cache(file_name: Optional[str], connection_id: Optional[str]) -> bool:
    # Live API/SQL connections have no immutable source version. Correctness is
    # more important than reusing a potentially stale answer.
    return bool(file_name and not connection_id)


def calculate_analytics_for_handle(
    handle: DatasetHandle,
    column_mapping: Optional[Dict[str, str]] = None,
    user_id: Optional[str] = None,
    file_attachment_name: Optional[str] = None,
    connection_id: Optional[str] = None,
    cleaning_profile: str = "standard",
    pandas_calculator=None,
) -> Dict[str, Any]:
    """
    Single analytics path for small (Pandas) and large (DuckDB) datasets.
    pandas_calculator: callable(df, mapping) -> dict from ChatService.analytics.calculate
    """
    mapping = column_mapping or {}
    profile = (cleaning_profile or "standard").strip().lower()
    validation_notes = []
    if not getattr(handle, "_prepared_for_analysis", False):
        validation_notes, handle = handle.prepare_for_analysis(mapping, profile)
    mapping = getattr(handle, "_effective_mapping", None) or mapping
    provenance = {
        "dataset_version_id": getattr(handle, "_dataset_version_id", None),
        "source_fingerprint": getattr(handle, "_source_fingerprint", None),
        "contract_hash": getattr(handle, "_contract_hash", None),
        "recipe_hash": getattr(handle, "_recipe_hash", None),
    }
    cache_key = None
    if user_id and _should_cache(file_attachment_name, connection_id):
        cache_key = base_cache_key(
            user_id, file_attachment_name, mapping, connection_id, profile, provenance
        )
        cached = get_base_analytics(cache_key)
        if cached:
            return dict(cached)

    if handle.is_large:
        summary_df = handle.summarize_df()
        column_profile = handle.profile_columns(summary_df)
        lines = handle.duckdb_summarize_stats(summary_df)
        role_to_col = handle.infer_roles_from_sample(mapping)
        lines.extend(append_extended_duckdb_analytics(handle, role_to_col, summary_df))
        domain_kpis = compute_domain_kpis_duckdb(handle, role_to_col)
        if domain_kpis:
            lines.append("\n=== Domain-Specific KPIs (full dataset, DuckDB) ===")
            lines.extend(domain_kpis)
        suggested_type = infer_dataset_type(role_to_col) if role_to_col else "general_business_data"
        result = {
            "formatted_notes": "\n".join(lines),
            "column_profile": column_profile,
            "raw_metrics": lines,
            "detected_roles": role_to_col,
            "suggested_dataset_type": suggested_type,
            "is_large": True,
        }
    else:
        if pandas_calculator is None:
            raise ValueError("pandas_calculator required for small datasets")
        result = pandas_calculator(handle.to_pandas(), mapping)
        result["column_profile"] = handle.profile_columns()
        result["is_large"] = False

    if validation_notes:
        prefix = "=== Data Validation Notes ===\n" + "\n".join(validation_notes)
        result["formatted_notes"] = prefix + "\n\n" + result.get("formatted_notes", "")
    cleaning_report = getattr(handle, "_cleaning_report", None) or {}
    if cleaning_report:
        result["cleaning_report"] = dict(cleaning_report)
        result["data_quality_score"] = cleaning_report.get("quality_score")
        result["schema_profile"] = cleaning_report.get("schema_profile", {})
        result["lineage"] = cleaning_report.get("lineage", {})
    if cache_key:
        set_base_analytics(cache_key, result)
    return result


def calculate_analytics_from_dataframe(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    user_id: Optional[str] = None,
    file_name: Optional[str] = None,
    cleaning_profile: str = "standard",
    pandas_calculator=None,
) -> Dict[str, Any]:
    handle = DatasetHandle.from_dataframe(df)
    return calculate_analytics_for_handle(
        handle,
        column_mapping,
        user_id=user_id,
        file_attachment_name=file_name,
        cleaning_profile=cleaning_profile,
        pandas_calculator=pandas_calculator,
    )


def calculate_analytics_from_bytes(
    file_bytes: bytes,
    file_name: str,
    column_mapping: Optional[Dict[str, str]] = None,
    user_id: Optional[str] = None,
    cleaning_profile: str = "standard",
    pandas_calculator=None,
) -> Dict[str, Any]:
    target_cols = list(column_mapping.keys()) if column_mapping else None
    handle = DatasetHandle.from_bytes(file_bytes, file_name, target_cols)
    if handle is None:
        raise ValueError(f"Unsupported or unreadable file: {file_name}")
    notes, handle = handle.prepare_for_analysis(column_mapping, cleaning_profile)
    result = calculate_analytics_for_handle(
        handle,
        column_mapping,
        user_id=user_id,
        file_attachment_name=file_name,
        cleaning_profile=cleaning_profile,
        pandas_calculator=pandas_calculator,
    )
    if notes and not str(result.get("formatted_notes", "")).startswith("=== Data Validation Notes ==="):
        prefix = "=== Data Validation Notes ===\n" + "\n".join(notes)
        result["formatted_notes"] = prefix + "\n\n" + result.get("formatted_notes", "")
    return result


def legacy_summary_from_analytics(analytics: Dict[str, Any]) -> Dict[str, Any]:
    """Shape-compatible summary for /api/normalize consumers."""
    notes = analytics.get("formatted_notes") or ""
    return {
        "summary": {
            "total_sales": 0,
            "total_items": 0,
            "avg_transaction": 0,
            "analytics_notes": notes[:4000],
        },
        "formatted_notes": notes,
        "detected_roles": analytics.get("detected_roles", {}),
        "suggested_dataset_type": analytics.get("suggested_dataset_type"),
    }
