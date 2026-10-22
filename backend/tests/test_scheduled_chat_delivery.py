from unittest.mock import MagicMock

import pytest

from app.services.scheduled_chat_delivery import (
    ScheduledChatDeliveryError,
    deliver_chat_report,
)


def test_chat_delivery_uses_transactional_rpc_and_reports_creation():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [
        {"message_id": "message-1", "created": True}
    ]

    result = deliver_chat_report(
        client=client,
        user_id="user-1",
        schedule_id="schedule-1",
        run_id="run-1",
        fingerprint="a" * 64,
        narration="Weekly analysis",
        metadata={"dataset_key": "sales.csv"},
    )

    client.rpc.assert_called_once_with(
        "deliver_scheduled_chat_message",
        {
            "p_user_id": "user-1",
            "p_schedule_id": "schedule-1",
            "p_run_id": "run-1",
            "p_fingerprint": "a" * 64,
            "p_content": "Weekly analysis",
            "p_response_metadata": {"dataset_key": "sales.csv"},
        },
    )
    assert result == {
        "channel": "chat",
        "message_id": "message-1",
        "created": True,
    }


def test_chat_delivery_fails_closed_when_rpc_returns_no_result():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = []

    with pytest.raises(ScheduledChatDeliveryError, match="no result"):
        deliver_chat_report(
            client=client,
            user_id="user-1",
            schedule_id="schedule-1",
            run_id=None,
            fingerprint="b" * 64,
            narration="Weekly analysis",
        )
