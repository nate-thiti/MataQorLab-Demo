"""Dead-letter queue for failed background jobs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.observability import correlation_id


class JobDlqError(ValueError):
    pass


def enqueue_dead_letter(
    client: Any,
    *,
    job_kind: str,
    job_key: str,
    error_message: str,
    payload: dict[str, Any] | None = None,
    error_code: str | None = None,
    user_id: str | None = None,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    attempt_count: int = 1,
) -> dict[str, Any] | None:
    row = {
        "job_kind": job_kind,
        "job_key": str(job_key)[:240],
        "error_message": str(error_message or "")[:4000],
        "error_code": str(error_code or "")[:120] or None,
        "payload": payload or {},
        "user_id": user_id,
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "attempt_count": max(1, int(attempt_count)),
        "status": "open",
        "correlation_id": correlation_id(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        existing = (
            client.table("job_dead_letters")
            .select("*")
            .eq("job_kind", job_kind)
            .eq("job_key", row["job_key"])
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        if existing.data:
            current = existing.data[0]
            response = (
                client.table("job_dead_letters")
                .update({
                    "error_message": row["error_message"],
                    "error_code": row["error_code"],
                    "payload": row["payload"],
                    "attempt_count": int(current.get("attempt_count") or 1) + 1,
                    "correlation_id": row["correlation_id"],
                    "updated_at": row["updated_at"],
                })
                .eq("id", current["id"])
                .execute()
            )
            return dict((response.data or existing.data)[0])
        response = client.table("job_dead_letters").insert(row).execute()
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as exc:
        if any(code in str(exc) for code in ("PGRST205", "42P01")):
            return None
        raise


def list_dead_letters(
    client: Any,
    *,
    status: str = "open",
    limit: int = 50,
) -> list[dict[str, Any]]:
    bounded = max(1, min(int(limit), 100))
    response = (
        client.table("job_dead_letters")
        .select("*")
        .eq("status", status)
        .order("created_at", desc=True)
        .limit(bounded)
        .execute()
    )
    return list(response.data or [])


def mark_dead_letter(
    client: Any,
    *,
    dead_letter_id: str,
    status: str,
) -> dict[str, Any]:
    if status not in {"open", "replaying", "resolved", "discarded"}:
        raise JobDlqError("Invalid dead-letter status")
    payload: dict[str, Any] = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if status in {"resolved", "discarded"}:
        payload["resolved_at"] = datetime.now(timezone.utc).isoformat()
    response = (
        client.table("job_dead_letters")
        .update(payload)
        .eq("id", dead_letter_id)
        .execute()
    )
    if not response.data:
        raise JobDlqError("Dead letter not found")
    return dict(response.data[0])


def dead_letter_depth(client: Any) -> int:
    try:
        response = (
            client.table("job_dead_letters")
            .select("id", count="exact")
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        return int(getattr(response, "count", None) or len(response.data or []))
    except Exception as exc:
        if any(code in str(exc) for code in ("PGRST205", "42P01")):
            return 0
        raise
