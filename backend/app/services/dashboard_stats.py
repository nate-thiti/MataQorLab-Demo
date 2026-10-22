"""Resilient owner-scoped dashboard statistics."""
from __future__ import annotations

import time
from typing import Any

from app.core.supabase import get_supabase_client


class DashboardStatsUnavailable(RuntimeError):
    pass


_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_SECONDS = 300


def get_dashboard_stats(
    user_id: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    try:
        response = client.rpc(
            "get_dashboard_stats",
            {"p_user_id": user_id},
        ).execute()
        data = dict(response.data or {})
        _CACHE[user_id] = (time.monotonic(), data)
        return data
    except Exception as exc:
        cached = _CACHE.get(user_id)
        if cached and time.monotonic() - cached[0] <= _CACHE_SECONDS:
            return {
                **cached[1],
                "stale": True,
                "warning": "Supabase is temporarily unreachable; showing recent statistics.",
            }
        raise DashboardStatsUnavailable(
            "Supabase is temporarily unreachable. Please retry shortly."
        ) from exc
