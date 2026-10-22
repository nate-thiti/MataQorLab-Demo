"""Append-only platform and administrative access audit."""
from __future__ import annotations

from typing import Any

from app.core.observability import correlation_id


def record_platform_audit(
    client: Any,
    *,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    payload = {
        "actor_user_id": actor_user_id,
        "action": str(action)[:120],
        "resource_type": str(resource_type)[:80],
        "resource_id": str(resource_id)[:120] if resource_id else None,
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "correlation_id": correlation_id(),
        "detail": detail or {},
    }
    try:
        response = client.table("platform_audit_events").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as exc:
        # Rolling deploys may hit environments before the P2 migration lands.
        if any(code in str(exc) for code in ("PGRST205", "42P01")):
            return None
        raise


def record_admin_access(
    client: Any,
    *,
    actor_user_id: str,
    action: str,
    target_user_id: str | None = None,
    organization_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    payload = {
        "actor_user_id": actor_user_id,
        "action": str(action)[:120],
        "target_user_id": target_user_id,
        "organization_id": organization_id,
        "resource_type": str(resource_type)[:80] if resource_type else None,
        "resource_id": str(resource_id)[:120] if resource_id else None,
        "correlation_id": correlation_id(),
        "detail": detail or {},
    }
    try:
        response = client.table("admin_access_events").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as exc:
        if any(code in str(exc) for code in ("PGRST205", "42P01")):
            return None
        raise


def list_platform_audit(
    client: Any,
    *,
    organization_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    bounded = max(1, min(int(limit), 200))
    response = (
        client.table("platform_audit_events")
        .select("*")
        .eq("organization_id", organization_id)
        .order("created_at", desc=True)
        .limit(bounded)
        .execute()
    )
    return list(response.data or [])
