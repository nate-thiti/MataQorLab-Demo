"""Transactional, exact-once delivery of scheduled analysis into app chat."""
from __future__ import annotations

from typing import Any


class ScheduledChatDeliveryError(RuntimeError):
    pass


def deliver_chat_report(
    *,
    client: Any,
    user_id: str,
    schedule_id: str,
    run_id: str | None,
    fingerprint: str,
    narration: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = client.rpc(
            "deliver_scheduled_chat_message",
            {
                "p_user_id": user_id,
                "p_schedule_id": schedule_id,
                "p_run_id": run_id,
                "p_fingerprint": fingerprint,
                "p_content": narration,
                "p_response_metadata": metadata or {},
            },
        ).execute()
    except Exception as exc:
        raise ScheduledChatDeliveryError(str(exc)) from exc

    rows = response.data or []
    if not rows:
        raise ScheduledChatDeliveryError("Scheduled chat delivery returned no result")
    row = rows[0]
    return {
        "channel": "chat",
        "message_id": row.get("message_id"),
        "created": bool(row.get("created")),
    }
