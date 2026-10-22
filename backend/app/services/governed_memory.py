"""Organization/workspace tenancy and governed memory operations."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from app.core.supabase import get_supabase_client
from app.services.conversation_memory import extract_keywords

ORG_ADMIN_ROLES = {"owner", "admin"}
REVIEW_ROLES = {"owner", "admin", "reviewer"}
EDIT_ROLES = {"owner", "admin", "reviewer", "member"}
ASSIGNABLE_ROLES = {"admin", "reviewer", "member"}
WORKSPACE_EDIT_ROLES = {"admin", "editor"}
ENTERPRISE_MIN_SEATS = 2
ENTERPRISE_MAX_SEATS = 500
MEMORY_TYPES = {
    "preference", "business_definition", "kpi_formula", "terminology",
    "policy", "reporting_convention", "dataset_fact",
}
SCOPES = {"personal", "organization", "workspace", "project", "dataset"}
STATUSES = {"draft", "pending", "approved", "rejected", "archived"}


class GovernanceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    if len(slug) < 2:
        slug = f"workspace-{hashlib.sha256((value or 'workspace').encode()).hexdigest()[:8]}"
    return slug[:63]


def _organization_role(client: Any, user_id: str, organization_id: str) -> str | None:
    response = (
        client.table("organization_members").select("role,status")
        .eq("organization_id", organization_id).eq("user_id", user_id).limit(1).execute()
    )
    if not response.data or response.data[0].get("status") != "active":
        return None
    return str(response.data[0].get("role") or "")


def _workspace_role(client: Any, user_id: str, workspace_id: str) -> str | None:
    response = (
        client.table("workspace_members").select("role")
        .eq("workspace_id", workspace_id).eq("user_id", user_id).limit(1).execute()
    )
    return str(response.data[0].get("role") or "") if response.data else None


def _require_org_role(client: Any, user_id: str, organization_id: str, roles: set[str]) -> str:
    role = _organization_role(client, user_id, organization_id)
    if role not in roles:
        raise GovernanceError("Insufficient organization permission")
    return role


def _enforce_organization_seat_limit(
    client: Any,
    organization_id: str,
    member_user_id: str,
) -> None:
    owner_rows = (
        client.table("organization_members")
        .select("user_id")
        .eq("organization_id", organization_id)
        .eq("role", "owner")
        .eq("status", "active")
        .limit(1)
        .execute()
    ).data or []
    if not owner_rows:
        return
    owner_id = owner_rows[0]["user_id"]
    profile_rows = (
        client.table("profiles")
        .select("subscription_seats,plans(name)")
        .eq("id", owner_id)
        .limit(1)
        .execute()
    ).data or []
    if not profile_rows:
        return
    profile = profile_rows[0]
    plan = profile.get("plans")
    if isinstance(plan, list):
        plan = plan[0] if plan else {}
    plan_name = str(plan.get("name") if isinstance(plan, dict) else "")
    if plan_name.casefold() != "enterprise":
        return

    memberships = (
        client.table("organization_members")
        .select("user_id,status")
        .eq("organization_id", organization_id)
        .execute()
    ).data or []
    if any(
        row.get("user_id") == member_user_id and row.get("status") == "active"
        for row in memberships
    ):
        return
    active_members = sum(row.get("status") == "active" for row in memberships)
    seat_limit = min(
        ENTERPRISE_MAX_SEATS,
        max(ENTERPRISE_MIN_SEATS, int(profile.get("subscription_seats") or 1)),
    )
    if active_members >= seat_limit:
        raise GovernanceError(
            f"Enterprise seat limit reached ({seat_limit} users)"
        )


def list_governance_context(user_id: str, *, client: Any | None = None) -> dict[str, Any]:
    client = client or get_supabase_client()
    memberships = (
        client.table("organization_members")
        .select("organization_id,role,status,organizations(id,name,slug,created_at)")
        .eq("user_id", user_id).eq("status", "active").execute()
    ).data or []
    organization_ids = [row["organization_id"] for row in memberships]
    workspaces: list[dict[str, Any]] = []
    if organization_ids:
        rows = (
            client.table("workspaces").select("*")
            .in_("organization_id", organization_ids).order("created_at").execute()
        ).data or []
        member_rows = (
            client.table("workspace_members").select("workspace_id,role")
            .eq("user_id", user_id).execute()
        ).data or []
        role_by_workspace = {row["workspace_id"]: row["role"] for row in member_rows}
        workspaces = [
            {**row, "role": role_by_workspace.get(row["id"])}
            for row in rows if row["id"] in role_by_workspace
        ]
    return {"organizations": memberships, "workspaces": workspaces}


def _require_enterprise_plan(client: Any, user_id: str) -> None:
    profile_rows = (
        client.table("profiles")
        .select("plans(name)")
        .eq("id", user_id)
        .limit(1)
        .execute()
    ).data or []
    plan = (profile_rows[0] or {}).get("plans") if profile_rows else None
    if isinstance(plan, list):
        plan = plan[0] if plan else {}
    plan_name = str(plan.get("name") if isinstance(plan, dict) else "")
    if plan_name.casefold() != "enterprise":
        raise GovernanceError(
            "Organization workspaces require a company (Enterprise) subscription"
        )


def create_organization(user_id: str, name: str, *, client: Any | None = None) -> dict[str, Any]:
    client = client or get_supabase_client()
    _require_enterprise_plan(client, user_id)
    safe_name = (name or "").strip()[:160]
    if not safe_name:
        raise GovernanceError("Organization name is required")
    slug = f"{_slug(safe_name)}-{hashlib.sha256(f'{user_id}:{safe_name}'.encode()).hexdigest()[:6]}"
    organization = (client.table("organizations").insert({
        "name": safe_name, "slug": slug, "created_by": user_id,
    }).execute().data or [None])[0]
    if not organization:
        raise GovernanceError("Could not create organization")
    try:
        client.table("organization_members").insert({
            "organization_id": organization["id"], "user_id": user_id,
            "role": "owner", "status": "active", "created_by": user_id,
        }).execute()
    except Exception:
        client.table("organizations").delete().eq("id", organization["id"]).execute()
        raise
    return organization


def create_workspace(
    user_id: str, organization_id: str, name: str, *, client: Any | None = None
) -> dict[str, Any]:
    client = client or get_supabase_client()
    _require_org_role(client, user_id, organization_id, ORG_ADMIN_ROLES)
    safe_name = (name or "").strip()[:160]
    if not safe_name:
        raise GovernanceError("Workspace name is required")
    workspace = (client.table("workspaces").insert({
        "organization_id": organization_id, "name": safe_name,
        "slug": _slug(safe_name), "created_by": user_id,
    }).execute().data or [None])[0]
    if not workspace:
        raise GovernanceError("Could not create workspace")
    try:
        client.table("workspace_members").insert({
            "workspace_id": workspace["id"], "user_id": user_id,
            "role": "admin", "created_by": user_id,
        }).execute()
    except Exception:
        client.table("workspaces").delete().eq("id", workspace["id"]).execute()
        raise
    return workspace


def update_organization(
    user_id: str, organization_id: str, name: str, *, client: Any | None = None
) -> dict[str, Any]:
    client = client or get_supabase_client()
    _require_org_role(client, user_id, organization_id, ORG_ADMIN_ROLES)
    safe_name = (name or "").strip()[:160]
    if not safe_name:
        raise GovernanceError("Organization name is required")
    updated = (
        client.table("organizations")
        .update({"name": safe_name, "updated_at": _now()})
        .eq("id", organization_id)
        .execute()
        .data
        or [None]
    )[0]
    if not updated:
        raise GovernanceError("Organization not found")
    return updated


def delete_organization(
    user_id: str, organization_id: str, *, client: Any | None = None
) -> dict[str, Any]:
    client = client or get_supabase_client()
    role = _organization_role(client, user_id, organization_id)
    if role != "owner":
        raise GovernanceError("Only the organization owner can delete it")
    existing = (
        client.table("organizations").select("id,name").eq("id", organization_id).limit(1).execute()
    ).data or []
    if not existing:
        raise GovernanceError("Organization not found")
    client.table("organizations").delete().eq("id", organization_id).execute()
    return {"id": organization_id, "deleted": True, "name": existing[0].get("name")}


def update_workspace(
    user_id: str,
    workspace_id: str,
    name: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    workspace = (
        client.table("workspaces")
        .select("id,organization_id,name,slug")
        .eq("id", workspace_id)
        .limit(1)
        .execute()
        .data
        or [None]
    )[0]
    if not workspace:
        raise GovernanceError("Workspace not found")
    _require_org_role(client, user_id, str(workspace["organization_id"]), ORG_ADMIN_ROLES)
    safe_name = (name or "").strip()[:160]
    if not safe_name:
        raise GovernanceError("Workspace name is required")
    updated = (
        client.table("workspaces")
        .update({
            "name": safe_name,
            "slug": _slug(safe_name),
            "updated_at": _now(),
        })
        .eq("id", workspace_id)
        .execute()
        .data
        or [None]
    )[0]
    if not updated:
        raise GovernanceError("Could not update workspace")
    return updated


def delete_workspace(
    user_id: str, workspace_id: str, *, client: Any | None = None
) -> dict[str, Any]:
    client = client or get_supabase_client()
    workspace = (
        client.table("workspaces")
        .select("id,organization_id,name")
        .eq("id", workspace_id)
        .limit(1)
        .execute()
        .data
        or [None]
    )[0]
    if not workspace:
        raise GovernanceError("Workspace not found")
    _require_org_role(client, user_id, str(workspace["organization_id"]), ORG_ADMIN_ROLES)
    client.table("workspaces").delete().eq("id", workspace_id).execute()
    return {
        "id": workspace_id,
        "organization_id": workspace["organization_id"],
        "deleted": True,
        "name": workspace.get("name"),
    }


def add_member(
    user_id: str,
    organization_id: str,
    member_user_id: str,
    role: str,
    *,
    workspace_id: str | None = None,
    client: Any | None = None,
) -> None:
    client = client or get_supabase_client()
    _require_org_role(client, user_id, organization_id, ORG_ADMIN_ROLES)
    safe_role = role if role in ASSIGNABLE_ROLES else "member"
    if workspace_id:
        workspace = (
            client.table("workspaces").select("id").eq("id", workspace_id)
            .eq("organization_id", organization_id).limit(1).execute()
        )
        if not workspace.data:
            raise GovernanceError("Workspace does not belong to organization")
    _enforce_organization_seat_limit(
        client,
        organization_id,
        member_user_id,
    )
    client.table("organization_members").upsert({
        "organization_id": organization_id, "user_id": member_user_id,
        "role": safe_role, "status": "active", "created_by": user_id, "updated_at": _now(),
    }, on_conflict="organization_id,user_id").execute()
    if workspace_id:
        workspace_role = "admin" if safe_role in ORG_ADMIN_ROLES else (
            "editor" if safe_role in {"reviewer", "member"} else "viewer"
        )
        client.table("workspace_members").upsert({
            "workspace_id": workspace_id, "user_id": member_user_id,
            "role": workspace_role, "created_by": user_id,
        }, on_conflict="workspace_id,user_id").execute()


def _memory_snapshot(memory: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "scope", "organization_id", "workspace_id", "owner_user_id", "memory_type",
        "memory_key", "title", "content", "structured_value", "keywords", "status",
        "confidence", "source_type", "source_ref", "source_hash", "version",
        "supersedes_id", "expires_at", "approved_by", "approved_at",
    )
    return {key: memory.get(key) for key in keys}


def _record_revision(client: Any, memory: dict[str, Any], actor: str, change_type: str) -> None:
    client.table("governed_memory_revisions").insert({
        "memory_id": memory["id"], "organization_id": memory.get("organization_id"),
        "owner_user_id": memory.get("owner_user_id"),
        "version": memory["version"], "snapshot": _memory_snapshot(memory),
        "change_type": change_type, "changed_by": actor,
    }).execute()
    client.table("governed_memory_audit_events").insert({
        "memory_id": memory["id"], "organization_id": memory.get("organization_id"),
        "owner_user_id": memory.get("owner_user_id"),
        "actor_user_id": actor, "event_type": change_type,
        "detail": {"version": memory["version"], "status": memory["status"]},
    }).execute()


def _can_edit_memory(client: Any, user_id: str, memory: dict[str, Any]) -> bool:
    if memory.get("scope") == "personal":
        return memory.get("owner_user_id") == user_id
    role = _organization_role(client, user_id, str(memory.get("organization_id")))
    if role not in EDIT_ROLES:
        return False
    workspace_id = memory.get("workspace_id")
    if workspace_id and _workspace_role(client, user_id, str(workspace_id)) not in WORKSPACE_EDIT_ROLES:
        return False
    return role in REVIEW_ROLES or memory.get("created_by") == user_id


def _can_view_memory(client: Any, user_id: str, memory: dict[str, Any]) -> bool:
    if memory.get("scope") == "personal":
        return memory.get("owner_user_id") == user_id
    role = _organization_role(client, user_id, str(memory.get("organization_id")))
    if role not in EDIT_ROLES:
        return False
    workspace_id = memory.get("workspace_id")
    if workspace_id and not _workspace_role(client, user_id, str(workspace_id)):
        return False
    return (
        memory.get("status") == "approved"
        or role in REVIEW_ROLES
        or memory.get("created_by") == user_id
    )


def list_memories(
    user_id: str,
    *,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    client = client or get_supabase_client()
    safe_limit = min(max(limit, 1), 200)
    query = client.table("governed_memories").select("*")
    organization_role: str | None = None
    accessible_workspace_ids: set[str] = set()
    if organization_id:
        organization_role = _require_org_role(
            client, user_id, organization_id, EDIT_ROLES
        )
        query = query.eq("organization_id", organization_id)
        if workspace_id:
            if not _workspace_role(client, user_id, workspace_id):
                raise GovernanceError("Workspace access denied")
            accessible_workspace_ids.add(workspace_id)
            query = query.eq("workspace_id", workspace_id)
        else:
            workspace_rows = (
                client.table("workspace_members").select("workspace_id")
                .eq("user_id", user_id).execute()
            ).data or []
            accessible_workspace_ids = {
                str(row["workspace_id"]) for row in workspace_rows
            }
    else:
        query = query.eq("owner_user_id", user_id).eq("scope", "personal")
    if status in STATUSES:
        query = query.eq("status", status)
    rows = list(
        query.order("updated_at", desc=True)
        .limit(safe_limit * 3)
        .execute().data or []
    )
    if not organization_id:
        return rows[:safe_limit]
    return [
        row for row in rows
        if (
            not row.get("workspace_id")
            or str(row["workspace_id"]) in accessible_workspace_ids
        )
        and (
            row.get("status") == "approved"
            or organization_role in REVIEW_ROLES
            or row.get("created_by") == user_id
        )
    ][:safe_limit]


def save_memory(user_id: str, payload: dict[str, Any], *, client: Any | None = None) -> dict[str, Any]:
    client = client or get_supabase_client()
    memory_id = payload.get("id")
    scope = str(payload.get("scope") or "personal")
    if scope not in SCOPES:
        raise GovernanceError("Invalid memory scope")
    organization_id = payload.get("organization_id")
    workspace_id = payload.get("workspace_id")
    if scope != "personal":
        if not organization_id:
            raise GovernanceError("organization_id is required")
        _require_org_role(client, user_id, organization_id, EDIT_ROLES)
        if scope in {"workspace", "project", "dataset"} and (
            not workspace_id
            or _workspace_role(client, user_id, workspace_id) not in WORKSPACE_EDIT_ROLES
        ):
            raise GovernanceError("Workspace access denied")
        if scope in {"workspace", "project", "dataset"}:
            workspace = (
                client.table("workspaces").select("id").eq("id", workspace_id)
                .eq("organization_id", organization_id).limit(1).execute()
            )
            if not workspace.data:
                raise GovernanceError("Workspace does not belong to organization")
    memory_type = str(payload.get("memory_type") or "business_definition")
    if memory_type not in MEMORY_TYPES:
        raise GovernanceError("Invalid memory type")
    title = str(payload.get("title") or "").strip()[:240]
    content = str(payload.get("content") or "").strip()[:12000]
    if not title or not content:
        raise GovernanceError("Title and content are required")
    status = "draft" if scope == "personal" else "pending"
    base = {
        "scope": scope, "organization_id": organization_id if scope != "personal" else None,
        "workspace_id": workspace_id if scope in {"workspace", "project", "dataset"} else None,
        "owner_user_id": user_id if scope == "personal" else None,
        "memory_type": memory_type,
        "memory_key": str(payload.get("memory_key") or _slug(title))[:240],
        "title": title, "content": content,
        "structured_value": payload.get("structured_value") if isinstance(payload.get("structured_value"), dict) else {},
        "keywords": extract_keywords(f"{title} {content}", limit=32),
        "confidence": min(1, max(0, float(payload.get("confidence", 1)))),
        "source_type": (
            str(payload.get("source_type") or "manual")
            if str(payload.get("source_type") or "manual") in {"manual", "verified_finding", "import", "correction"}
            else "manual"
        ),
        "source_ref": str(payload.get("source_ref") or "")[:1000] or None,
        "source_hash": hashlib.sha256(content.encode()).hexdigest(),
        "updated_at": _now(),
    }
    if memory_id:
        existing = (client.table("governed_memories").select("*").eq("id", memory_id).limit(1).execute().data or [None])[0]
        if not existing or not _can_edit_memory(client, user_id, existing):
            raise GovernanceError("Memory not found or access denied")
        if (
            scope != existing.get("scope")
            or organization_id != existing.get("organization_id")
            or workspace_id != existing.get("workspace_id")
        ):
            raise GovernanceError("Memory scope and tenancy cannot be changed")
        base.update({"version": int(existing["version"]) + 1, "status": status, "approved_by": None, "approved_at": None})
        memory = (
            client.table("governed_memories").update(base)
            .eq("id", memory_id).eq("version", existing["version"])
            .execute().data or [None]
        )[0]
        if not memory:
            raise GovernanceError("Memory changed concurrently; reload and try again")
        change = "updated"
    else:
        base.update({"created_by": user_id, "status": status})
        memory = (client.table("governed_memories").insert(base).execute().data or [None])[0]
        change = "created"
    if not memory:
        raise GovernanceError("Could not save memory")
    _record_revision(client, memory, user_id, change)
    return memory


def review_memory(
    user_id: str, memory_id: str, decision: str, *, client: Any | None = None
) -> dict[str, Any]:
    client = client or get_supabase_client()
    memory = (client.table("governed_memories").select("*").eq("id", memory_id).limit(1).execute().data or [None])[0]
    if not memory or memory.get("scope") == "personal":
        raise GovernanceError("Shared memory not found")
    _require_org_role(client, user_id, memory["organization_id"], REVIEW_ROLES)
    if memory.get("status") != "pending":
        raise GovernanceError("Only pending memory can be reviewed")
    status = "approved" if decision == "approve" else "rejected"
    update = {
        "status": status, "version": int(memory["version"]) + 1,
        "approved_by": user_id if status == "approved" else None,
        "approved_at": _now() if status == "approved" else None, "updated_at": _now(),
    }
    saved = (
        client.table("governed_memories").update(update)
        .eq("id", memory_id).eq("version", memory["version"])
        .execute().data or [None]
    )[0]
    if not saved:
        raise GovernanceError("Memory changed concurrently; reload and try again")
    _record_revision(client, saved, user_id, status)
    return saved


def archive_memory(user_id: str, memory_id: str, *, client: Any | None = None) -> dict[str, Any]:
    client = client or get_supabase_client()
    memory = (client.table("governed_memories").select("*").eq("id", memory_id).limit(1).execute().data or [None])[0]
    if not memory or not _can_edit_memory(client, user_id, memory):
        raise GovernanceError("Memory not found or access denied")
    saved = (
        client.table("governed_memories").update({
            "status": "archived", "version": int(memory["version"]) + 1,
            "approved_by": None, "approved_at": None, "updated_at": _now(),
        }).eq("id", memory_id).eq("version", memory["version"])
        .execute().data or [None]
    )[0]
    if not saved:
        raise GovernanceError("Memory changed concurrently; reload and try again")
    _record_revision(client, saved, user_id, "archived")
    return saved


def restore_memory(
    user_id: str, memory_id: str, revision_id: str, *, client: Any | None = None
) -> dict[str, Any]:
    client = client or get_supabase_client()
    memory = (client.table("governed_memories").select("*").eq("id", memory_id).limit(1).execute().data or [None])[0]
    if not memory or not _can_edit_memory(client, user_id, memory):
        raise GovernanceError("Memory not found or access denied")
    revision = (
        client.table("governed_memory_revisions").select("snapshot")
        .eq("id", revision_id).eq("memory_id", memory_id).limit(1).execute()
    )
    if not revision.data:
        raise GovernanceError("Revision not found")
    snapshot = dict(revision.data[0]["snapshot"])
    snapshot.pop("version", None)
    snapshot.update({
        "version": int(memory["version"]) + 1,
        "status": "draft" if memory.get("scope") == "personal" else "pending",
        "approved_by": None,
        "approved_at": None,
        "updated_at": _now(),
    })
    saved = (
        client.table("governed_memories").update(snapshot)
        .eq("id", memory_id).eq("version", memory["version"])
        .execute().data or [None]
    )[0]
    if not saved:
        raise GovernanceError("Memory changed concurrently; reload and try again")
    _record_revision(client, saved, user_id, "restored")
    return saved


def memory_history(
    user_id: str, memory_id: str, *, client: Any | None = None
) -> dict[str, Any]:
    client = client or get_supabase_client()
    memory = (client.table("governed_memories").select("*").eq("id", memory_id).limit(1).execute().data or [None])[0]
    if not memory or not _can_view_memory(client, user_id, memory):
        raise GovernanceError("Memory not found or access denied")
    revisions = (
        client.table("governed_memory_revisions").select("*")
        .eq("memory_id", memory_id).order("version", desc=True).limit(100).execute()
    ).data or []
    audits = (
        client.table("governed_memory_audit_events").select("*")
        .eq("memory_id", memory_id).order("created_at", desc=True).limit(100).execute()
    ).data or []
    return {"revisions": revisions, "audit_events": audits}


def retrieve_governed_memory(
    user_id: str,
    question: str,
    *,
    dataset_key: str | None = None,
    limit: int = 8,
    max_chars: int = 5000,
    client: Any | None = None,
) -> dict[str, Any]:
    """Permission-aware, bounded retrieval. Shared memory must be approved."""
    client = client or get_supabase_client()
    context = list_governance_context(user_id, client=client)
    org_ids = [row["organization_id"] for row in context["organizations"]]
    workspace_ids = [row["id"] for row in context["workspaces"]]
    rows = list_memories(user_id, limit=100, client=client)
    if org_ids:
        shared = (
            client.table("governed_memories").select("*")
            .in_("organization_id", org_ids).eq("status", "approved")
            .order("updated_at", desc=True).limit(200).execute()
        ).data or []
        rows.extend(
            row for row in shared
            if row.get("workspace_id") is None or row.get("workspace_id") in workspace_ids
        )
    query_terms = set(extract_keywords(question, limit=32))
    if dataset_key:
        query_terms.update(extract_keywords(dataset_key, limit=8))
    scored: list[tuple[float, dict[str, Any]]] = []
    now = datetime.now(timezone.utc)
    for row in rows:
        expires = row.get("expires_at")
        if expires:
            try:
                if datetime.fromisoformat(str(expires).replace("Z", "+00:00")) <= now:
                    continue
            except ValueError:
                continue
        terms = set(row.get("keywords") or [])
        overlap = len(query_terms & terms)
        dataset_bonus = 2 if dataset_key and dataset_key in str(row.get("memory_key")) else 0
        scope_bonus = 1 if row.get("scope") in {"workspace", "dataset"} else 0
        score = overlap * 3 + dataset_bonus + scope_bonus + float(row.get("confidence") or 0)
        if overlap or not query_terms:
            scored.append((score, row))
    scored.sort(key=lambda item: (item[0], item[1].get("updated_at") or ""), reverse=True)
    selected: list[dict[str, Any]] = []
    used = 0
    for score, row in scored[:limit]:
        text = f"{row['title']}: {row['content']}"
        if used + len(text) > max_chars:
            break
        used += len(text)
        selected.append({
            "id": row["id"], "scope": row["scope"], "type": row["memory_type"],
            "title": row["title"], "content": row["content"], "confidence": float(row["confidence"]),
            "source_hash": row.get("source_hash"), "score": round(score, 3),
        })
        try:
            client.table("governed_memory_audit_events").insert({
                "memory_id": row["id"],
                "organization_id": row.get("organization_id"),
                "owner_user_id": row.get("owner_user_id"),
                "actor_user_id": user_id,
                "event_type": "retrieved",
                "detail": {"score": round(score, 3), "dataset_key": dataset_key},
            }).execute()
        except Exception:
            pass
    return {"items": selected, "context_chars": used}
