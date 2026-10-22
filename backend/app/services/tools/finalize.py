"""finalize_data_setup — publish ownership (recipe run + catalog + ready).

prepare_data / clean_data must not call this. Only the compatibility sequencer
(or an explicit finalize call) publishes dataset versions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from app.core.supabase import get_supabase_client
from app.services.data_setup import _safe_text
from app.services.dataset_catalog import register_completed_dataset_version
from app.services.dataset_engine import DatasetHandle
from app.services.dataset_loader import load_handle_from_storage
from app.services.etl_execution import (
    EtlExecutionError,
    create_etl_run,
    publish_transformed_handle,
)
from app.services.etl_pipeline import (
    effective_mapping_for_contract,
    normalize_data_contract,
    normalize_recipe,
    recipe_hash,
    validate_data_contract,
)
from app.services.semantic_mapping_gate import (
    evaluate_semantic_mapping_gate,
    scan_columns,
    suggested_mapping_from_scan,
)
from app.services.tools.types import ToolResult
from app.services.workflow.artifacts import load_cleaned_artifact


def apply_post_clean_semantics(
    handle: DatasetHandle,
    *,
    mapping: Mapping[str, str],
    recipe: Dict[str, Any],
) -> DatasetHandle:
    """Apply mapping coercion + business contract after cleaning.

    These are not cleaning-profile rules and are not owned by clean_data.
    """
    contract = normalize_data_contract(recipe.get("data_contract"))
    effective = effective_mapping_for_contract(mapping, contract)
    _notes, handle = handle.apply_mapping_clean(dict(mapping or {}))
    _notes, handle = handle.apply_business_contract(contract, effective)
    handle._prepared_for_analysis = True
    handle._effective_mapping = effective
    handle._data_contract = contract
    return handle


def finalize_data_setup(
    *,
    user_id: str,
    session: Mapping[str, Any],
    dataset_key: str,
    recipe: Dict[str, Any],
    cleaned_handle: Optional[DatasetHandle] = None,
    cleaned_artifact_key: Optional[str] = None,
    client: Any | None = None,
) -> ToolResult:
    """Persist recipe, publish transformed output, register version, mark ready.

    If ``cleaned_handle`` is provided, cleaning is assumed already applied by
    ``clean_data`` and will not be re-run. Mapping coercion + business contract
    still apply once via ``apply_post_clean_semantics``.

    Idempotent when the session is already ``ready`` or already has a published
    ``output_file`` + ``dataset_version_id`` for this setup.
    """
    client = client or get_supabase_client()
    session_id = str(session.get("id") or "")

    # Refresh session for duplicate-dispatch safety.
    fresh = (
        client.table("data_setup_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    current = (fresh.data or [dict(session)])[0]
    source_type = str(current.get("source_type") or "file")
    source_ref = current.get("source_ref") or {}
    normalized = normalize_recipe(recipe)
    mapping = {
        str(column): str(role).strip().lower()
        for column, role in (normalized.get("column_mapping") or {}).items()
        if str(role or "").strip()
    }
    scan = current.get("scan_result") or {}
    mapping_gate = evaluate_semantic_mapping_gate(
        mapping=mapping,
        data_contract=normalized.get("data_contract") or {},
        columns=scan_columns(scan) or list(mapping),
        suggested_mapping=suggested_mapping_from_scan(scan),
        require_confirmation=True,
    )
    if not mapping_gate["ready"]:
        return ToolResult(
            tool="finalize",
            status="awaiting_user",
            summary="Semantic mapping must be completed and confirmed before analysis.",
            findings=[{"severity": "error", **item} for item in mapping_gate["issues"]],
            artifacts={"semantic_mapping_gate": mapping_gate},
            metadata={"semantic_mapping_ready": False},
            suggested_next_actions=["map_schema", "ask_user"],
        )
    if current.get("status") == "ready" and current.get("output_file"):
        return ToolResult(
            tool="finalize",
            status="completed",
            summary="Setup already finalized; reused existing publish",
            artifacts={
                "recipe_id": current.get("recipe_id"),
                "etl_run_id": current.get("run_id"),
                "output_file": current.get("output_file"),
                "output_dataset_key": current.get("output_dataset_key"),
                "dataset_version_id": current.get("dataset_version_id"),
                "recipe_hash": current.get("recipe_hash"),
                "contract_hash": current.get("contract_hash"),
                "reused": True,
            },
            metadata={"rows": None, "idempotent": True, "semantic_mapping_ready": True},
            suggested_next_actions=["analyze_data"],
        )
    normalized_recipe_hash = recipe_hash(normalized)
    contract_hash = hashlib.sha256(
        json.dumps(
            normalized.get("data_contract") or {},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    recipe_id = current.get("recipe_id")
    if not recipe_id:
        existing = (
            client.table("etl_recipes")
            .select("version")
            .eq("user_id", user_id)
            .eq("dataset_key", dataset_key)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        version = int(existing.data[0]["version"]) + 1 if existing.data else 1
        saved = client.table("etl_recipes").insert({
            "user_id": user_id,
            "dataset_key": dataset_key,
            "name": (
                f"{_safe_text((current.get('scan_result') or {}).get('source_label'), 100) or 'Dataset'} setup"
            ),
            "version": version,
            "recipe": normalized,
            "recipe_hash": normalized_recipe_hash,
            "is_active": True,
        }).execute()
        recipe_id = (saved.data or [{}])[0].get("id")
        if not recipe_id:
            return ToolResult(
                tool="finalize",
                status="failed",
                summary="Could not save the approved ETL recipe",
            )
        client.table("data_setup_sessions").update({
            "recipe_id": recipe_id,
            "processing_progress": {"percent": 70, "stage": "finalizing"},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).eq("user_id", user_id).execute()
    else:
        client.table("data_setup_sessions").update({
            "processing_progress": {"percent": 70, "stage": "finalizing"},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).eq("user_id", user_id).execute()

    # If a prior finalize partially published, reuse without creating a second version.
    if current.get("output_file") and current.get("dataset_version_id"):
        ready_payload = {
            "status": "ready",
            "current_step": "ready",
            "recipe_hash": current.get("recipe_hash") or normalized_recipe_hash,
            "contract_hash": current.get("contract_hash") or contract_hash,
            "processing_progress": {"percent": 100, "stage": "ready"},
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("data_setup_sessions").update(ready_payload).eq(
            "id", session_id
        ).eq("user_id", user_id).execute()
        return ToolResult(
            tool="finalize",
            status="completed",
            summary="Reused partially published setup artifacts",
            artifacts={
                "recipe_id": recipe_id,
                "etl_run_id": current.get("run_id"),
                "output_file": current.get("output_file"),
                "output_dataset_key": current.get("output_dataset_key"),
                "dataset_version_id": current.get("dataset_version_id"),
                "recipe_hash": ready_payload["recipe_hash"],
                "contract_hash": ready_payload["contract_hash"],
                "reused": True,
            },
            metadata={"idempotent": True},
            suggested_next_actions=["analyze_data"],
        )

    stable_output_key = f"etl:recipe:{recipe_id}"
    run_id = current.get("run_id")
    if not run_id:
        run_id = create_etl_run(
            client,
            user_id=user_id,
            recipe_id=recipe_id,
            dataset_key=dataset_key,
            output_dataset_key=stable_output_key,
            recipe=normalized,
            trigger_kind="data_setup",
        )
        client.table("data_setup_sessions").update({
            "run_id": run_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).eq("user_id", user_id).execute()

    try:
        handle = cleaned_handle
        if handle is None and cleaned_artifact_key:
            handle = load_cleaned_artifact(user_id, cleaned_artifact_key)
        if handle is None:
            handle = load_handle_from_storage(user_id, dataset_key, None)
            if handle is None:
                raise EtlExecutionError("Unsupported tabular source")
            profile = normalized.get("cleaning_profile") or "standard"
            _notes, handle = handle.prepare_for_analysis(mapping, profile, normalized)
        else:
            handle = apply_post_clean_semantics(
                handle, mapping=mapping, recipe=normalized
            )

        contract_readiness = validate_data_contract(
            normalized.get("data_contract"),
            mapping,
            handle.column_names(),
        )
        if (
            (normalized.get("data_contract") or {}).get("enforcement_mode") == "strict"
            and contract_readiness["status"] != "ready"
        ):
            missing = ", ".join(contract_readiness.get("missing") or [])
            raise EtlExecutionError(
                f"Data contract is not ready for strict execution: {missing or 'validation failed'}"
            )

        publish = publish_transformed_handle(
            client,
            user_id=user_id,
            handle=handle,
            run_id=run_id,
            recipe=normalized,
            dataset_key=dataset_key,
            output_dataset_key=stable_output_key,
            output_name=_safe_text(
                (current.get("scan_result") or {}).get("source_label"), 100
            ),
            contract_readiness=contract_readiness,
            source_dataset_key=dataset_key,
        )
    except Exception as exc:
        if run_id:
            client.table("etl_pipeline_runs").update({
                "status": "failed",
                "error_message": str(exc)[:1000],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).eq("user_id", user_id).execute()
        raise

    dataset_version = register_completed_dataset_version(
        client,
        user_id=user_id,
        source_type=source_type,
        source_ref=dict(source_ref),
        display_name=(
            _safe_text((current.get("scan_result") or {}).get("source_label"), 500)
            or publish.get("dataset_key")
        ),
        source_fingerprint=current.get("source_fingerprint"),
        recipe_hash=normalized_recipe_hash,
        contract_hash=contract_hash,
        recipe_id=recipe_id,
        run_id=publish.get("run_id"),
        data_setup_session_id=session_id,
        output_dataset_key=publish.get("dataset_key"),
        output_file=publish.get("output_file"),
        output_version=publish.get("output_version"),
        lineage={
            "trigger_kind": "data_setup",
            "source_ref": source_ref,
            "materialized_prepared": True,
            "approved_by": current.get("approved_by"),
            "approved_at": current.get("approved_at"),
            "phase2_tools": True,
            "phase3_workflow_steps": True,
        },
    )
    if dataset_version and (current.get("workspace_id") or current.get("organization_id")):
        tenancy_payload = {
            "organization_id": current.get("organization_id"),
            "workspace_id": current.get("workspace_id"),
        }
        try:
            client.table("dataset_versions").update(tenancy_payload).eq(
                "id", dataset_version["id"]
            ).eq("user_id", user_id).execute()
            if dataset_version.get("catalog_id"):
                client.table("dataset_catalog").update(tenancy_payload).eq(
                    "id", dataset_version["catalog_id"]
                ).eq("user_id", user_id).execute()
        except Exception as exc:
            if not any(code in str(exc) for code in ("PGRST205", "42703")):
                raise

    ready_payload: Dict[str, Any] = {
        "status": "ready",
        "current_step": "ready",
        "run_id": publish.get("run_id"),
        "recipe_hash": normalized_recipe_hash,
        "contract_hash": contract_hash,
        "output_dataset_key": publish.get("dataset_key"),
        "output_file": publish.get("output_file"),
        "processing_progress": {"percent": 100, "stage": "ready"},
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "next_action": None,
        "last_failed_step": None,
    }
    if dataset_version:
        ready_payload["dataset_version_id"] = dataset_version.get("id")
    try:
        client.table("data_setup_sessions").update(ready_payload).eq(
            "id", session_id
        ).eq("user_id", user_id).execute()
    except Exception as exc:
        # Migration may not have next_action columns yet.
        if any(code in str(exc) for code in ("PGRST204", "42703")):
            ready_payload.pop("next_action", None)
            ready_payload.pop("last_failed_step", None)
            client.table("data_setup_sessions").update(ready_payload).eq(
                "id", session_id
            ).eq("user_id", user_id).execute()
        else:
            raise

    return ToolResult(
        tool="finalize",
        status="completed",
        summary="Dataset published and setup session marked ready",
        artifacts={
            "recipe_id": recipe_id,
            "etl_run_id": publish.get("run_id"),
            "output_file": publish.get("output_file"),
            "output_dataset_key": publish.get("dataset_key"),
            "dataset_version_id": (
                dataset_version.get("id") if dataset_version else None
            ),
            "recipe_hash": normalized_recipe_hash,
            "contract_hash": contract_hash,
        },
        metadata={
            "rows": publish.get("rows"),
            "quality_alerts": len(publish.get("quality_alerts") or []),
        },
        suggested_next_actions=["analyze_data"],
    )
