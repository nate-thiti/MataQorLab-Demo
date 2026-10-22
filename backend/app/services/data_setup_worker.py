"""Durable recovery loop for approved adaptive Data Setup jobs."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.supabase import get_supabase_client
from app.services.data_setup import process_data_setup_session

logger = logging.getLogger("mataqorlab.data_setup_worker")


def _claim_batch(batch_size: int):
    client = get_supabase_client()
    limit = max(1, min(int(batch_size), 10))
    try:
        return client.rpc(
            "claim_data_setup_sessions", {"p_limit": limit}
        ).execute().data or []
    except Exception as exc:
        if "service_role required" not in str(exc):
            raise
        logger.warning(
            "data_setup_legacy_claim_fallback",
            extra={"error_code": "legacy_rpc_claim_guard"},
        )
        candidates = (
            client.table("data_setup_sessions")
            .select("id,user_id")
            .eq("status", "approved")
            .order("updated_at")
            .limit(limit)
            .execute()
            .data
            or []
        )
        claimed = []
        for candidate in candidates:
            response = (
                client.table("data_setup_sessions")
                .update({
                    "status": "processing",
                    "current_step": "processing",
                    "processing_progress": {"percent": 5, "stage": "claimed"},
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", candidate["id"])
                .eq("user_id", candidate["user_id"])
                .eq("status", "approved")
                .execute()
            )
            claimed.extend(response.data or [])
        return claimed


async def process_claimed_data_setup_batch(*, batch_size: int = 2) -> int:
    sessions = await asyncio.to_thread(_claim_batch, batch_size)
    if sessions:
        await asyncio.gather(*[
            asyncio.to_thread(
                process_data_setup_session,
                str(session["id"]),
                str(session["user_id"]),
            )
            for session in sessions
        ])
    return len(sessions)


async def data_setup_worker_loop(
    stop_event: asyncio.Event,
    *,
    poll_seconds: int = 10,
    batch_size: int = 2,
) -> None:
    """Claim queued work and recover jobs abandoned by a dead web process."""
    while not stop_event.is_set():
        try:
            await process_claimed_data_setup_batch(batch_size=batch_size)
        except Exception as exc:
            logger.error(
                "data_setup_worker_poll_failed",
                extra={"error_code": "worker_poll_failed", "error": str(exc)},
            )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(2, int(poll_seconds)))
        except asyncio.TimeoutError:
            pass
