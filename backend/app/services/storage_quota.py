"""Unified customer storage quota checks backed by a locked Postgres RPC."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.supabase import get_supabase_client


class StorageQuotaExceeded(ValueError):
    pass


def get_customer_storage_usage(user_id: str) -> Dict[str, Any]:
    response = get_supabase_client().rpc(
        "get_customer_storage_usage", {"p_user_id": user_id}
    ).execute()
    return dict(response.data or {})


def enforce_customer_storage_quota(
    user_id: str,
    additional_bytes: int = 0,
    replacing_path: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        response = get_supabase_client().rpc(
            "enforce_customer_storage_quota",
            {
                "p_user_id": user_id,
                "p_additional_bytes": max(0, int(additional_bytes)),
                "p_replacing_path": replacing_path,
            },
        ).execute()
        return dict(response.data or {})
    except Exception as exc:
        if "quota exceeded" in str(exc).lower():
            raise StorageQuotaExceeded(
                "พื้นที่จัดเก็บตามแพ็กเกจไม่เพียงพอ กรุณาลบข้อมูลหรืออัปเกรดแพ็กเกจ"
            ) from exc
        raise
