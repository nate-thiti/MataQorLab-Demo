"""Dataset Catalog and immutable DatasetVersion registration."""

from __future__ import annotations

from typing import Any


SUPPORTED_SOURCE_TYPES = {"file", "api", "sql", "cloud"}
_MISSING_CATALOG_ERRORS = ("PGRST202", "PGRST205", "42P01")


def canonical_dataset_key(source_type: str, source_ref: dict[str, Any]) -> str:
    normalized_type = str(source_type or "").strip().lower()
    if normalized_type not in SUPPORTED_SOURCE_TYPES:
        raise ValueError("Unsupported dataset source type")
    if normalized_type == "file":
        identity = source_ref.get("file_name")
    elif normalized_type == "sql":
        identity = ":".join(
            filter(
                None,
                [
                    str(source_ref.get("connection_id") or "").strip(),
                    str(source_ref.get("table_name") or "").strip(),
                ],
            )
        )
    elif normalized_type == "cloud":
        identity = (
            source_ref.get("connection_id")
            or source_ref.get("source_url")
            or source_ref.get("url")
        )
    else:
        identity = source_ref.get("connection_id")
    normalized_identity = str(identity or "").strip()
    if not normalized_identity:
        raise ValueError("Dataset source identity is missing")
    return f"{normalized_type}:{normalized_identity}"


def register_completed_dataset_version(
    client: Any,
    *,
    user_id: str,
    source_type: str,
    source_ref: dict[str, Any],
    display_name: str,
    source_fingerprint: str | None,
    recipe_hash: str | None,
    contract_hash: str | None,
    recipe_id: str | None,
    run_id: str | None,
    data_setup_session_id: str | None,
    output_dataset_key: str,
    output_file: str,
    output_version: str | None,
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Atomically register a completed materialized version.

    Missing migration errors are tolerated during rolling deployment. Other
    registration failures remain visible to avoid silently corrupting lineage.
    """
    source_type = str(source_type or "").strip().lower()
    params = {
        "p_user_id": user_id,
        "p_canonical_dataset_key": canonical_dataset_key(source_type, source_ref),
        "p_source_type": source_type,
        "p_source_ref": source_ref,
        "p_display_name": str(display_name or output_dataset_key).strip()[:500],
        "p_source_fingerprint": source_fingerprint,
        "p_recipe_hash": recipe_hash,
        "p_contract_hash": contract_hash,
        "p_recipe_id": recipe_id,
        "p_run_id": run_id,
        "p_data_setup_session_id": data_setup_session_id,
        "p_output_dataset_key": output_dataset_key,
        "p_output_file": output_file,
        "p_output_version": output_version,
        "p_lineage": lineage or {},
    }
    if not hasattr(client, "rpc"):
        return None
    try:
        response = client.rpc("register_dataset_version", params).execute()
    except Exception as exc:
        if any(code in str(exc) for code in _MISSING_CATALOG_ERRORS):
            return None
        raise
    rows = response.data or []
    return rows[0] if rows else None


def list_dataset_catalog(
    user_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    workspace_id: str | None = None,
    client: Any,
) -> dict[str, Any]:
    from app.services.tenancy import list_user_workspace_ids

    bounded_limit = max(1, min(int(limit), 100))
    bounded_offset = max(0, int(offset))
    query = (
        client.table("dataset_catalog")
        .select("*, active_version:dataset_versions!dataset_catalog_active_version_id_fkey(*)")
    )
    if workspace_id:
        query = query.eq("workspace_id", workspace_id)
    else:
        workspace_ids = list(list_user_workspace_ids(client, user_id))
        # Owner rows plus shared workspace rows. PostgREST or-filter keeps the
        # browser client from needing service-role expansion.
        if workspace_ids:
            quoted = ",".join(workspace_ids)
            query = query.or_(
                f"user_id.eq.{user_id},workspace_id.in.({quoted})"
            )
        else:
            query = query.eq("user_id", user_id)
    response = (
        query.order("updated_at", desc=True)
        .range(bounded_offset, bounded_offset + bounded_limit)
        .execute()
    )
    rows = response.data or []
    has_more = len(rows) > bounded_limit
    return {
        "datasets": rows[:bounded_limit],
        "next_offset": bounded_offset + bounded_limit if has_more else None,
        "has_more": has_more,
    }


def list_dataset_versions(
    user_id: str,
    catalog_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    client: Any,
) -> dict[str, Any]:
    owner = (
        client.table("dataset_catalog").select("id")
        .eq("id", catalog_id).eq("user_id", user_id).limit(1).execute()
    )
    if not owner.data:
        raise ValueError("Dataset not found")
    bounded_limit = max(1, min(int(limit), 100))
    bounded_offset = max(0, int(offset))
    response = (
        client.table("dataset_versions").select("*")
        .eq("catalog_id", catalog_id).eq("user_id", user_id)
        .order("version_number", desc=True)
        .range(bounded_offset, bounded_offset + bounded_limit)
        .execute()
    )
    rows = response.data or []
    has_more = len(rows) > bounded_limit
    return {
        "versions": rows[:bounded_limit],
        "next_offset": bounded_offset + bounded_limit if has_more else None,
        "has_more": has_more,
    }


def list_dataset_lineage(
    user_id: str,
    dataset_version_id: str,
    *,
    limit: int = 100,
    client: Any,
) -> list[dict[str, Any]]:
    version = (
        client.table("dataset_versions").select("id")
        .eq("id", dataset_version_id).eq("user_id", user_id).limit(1).execute()
    )
    if not version.data:
        raise ValueError("DatasetVersion not found")
    response = (
        client.table("dataset_lineage_events").select("*")
        .eq("dataset_version_id", dataset_version_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(max(1, min(int(limit), 200)))
        .execute()
    )
    return list(response.data or [])


def record_dataset_lineage_event(
    client: Any,
    *,
    user_id: str,
    dataset_version_id: str | None,
    event_kind: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not dataset_version_id:
        return None
    try:
        version = (
            client.table("dataset_versions").select("id")
            .eq("id", dataset_version_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not version.data:
            return None
        response = client.table("dataset_lineage_events").insert({
            "user_id": user_id,
            "dataset_version_id": dataset_version_id,
            "event_kind": event_kind,
            "payload": payload or {},
        }).execute()
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as exc:
        if any(code in str(exc) for code in _MISSING_CATALOG_ERRORS):
            return None
        raise
