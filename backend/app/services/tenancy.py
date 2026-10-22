"""Organization/workspace membership and resource grant checks."""
from __future__ import annotations

from typing import Any

WORKSPACE_EDITOR_ROLES = {"admin", "editor"}
ORG_ADMIN_ROLES = {"owner", "admin", "reviewer"}


class TenancyError(ValueError):
    pass


def get_workspace_membership(
    client: Any,
    *,
    user_id: str,
    workspace_id: str,
) -> dict[str, Any] | None:
    response = (
        client.table("workspace_members")
        .select("workspace_id,user_id,role,workspaces!inner(id,organization_id,name)")
        .eq("workspace_id", workspace_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def require_workspace_access(
    client: Any,
    *,
    user_id: str,
    workspace_id: str | None,
    write: bool = False,
) -> dict[str, Any] | None:
    if not workspace_id:
        return None
    membership = get_workspace_membership(
        client, user_id=user_id, workspace_id=workspace_id
    )
    if not membership:
        raise TenancyError("Workspace access denied")
    if write and membership.get("role") not in WORKSPACE_EDITOR_ROLES:
        raise TenancyError("Workspace write access denied")
    workspace = membership.get("workspaces") or {}
    return {
        "workspace_id": workspace_id,
        "organization_id": workspace.get("organization_id"),
        "role": membership.get("role"),
    }


def ownership_payload(
    *,
    user_id: str,
    workspace_context: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = {"user_id": user_id}
    if workspace_context:
        payload["workspace_id"] = workspace_context.get("workspace_id")
        payload["organization_id"] = workspace_context.get("organization_id")
    return payload


def can_access_owner_or_workspace(
    *,
    row: dict[str, Any],
    user_id: str,
    workspace_ids: set[str] | None = None,
) -> bool:
    if str(row.get("user_id") or "") == str(user_id):
        return True
    workspace_id = str(row.get("workspace_id") or "")
    return bool(workspace_id and workspace_ids and workspace_id in workspace_ids)


def list_user_workspace_ids(client: Any, user_id: str) -> set[str]:
    response = (
        client.table("workspace_members")
        .select("workspace_id")
        .eq("user_id", user_id)
        .execute()
    )
    return {
        str(row["workspace_id"])
        for row in (response.data or [])
        if row.get("workspace_id")
    }


def grant_resource_access(
    client: Any,
    *,
    organization_id: str,
    workspace_id: str | None,
    resource_type: str,
    resource_id: str,
    principal_type: str,
    principal_id: str,
    role: str,
    granted_by: str,
) -> dict[str, Any]:
    if role not in {"viewer", "editor", "admin"}:
        raise TenancyError("Invalid grant role")
    if principal_type not in {"organization", "workspace", "user"}:
        raise TenancyError("Invalid grant principal")
    payload = {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "principal_type": principal_type,
        "principal_id": principal_id,
        "role": role,
        "granted_by": granted_by,
        "revoked_at": None,
    }
    existing = (
        client.table("resource_grants")
        .select("*")
        .eq("resource_type", resource_type)
        .eq("resource_id", resource_id)
        .eq("principal_type", principal_type)
        .eq("principal_id", principal_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        response = (
            client.table("resource_grants")
            .update({
                "role": role,
                "granted_by": granted_by,
                "workspace_id": workspace_id,
                "revoked_at": None,
            })
            .eq("id", existing.data[0]["id"])
            .execute()
        )
        return dict((response.data or existing.data)[0])
    response = client.table("resource_grants").insert(payload).execute()
    if not response.data:
        raise TenancyError("Could not create resource grant")
    return dict(response.data[0])


def revoke_resource_access(
    client: Any,
    *,
    grant_id: str,
    organization_id: str,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    response = (
        client.table("resource_grants")
        .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", grant_id)
        .eq("organization_id", organization_id)
        .is_("revoked_at", "null")
        .execute()
    )
    if not response.data:
        raise TenancyError("Grant not found")
    return dict(response.data[0])


def has_resource_grant(
    client: Any,
    *,
    user_id: str,
    resource_type: str,
    resource_id: str,
    minimum_role: str = "viewer",
) -> bool:
    role_rank = {"viewer": 1, "editor": 2, "admin": 3}
    needed = role_rank.get(minimum_role, 1)
    workspace_ids = list_user_workspace_ids(client, user_id)
    response = (
        client.table("resource_grants")
        .select("role,principal_type,principal_id")
        .eq("resource_type", resource_type)
        .eq("resource_id", resource_id)
        .is_("revoked_at", "null")
        .execute()
    )
    for row in response.data or []:
        principal_type = row.get("principal_type")
        principal_id = str(row.get("principal_id") or "")
        if role_rank.get(str(row.get("role") or ""), 0) < needed:
            continue
        if principal_type == "user" and principal_id == str(user_id):
            return True
        if principal_type == "workspace" and principal_id in workspace_ids:
            return True
        if principal_type == "organization":
            membership = (
                client.table("organization_members")
                .select("organization_id")
                .eq("organization_id", principal_id)
                .eq("user_id", user_id)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if membership.data:
                return True
    return False
