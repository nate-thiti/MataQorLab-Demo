"""Step runners used only through WorkflowEngine.execute_step.

Product data-setup must not import these runners (or raw tools) directly.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from app.services.data_setup import _safe_text
from app.services.dataset_loader import load_handle_from_storage
from app.services.etl_pipeline import normalize_recipe
from app.services.tools.clean_data import run_clean_data
from app.services.tools.finalize import finalize_data_setup
from app.services.tools.inspect_source import inspect_source
from app.services.tools.map_schema import map_schema
from app.services.tools.prepare_data import run_prepare_data
from app.services.tools.types import ToolResult
from app.services.tools.validate_data import validate_data
from app.services.workflow.artifacts import (
    load_cleaned_artifact,
    persist_cleaned_handle,
)
from app.services.workflow.models import WorkflowStepType
from app.services.workflow.state import get_latest_step


def session_mapping(session: Mapping[str, Any]) -> Dict[str, str]:
    recipe = normalize_recipe(session.get("cleaning_recipe") or {})
    mapping = {
        str(column): str(role).strip().lower()
        for column, role in (
            session.get("column_mapping") or recipe.get("column_mapping") or {}
        ).items()
        if str(role or "").strip()
    }
    return mapping


def dataset_key_from_context(
    context: Mapping[str, Any],
    session: Mapping[str, Any],
) -> str:
    key = _safe_text(context.get("dataset_key"), 500)
    if key:
        return key
    source_ref = session.get("source_ref") or {}
    return _safe_text(source_ref.get("file_name"), 500)


def run_inspect_step(
    *,
    user_id: str,
    session: Mapping[str, Any],
) -> ToolResult:
    source_ref = session.get("source_ref") or {}
    return inspect_source(
        user_id=user_id,
        source_type=str(session.get("source_type") or "file"),
        source_ref=source_ref,
        source_label=_safe_text(
            (session.get("scan_result") or {}).get("source_label"), 300
        ),
        existing_scan=session.get("scan_result") or None,
    )


def run_prepare_step(
    *,
    user_id: str,
    session_id: str,
    session: Mapping[str, Any],
) -> ToolResult:
    result, _handle = run_prepare_data(
        user_id=user_id,
        source_type=str(session.get("source_type") or "file"),
        source_ref=session.get("source_ref") or {},
        session_id=session_id,
        retain_handle=False,
    )
    return result


def run_map_step(*, session: Mapping[str, Any]) -> ToolResult:
    mapping = session_mapping(session)
    return map_schema(
        column_mapping=mapping,
        suggested_mapping=(session.get("scan_result") or {}).get("suggested_mapping"),
        columns=[
            str(col.get("name"))
            for col in ((session.get("scan_result") or {}).get("columns") or [])
            if col.get("name")
        ],
    )


def run_validate_step(*, session: Mapping[str, Any]) -> ToolResult:
    recipe = normalize_recipe(session.get("cleaning_recipe") or {})
    mapping = session_mapping(session)
    recipe["column_mapping"] = mapping
    scan = session.get("scan_result") or {}
    columns = [
        str(item.get("name"))
        for item in scan.get("columns") or []
        if isinstance(item, Mapping) and item.get("name")
    ]
    return validate_data(
        data_contract=recipe.get("data_contract"),
        column_mapping=mapping,
        columns=columns or list(mapping.keys()) or None,
        suggested_mapping=scan.get("suggested_mapping") or {},
    )


def run_clean_step(
    *,
    user_id: str,
    session_id: str,
    session: Mapping[str, Any],
    context: Dict[str, Any],
    client: Any | None = None,
) -> Tuple[ToolResult, Optional[Any]]:
    mapping = session_mapping(session)
    recipe = normalize_recipe(session.get("cleaning_recipe") or {})
    recipe["column_mapping"] = mapping
    cleaning_profile = (
        session.get("cleaning_profile")
        or recipe.get("cleaning_profile")
        or "standard"
    )
    dataset_key = dataset_key_from_context(context, session)
    if not dataset_key:
        return (
            ToolResult(
                tool="clean_data",
                status="failed",
                summary="dataset_key missing for clean",
            ),
            None,
        )

    # Resume from artifact when already available in context.
    artifact_key = str(context.get("cleaned_artifact_key") or "")
    if artifact_key:
        handle = load_cleaned_artifact(user_id, artifact_key)
        if handle is not None:
            context["cleaned_handle"] = handle
            return (
                ToolResult(
                    tool="clean_data",
                    status="completed",
                    summary="Reused cleaned artifact",
                    artifacts={
                        "cleaned_artifact_key": artifact_key,
                        "dataset_key": dataset_key,
                    },
                    metadata={"mode": "apply", "reused_artifact": True},
                ),
                handle,
            )

    source_handle = load_handle_from_storage(user_id, dataset_key, None)
    if source_handle is None:
        return (
            ToolResult(
                tool="clean_data",
                status="failed",
                summary="Unsupported tabular source",
            ),
            None,
        )
    result, handle = run_clean_data(
        mode="apply",
        handle=source_handle,
        mapping=mapping,
        cleaning_profile=cleaning_profile,
        recipe=recipe,
        retain_handle=True,
    )
    if result.status != "completed" or handle is None:
        return result, None
    prior = get_latest_step(session_id, WorkflowStepType.CLEAN, client=client) or {}
    version = int(prior.get("version") or 1)
    artifact_key = persist_cleaned_handle(
        user_id, session_id, handle, version=version
    )
    result.artifacts["cleaned_artifact_key"] = artifact_key
    result.artifacts["dataset_key"] = dataset_key
    context["cleaned_artifact_key"] = artifact_key
    context["cleaned_handle"] = handle
    context["dataset_key"] = dataset_key
    return result, handle


def run_finalize_step(
    *,
    user_id: str,
    session: Mapping[str, Any],
    context: Mapping[str, Any],
    client: Any | None = None,
) -> ToolResult:
    mapping = session_mapping(session)
    recipe = normalize_recipe(session.get("cleaning_recipe") or {})
    recipe["column_mapping"] = mapping
    dataset_key = dataset_key_from_context(context, session)
    return finalize_data_setup(
        user_id=user_id,
        session=session,
        dataset_key=dataset_key,
        recipe=recipe,
        cleaned_handle=context.get("cleaned_handle"),
        cleaned_artifact_key=context.get("cleaned_artifact_key") or None,
        client=client,
    )
