import logging
from typing import Any, Mapping, Optional

from fastapi import HTTPException, status
from postgrest.exceptions import APIError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.supabase import get_supabase_client
from app.schemas.chat import UserTier

logger = logging.getLogger("mataqorlab.quota")


def _is_transient_rpc_error(exc: Exception) -> bool:
    if isinstance(exc, APIError):
        return False
    msg = str(exc).lower()
    return (
        "timeout" in msg
        or "timed out" in msg
        or "connection" in msg
        or "503" in msg
        or "502" in msg
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    retry=retry_if_exception(_is_transient_rpc_error),
    reraise=True,
)
def _call_quota_rpc(function_name: str, params: dict) -> dict:
    supabase = get_supabase_client()
    result = supabase.rpc(function_name, params).execute()
    if result.data is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ระบบตรวจสอบโควตาชั่วคราวไม่พร้อม กรุณาลองใหม่อีกครั้ง",
        )
    payload = result.data
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ได้รับข้อมูลโควตาในรูปแบบที่ไม่ถูกต้อง",
        )
    return payload


def _raise_if_quota_error(payload: dict) -> None:
    if payload.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": payload.get("error", "Quota Exceeded"),
                "message": payload.get("message", "Quota exceeded"),
                "used": payload.get("used"),
                "limit": payload.get("limit"),
                "reset_at": payload.get("reset_at"),
            },
        )


async def check_user_message_quota(user_id: str) -> dict[str, Any]:
    """
    ตรวจสอบโควตาผ่าน Supabase RPC (refresh + plan limits) ก่อนประมวลผล AI
    """
    try:
        payload = _call_quota_rpc("check_user_message_quota", {"p_user_id": user_id})
    except APIError as exc:
        detail = str(exc).lower()
        if "profile_not_found" in detail or "p0002" in detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ไม่พบข้อมูลผู้ใช้งานในระบบ",
            )
        if "forbidden" in detail or "42501" in detail:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ไม่มีสิทธิ์ตรวจสอบโควตาของผู้ใช้นี้",
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ระบบตรวจสอบโควตาชั่วคราวไม่พร้อม กรุณาลองใหม่อีกครั้ง",
        )
    except HTTPException:
        raise
    except Exception as exc:
        if _is_transient_rpc_error(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ระบบตรวจสอบโควตาชั่วคราวไม่พร้อม กรุณาลองใหม่อีกครั้ง",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ไม่สามารถตรวจสอบข้อมูลสมาชิกได้ กรุณาตั้งค่าแผนการใช้งานของคุณให้เรียบร้อย",
        )

    _raise_if_quota_error(payload)
    return payload


def _tier_from_plan_name(plan_name: Any) -> UserTier:
    plan_name = str(plan_name or "free").strip().lower()
    if "pro" in plan_name or "enterprise" in plan_name:
        return UserTier.PRO
    if "plus" in plan_name:
        return UserTier.PLUS
    return UserTier.FREE


def get_user_tier(user_id: str) -> UserTier:
    """Resolve feature access from server-owned profile/plan rows; fail closed."""
    try:
        supabase = get_supabase_client()
        result = (
            supabase.table("profiles")
            .select("plan_id,plans(name)")
            .eq("id", user_id)
            .single()
            .execute()
        )
        row = result.data or {}
        plans = row.get("plans")
        if isinstance(plans, list):
            plans = plans[0] if plans else {}
        plan_name = plans.get("name") if isinstance(plans, dict) else None
        return _tier_from_plan_name(plan_name)
    except Exception as exc:
        print(f"Failed to resolve server-side tier for {user_id}: {exc}")
        return UserTier.FREE


async def record_token_usage(
    user_id: str,
    total_tokens: Optional[int],
    *,
    usage_type: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> None:
    """
    บันทึกการใช้ token หลังแชทสำเร็จ (Supabase RPC — refresh + atomic increment)

    Canonical quota path for all LLM usage including workflow_orchestrator.
    ``usage_type`` is classification metadata (logged); profile counters remain
    the single source of plan allowance enforcement.
    """
    tokens = int(total_tokens or 0)
    if tokens <= 0:
        return

    try:
        payload = _call_quota_rpc(
            "increment_profile_tokens",
            {"p_user_id": user_id, "p_tokens": tokens},
        )
        # Avoid reserved LogRecord keys (e.g. message) in extras.
        safe_meta = {
            (f"meta_{k}" if k in {"message", "msg", "args", "name", "levelname"} else k): v
            for k, v in dict(metadata or {}).items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
        logger.info(
            "token_usage_recorded",
            extra={
                "user_id": user_id,
                "tokens": tokens,
                "usage_type": usage_type or "analysis_chat",
                "status": payload.get("status"),
                **safe_meta,
            },
        )
        if payload.get("status") == "error":
            logger.warning(
                "token_increment_rejected",
                extra={
                    "user_id": user_id,
                    "usage_type": usage_type or "analysis_chat",
                    "detail": payload.get("message", "quota exceeded"),
                },
            )
    except Exception as exc:
        # Existing policy: log and continue — do not corrupt chat/workflow state.
        logger.warning(
            "token_usage_record_failed",
            extra={
                "user_id": user_id,
                "usage_type": usage_type or "analysis_chat",
                "error": str(exc)[:200],
            },
        )
