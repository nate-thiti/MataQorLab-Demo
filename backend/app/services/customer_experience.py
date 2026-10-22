"""Customer-facing lifecycle operations from activation through embedded delivery."""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.supabase import get_supabase_client
from app.services.governed_memory import add_member, list_governance_context

ONBOARDING_STEPS = {
    "profile",
    "sample_data",
    "connect_data",
    "prepare_data",
    "first_analysis",
    "first_dashboard",
    "invite_team",
    "create_alert",
}
ASSET_KINDS = {"file", "api", "sql", "cloud", "dataset"}
COLLABORATION_KINDS = {"comment", "annotation", "assignment", "approval"}
COLLABORATION_STATUSES = {"open", "resolved", "approved", "rejected"}
ALERT_OPERATORS = {"gt", "gte", "lt", "lte", "eq", "change_gt", "change_lt"}
ALERT_CHANNELS = {"in_app", "email", "slack", "teams", "webhook"}
INTEGRATION_KINDS = {"connector", "notification", "sso", "scim", "embed"}
INTEGRATION_STATUSES = {"draft", "ready", "active", "error", "disabled"}
ORGANIZATION_ONLY_PROVIDERS = {"slack", "teams", "saml", "scim"}
ORG_ADMIN_ROLES = {"owner", "admin"}
SECRET_KEY_PATTERN = re.compile(
    r"(secret|password|private.?key|access.?token|refresh.?token|api.?key|webhook.?secret)",
    re.IGNORECASE,
)


class CustomerExperienceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first(response: Any) -> dict[str, Any] | None:
    rows = response.data or []
    return rows[0] if rows else None


def _organization_role(client: Any, user_id: str, organization_id: str) -> str | None:
    row = _first(
        client.table("organization_members")
        .select("role,status")
        .eq("organization_id", organization_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not row or row.get("status") != "active":
        return None
    return str(row.get("role") or "")


def _require_org_member(client: Any, user_id: str, organization_id: str) -> str:
    role = _organization_role(client, user_id, organization_id)
    if not role:
        raise CustomerExperienceError("Organization membership is required")
    return role


def _require_org_admin(client: Any, user_id: str, organization_id: str) -> str:
    role = _require_org_member(client, user_id, organization_id)
    if role not in ORG_ADMIN_ROLES:
        raise CustomerExperienceError("Organization owner or admin permission is required")
    return role


def _require_owned_report(client: Any, user_id: str, report_id: str) -> None:
    row = _first(
        client.table("visualization_reports")
        .select("id")
        .eq("id", report_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not row:
        raise CustomerExperienceError("Visualization report was not found")


def _validate_workspace(
    client: Any,
    organization_id: str | None,
    workspace_id: str | None,
) -> None:
    if not workspace_id:
        return
    query = client.table("workspaces").select("id").eq("id", workspace_id)
    if organization_id:
        query = query.eq("organization_id", organization_id)
    if not _first(query.limit(1).execute()):
        raise CustomerExperienceError("Workspace does not belong to the organization")


def _reject_secret_configuration(value: Any, path: str = "configuration") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if SECRET_KEY_PATTERN.search(str(key)):
                raise CustomerExperienceError(
                    f"{path}.{key} is secret material and must use production secret storage"
                )
            _reject_secret_configuration(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_secret_configuration(nested, f"{path}[{index}]")


def _owned_rows(
    client: Any,
    table: str,
    user_id: str,
    *,
    order: str = "updated_at",
    limit: int = 50,
) -> list[dict[str, Any]]:
    return (
        client.table(table)
        .select("*")
        .eq("user_id", user_id)
        .order(order, desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def _safe_user_rows(
    client: Any,
    table: str,
    user_id: str,
    columns: str,
    *,
    limit: int = 100,
    user_column: str = "user_id",
) -> list[dict[str, Any]]:
    try:
        return (
            client.table(table)
            .select(columns)
            .eq(user_column, user_id)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def _source_asset_rows(client: Any, user_id: str) -> list[dict[str, Any]]:
    """Project existing saved connections into the unified health contract."""
    sources = (
        (
            "sql",
            _safe_user_rows(
                client,
                "database_connections",
                user_id,
                "id,name,provider,status,created_at",
            ),
        ),
        (
            "api",
            _safe_user_rows(
                client,
                "api_connections",
                user_id,
                "id,name,method,status,created_at",
            ),
        ),
        (
            "cloud",
            _safe_user_rows(
                client,
                "cloud_dataset_connections",
                user_id,
                "id,display_name,provider,last_status,last_refreshed_at,last_error,created_at",
            ),
        ),
    )
    assets: list[dict[str, Any]] = []
    for kind, rows in sources:
        for row in rows:
            raw_status = str(row.get("last_status") or row.get("status") or "unknown").lower()
            healthy = raw_status in {"active", "success", "completed", "healthy"}
            failed = raw_status in {"error", "failed"}
            assets.append({
                "id": f"{kind}:{row.get('id')}",
                "asset_kind": kind,
                "asset_key": str(row.get("id") or ""),
                "display_name": row.get("display_name") or row.get("name") or kind.upper(),
                "connection_status": "healthy" if healthy else ("failed" if failed else "unknown"),
                "freshness_status": "fresh" if row.get("last_refreshed_at") else "unknown",
                "quality_score": None,
                "issue_count": 1 if failed else 0,
                "issues": ([{"code": "connection_failed", "message": row.get("last_error")}]
                           if failed else []),
                "last_success_at": row.get("last_refreshed_at"),
                "last_error": row.get("last_error"),
                "metadata": {
                    "provider": row.get("provider"),
                    "method": row.get("method"),
                    "source": "existing_connection",
                },
                "created_at": row.get("created_at"),
                "updated_at": row.get("last_refreshed_at") or row.get("created_at"),
            })
    return assets


def get_customer_experience_overview(
    user_id: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    onboarding = _first(
        client.table("customer_onboarding_progress")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ) or {
        "user_id": user_id,
        "completed_steps": [],
        "dismissed": False,
        "sample_dataset_loaded": False,
    }
    assets = _owned_rows(client, "customer_data_assets", user_id)
    registered_keys = {
        (str(row.get("asset_kind")), str(row.get("asset_key")))
        for row in assets
    }
    for projected in _source_asset_rows(client, user_id):
        key = (str(projected.get("asset_kind")), str(projected.get("asset_key")))
        if key not in registered_keys:
            assets.append(projected)
    lineage = _owned_rows(
        client, "customer_analysis_lineage", user_id, order="computed_at", limit=30
    )
    collaboration = _owned_rows(
        client, "customer_collaboration_items", user_id, order="created_at"
    )
    alerts = _owned_rows(client, "customer_alert_rules", user_id)
    alert_events = _owned_rows(
        client, "customer_alert_events", user_id, order="triggered_at"
    )
    integrations = _owned_rows(client, "customer_integration_settings", user_id)
    embeds = _owned_rows(client, "customer_embed_configs", user_id)
    governance = list_governance_context(user_id, client=client)
    organization_ids = [
        row.get("organization_id")
        for row in governance.get("organizations", [])
        if row.get("organization_id")
        and row.get("role") in ORG_ADMIN_ROLES
    ]
    invitations: list[dict[str, Any]] = []
    if organization_ids:
        invitations = (
            client.table("customer_organization_invitations")
            .select(
                "id,organization_id,workspace_id,email,role,status,"
                "expires_at,accepted_by,accepted_at,created_at,updated_at"
            )
            .in_("organization_id", organization_ids)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
            or []
        )
    completed = set(onboarding.get("completed_steps") or [])
    if _safe_user_rows(
        client, "profiles", user_id, "id", limit=1, user_column="id"
    ):
        completed.add("profile")
    if assets:
        completed.add("connect_data")
    if _safe_user_rows(client, "etl_recipes", user_id, "id", limit=1):
        completed.add("prepare_data")
    if _safe_user_rows(client, "conversations", user_id, "id", limit=1):
        completed.add("first_analysis")
    reports = _safe_user_rows(
        client,
        "visualization_reports",
        user_id,
        "id,title,dataset_key,dashboard_spec,status,updated_at",
        limit=100,
    )
    if reports:
        completed.add("first_dashboard")
    if alerts:
        completed.add("create_alert")
    if invitations:
        completed.add("invite_team")
    onboarding = {**onboarding, "completed_steps": sorted(completed)}
    return {
        "onboarding": {
            **onboarding,
            "completion_percent": round(len(completed & ONBOARDING_STEPS) / len(ONBOARDING_STEPS) * 100),
            "next_step": next(
                (
                    step
                    for step in (
                        "profile",
                        "sample_data",
                        "connect_data",
                        "prepare_data",
                        "first_analysis",
                        "first_dashboard",
                        "invite_team",
                        "create_alert",
                    )
                    if step not in completed
                ),
                None,
            ),
        },
        "data_assets": assets,
        "lineage": lineage,
        "collaboration": collaboration,
        "alerts": alerts,
        "alert_events": alert_events,
        "available_reports": reports,
        "integrations": integrations,
        "embeds": embeds,
        "invitations": invitations,
        "governance": governance,
        "summary": {
            "healthy_assets": sum(row.get("connection_status") == "healthy" for row in assets),
            "asset_issues": sum(int(row.get("issue_count") or 0) for row in assets),
            "open_collaboration": sum(row.get("status") == "open" for row in collaboration),
            "enabled_alerts": sum(bool(row.get("enabled")) for row in alerts),
            "active_integrations": sum(row.get("status") == "active" for row in integrations),
        },
    }


def save_onboarding_progress(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    steps = sorted({str(step) for step in payload.get("completed_steps") or []})
    if not set(steps).issubset(ONBOARDING_STEPS):
        raise CustomerExperienceError("Unsupported onboarding step")
    dashboard_id = payload.get("first_dashboard_id")
    if dashboard_id:
        _require_owned_report(client, user_id, str(dashboard_id))
    complete = set(steps) == ONBOARDING_STEPS
    row = {
        "user_id": user_id,
        "completed_steps": steps,
        "dismissed": bool(payload.get("dismissed", False)),
        "sample_dataset_loaded": bool(payload.get("sample_dataset_loaded", False)),
        "first_dashboard_id": dashboard_id,
        "completed_at": _now() if complete else None,
        "updated_at": _now(),
    }
    response = (
        client.table("customer_onboarding_progress")
        .upsert(row, on_conflict="user_id")
        .execute()
    )
    return _first(response) or row


def upsert_data_asset(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    kind = str(payload.get("asset_kind") or "").lower()
    if kind not in ASSET_KINDS:
        raise CustomerExperienceError("Unsupported data asset kind")
    key = str(payload.get("asset_key") or "").strip()[:500]
    name = str(payload.get("display_name") or "").strip()[:240]
    if not key or not name:
        raise CustomerExperienceError("Asset key and display name are required")
    organization_id = payload.get("organization_id")
    workspace_id = payload.get("workspace_id")
    if organization_id:
        _require_org_member(client, user_id, str(organization_id))
    _validate_workspace(client, organization_id, workspace_id)
    row = {
        "user_id": user_id,
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "asset_kind": kind,
        "asset_key": key,
        "display_name": name,
        "connection_status": payload.get("connection_status", "unknown"),
        "freshness_status": payload.get("freshness_status", "unknown"),
        "quality_score": payload.get("quality_score"),
        "schema_hash": payload.get("schema_hash"),
        "row_count": payload.get("row_count"),
        "issue_count": max(0, int(payload.get("issue_count") or 0)),
        "issues": payload.get("issues") or [],
        "metadata": payload.get("metadata") or {},
        "last_checked_at": payload.get("last_checked_at") or _now(),
        "last_success_at": payload.get("last_success_at"),
        "last_error": str(payload.get("last_error") or "")[:2000] or None,
        "updated_at": _now(),
    }
    response = (
        client.table("customer_data_assets")
        .upsert(row, on_conflict="user_id,asset_kind,asset_key")
        .execute()
    )
    return _first(response) or row


def create_lineage_record(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    dataset_key = str(payload.get("dataset_key") or "").strip()[:500]
    if not dataset_key:
        raise CustomerExperienceError("Dataset key is required")
    report_id = payload.get("report_id")
    if report_id:
        _require_owned_report(client, user_id, str(report_id))
    row = {
        "user_id": user_id,
        "organization_id": payload.get("organization_id"),
        "workspace_id": payload.get("workspace_id"),
        "report_id": report_id,
        "dataset_key": dataset_key,
        "finding_hash": payload.get("finding_hash"),
        "metric_key": payload.get("metric_key"),
        "formula": payload.get("formula"),
        "executed_sql": payload.get("executed_sql"),
        "source_refs": payload.get("source_refs") or [],
        "filter_state": payload.get("filter_state") or {},
        "data_version": payload.get("data_version"),
        "confidence": min(1, max(0, float(payload.get("confidence", 1)))),
        "computed_at": payload.get("computed_at") or _now(),
    }
    if row["organization_id"]:
        _require_org_member(client, user_id, str(row["organization_id"]))
    _validate_workspace(client, row["organization_id"], row["workspace_id"])
    response = client.table("customer_analysis_lineage").insert(row).execute()
    return _first(response) or row


def create_collaboration_item(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    report_id = str(payload.get("report_id") or "")
    _require_owned_report(client, user_id, report_id)
    kind = str(payload.get("item_kind") or "comment")
    if kind not in COLLABORATION_KINDS:
        raise CustomerExperienceError("Unsupported collaboration item")
    body = str(payload.get("body") or "").strip()[:5000]
    if kind in {"comment", "annotation"} and not body:
        raise CustomerExperienceError("Comment body is required")
    row = {
        "user_id": user_id,
        "organization_id": payload.get("organization_id"),
        "workspace_id": payload.get("workspace_id"),
        "report_id": report_id,
        "item_kind": kind,
        "body": body,
        "anchor": payload.get("anchor") or {},
        "assignee_user_id": payload.get("assignee_user_id"),
        "status": "open",
    }
    response = client.table("customer_collaboration_items").insert(row).execute()
    return _first(response) or row


def update_collaboration_status(
    user_id: str,
    item_id: str,
    status: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    if status not in COLLABORATION_STATUSES:
        raise CustomerExperienceError("Unsupported collaboration status")
    existing = _first(
        client.table("customer_collaboration_items")
        .select("id")
        .eq("id", item_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not existing:
        raise CustomerExperienceError("Collaboration item was not found")
    update = {
        "status": status,
        "resolved_at": _now() if status != "open" else None,
        "updated_at": _now(),
    }
    response = (
        client.table("customer_collaboration_items")
        .update(update)
        .eq("id", item_id)
        .eq("user_id", user_id)
        .execute()
    )
    return _first(response) or {**existing, **update}


def create_alert_rule(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    name = str(payload.get("name") or "").strip()[:160]
    metric_key = str(payload.get("metric_key") or "").strip()[:160]
    operator = str(payload.get("operator") or "")
    channels = sorted({str(channel) for channel in payload.get("channels") or ["in_app"]})
    if not name or not metric_key:
        raise CustomerExperienceError("Alert name and metric are required")
    if operator not in ALERT_OPERATORS:
        raise CustomerExperienceError("Unsupported alert operator")
    if not channels or not set(channels).issubset(ALERT_CHANNELS):
        raise CustomerExperienceError("Unsupported alert channel")
    report_id = payload.get("report_id")
    if not report_id:
        raise CustomerExperienceError(
            "A dashboard is required so the alert can compute a verified metric"
        )
    _require_owned_report(client, user_id, str(report_id))
    row = {
        "user_id": user_id,
        "organization_id": payload.get("organization_id"),
        "workspace_id": payload.get("workspace_id"),
        "report_id": report_id,
        "name": name,
        "metric_key": metric_key,
        "operator": operator,
        "threshold": payload.get("threshold"),
        "filter_state": payload.get("filter_state") or {},
        "evaluation_interval_minutes": min(
            1440,
            max(1, int(payload.get("evaluation_interval_minutes") or 5)),
        ),
        "next_evaluation_at": _now(),
        "channels": channels,
        "recipients": payload.get("recipients") or [],
        "cooldown_minutes": min(43200, max(1, int(payload.get("cooldown_minutes") or 60))),
        "enabled": bool(payload.get("enabled", True)),
    }
    response = client.table("customer_alert_rules").insert(row).execute()
    return _first(response) or row


def update_alert_rule(
    user_id: str,
    rule_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    existing = _first(
        client.table("customer_alert_rules")
        .select("id")
        .eq("id", rule_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not existing:
        raise CustomerExperienceError("Alert rule was not found")
    update: dict[str, Any] = {"updated_at": _now()}
    for key in ("enabled", "muted_until"):
        if key in payload:
            update[key] = payload[key]
    response = (
        client.table("customer_alert_rules")
        .update(update)
        .eq("id", rule_id)
        .eq("user_id", user_id)
        .execute()
    )
    return _first(response) or {**existing, **update}


def upsert_integration(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    kind = str(payload.get("integration_kind") or "")
    status = str(payload.get("status") or "draft")
    provider = str(payload.get("provider") or "").strip().lower()[:80]
    name = str(payload.get("display_name") or "").strip()[:160]
    configuration = payload.get("configuration") or {}
    if kind not in INTEGRATION_KINDS or status not in INTEGRATION_STATUSES:
        raise CustomerExperienceError("Unsupported integration configuration")
    if not provider or not name:
        raise CustomerExperienceError("Provider and display name are required")
    _reject_secret_configuration(configuration)
    organization_id = payload.get("organization_id")
    if provider in ORGANIZATION_ONLY_PROVIDERS and not organization_id:
        raise CustomerExperienceError(
            f"{provider.upper()} integration requires an organization owner or admin"
        )
    if organization_id:
        _require_org_admin(client, user_id, str(organization_id))
    row = {
        "user_id": user_id,
        "organization_id": organization_id,
        "integration_kind": kind,
        "provider": provider,
        "display_name": name,
        "status": status,
        "enabled": bool(payload.get("enabled", False)),
        "configuration": configuration,
        "last_tested_at": payload.get("last_tested_at"),
        "last_error": str(payload.get("last_error") or "")[:2000] or None,
        "updated_at": _now(),
    }
    response = (
        client.table("customer_integration_settings")
        .upsert(
            row,
            on_conflict="user_id,integration_kind,provider,display_name",
        )
        .execute()
    )
    return _first(response) or row


def create_organization_invitation(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    organization_id = str(payload.get("organization_id") or "")
    _require_org_admin(client, user_id, organization_id)
    workspace_id = payload.get("workspace_id")
    _validate_workspace(client, organization_id, workspace_id)
    email = str(payload.get("email") or "").strip().lower()
    if len(email) > 320 or "@" not in email:
        raise CustomerExperienceError("A valid invitation email is required")
    role = str(payload.get("role") or "member")
    if role not in {"admin", "reviewer", "member"}:
        raise CustomerExperienceError("Unsupported organization role")
    expires_in_days = min(30, max(1, int(payload.get("expires_in_days") or 7)))
    token = secrets.token_urlsafe(32)
    row = {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "email": email,
        "role": role,
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "status": "pending",
        "invited_by": user_id,
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        ).isoformat(),
    }
    response = client.table("customer_organization_invitations").insert(row).execute()
    saved = _first(response) or row
    return {
        "invitation": {key: value for key, value in saved.items() if key != "token_hash"},
        "token": token,
    }


def accept_organization_invitation(
    user_id: str,
    token: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    safe_token = str(token or "").strip()
    if len(safe_token) < 32:
        raise CustomerExperienceError("Invitation token is invalid")
    token_hash = hashlib.sha256(safe_token.encode()).hexdigest()
    invitation = _first(
        client.table("customer_organization_invitations")
        .select("*")
        .eq("token_hash", token_hash)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if not invitation:
        raise CustomerExperienceError("Invitation is invalid or no longer active")
    expires_at = datetime.fromisoformat(str(invitation["expires_at"]).replace("Z", "+00:00"))
    if expires_at <= datetime.now(timezone.utc):
        client.table("customer_organization_invitations").update({
            "status": "expired",
            "updated_at": _now(),
        }).eq("id", invitation["id"]).execute()
        raise CustomerExperienceError("Invitation has expired")
    profile = _first(
        client.table("profiles")
        .select("email")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if str((profile or {}).get("email") or "").strip().lower() != invitation["email"]:
        raise CustomerExperienceError("Invitation email does not match the signed-in account")
    add_member(
        str(invitation["invited_by"]),
        str(invitation["organization_id"]),
        user_id,
        str(invitation["role"]),
        workspace_id=invitation.get("workspace_id"),
        client=client,
    )
    update = {
        "status": "accepted",
        "accepted_by": user_id,
        "accepted_at": _now(),
        "updated_at": _now(),
    }
    saved = _first(
        client.table("customer_organization_invitations")
        .update(update)
        .eq("id", invitation["id"])
        .eq("status", "pending")
        .execute()
    )
    if not saved:
        raise CustomerExperienceError("Invitation was already processed")
    advance_onboarding_fail_safe(user_id, "invite_team", client=client)
    return {key: value for key, value in saved.items() if key != "token_hash"}


def create_embed_config(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    report_id = str(payload.get("report_id") or "")
    _require_owned_report(client, user_id, report_id)
    origins = sorted(
        {
            str(origin).strip().rstrip("/")
            for origin in payload.get("allowed_origins") or []
            if str(origin).strip().startswith("https://")
        }
    )
    if not origins:
        raise CustomerExperienceError("At least one HTTPS embed origin is required")
    expires_in_days = payload.get("expires_in_days")
    expires_at = None
    if expires_in_days is not None:
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(days=min(365, max(1, int(expires_in_days))))
        ).isoformat()
    token = secrets.token_urlsafe(32)
    row = {
        "user_id": user_id,
        "organization_id": payload.get("organization_id"),
        "report_id": report_id,
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "allowed_origins": origins,
        "branding": payload.get("branding") or {},
        "status": "active",
        "expires_at": expires_at,
    }
    response = client.table("customer_embed_configs").insert(row).execute()
    saved = _first(response) or row
    return {
        "embed": {key: value for key, value in saved.items() if key != "token_hash"},
        "token": token,
    }


def advance_onboarding_fail_safe(
    user_id: str,
    *steps: str,
    first_dashboard_id: str | None = None,
    client: Any | None = None,
) -> None:
    """Add activation steps without allowing optional telemetry to break core work."""
    try:
        client = client or get_supabase_client()
        existing = _first(
            client.table("customer_onboarding_progress")
            .select("completed_steps,sample_dataset_loaded,first_dashboard_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        ) or {}
        completed = set(existing.get("completed_steps") or [])
        completed.update(step for step in steps if step in ONBOARDING_STEPS)
        save_onboarding_progress(
            user_id,
            {
                "completed_steps": sorted(completed),
                "sample_dataset_loaded": bool(
                    existing.get("sample_dataset_loaded")
                    or "sample_data" in completed
                ),
                "first_dashboard_id": (
                    first_dashboard_id
                    or existing.get("first_dashboard_id")
                ),
            },
            client=client,
        )
    except Exception:
        # This platform layer is additive until its migration is deployed.
        return


def record_asset_health_fail_safe(
    user_id: str,
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> None:
    try:
        upsert_data_asset(user_id, payload, client=client)
        advance_onboarding_fail_safe(
            user_id,
            "connect_data",
            client=client,
        )
    except Exception:
        return


def record_dashboard_lineage_fail_safe(
    user_id: str,
    report: dict[str, Any],
    *,
    client: Any | None = None,
) -> None:
    """Persist explainability records from schema-validated dashboard widgets."""
    try:
        client = client or get_supabase_client()
        report_id = str(report.get("id") or "")
        dataset_key = str(report.get("dataset_key") or "")
        if not report_id or not dataset_key:
            return
        spec = report.get("dashboard_spec") or {}
        widgets = spec.get("widgets") if isinstance(spec, dict) else []
        for widget in widgets or []:
            if not isinstance(widget, dict):
                continue
            config = widget.get("config") if isinstance(widget.get("config"), dict) else {}
            metric_key = (
                config.get("metric")
                or config.get("metric_key")
                or config.get("y")
                or widget.get("title")
            )
            if not metric_key:
                continue
            create_lineage_record(
                user_id,
                {
                    "report_id": report_id,
                    "dataset_key": dataset_key,
                    "metric_key": str(metric_key)[:160],
                    "formula": config.get("formula"),
                    "source_refs": [{
                        "kind": "dashboard_widget",
                        "widget_id": widget.get("id"),
                        "widget_kind": widget.get("kind"),
                    }],
                    "filter_state": spec.get("filters") or {},
                    "data_version": report.get("updated_at") or report.get("created_at"),
                    "confidence": 1,
                },
                client=client,
            )
        advance_onboarding_fail_safe(
            user_id,
            "first_dashboard",
            first_dashboard_id=report_id,
            client=client,
        )
    except Exception:
        return
