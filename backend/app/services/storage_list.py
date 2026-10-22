"""Owner-scoped paginated inventory for business-data objects."""

from __future__ import annotations

from typing import Any

from app.core.supabase import get_supabase_client


def list_business_files(
    user_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    bounded_limit = max(1, min(int(limit), 100))
    bounded_offset = max(0, int(offset))
    options: dict[str, Any] = {
        "limit": bounded_limit + 1,
        "offset": bounded_offset,
        "sortBy": {"column": "created_at", "order": "desc"},
    }
    normalized_search = str(search or "").strip()[:200]
    if normalized_search:
        options["search"] = normalized_search
    rows = (
        client.storage.from_("business-data").list(user_id, options)
        or []
    )
    has_more = len(rows) > bounded_limit
    files = rows[:bounded_limit]
    return {
        "files": files,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "next_offset": bounded_offset + bounded_limit if has_more else None,
        "has_more": has_more,
    }
