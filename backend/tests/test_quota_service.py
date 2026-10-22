"""Tests for quota_service RPC response handling."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import quota_service
from app.schemas.chat import UserTier


def test_raise_if_quota_error_raises_403():
    with pytest.raises(HTTPException) as exc:
        quota_service._raise_if_quota_error({
            "status": "error",
            "error": "Quota Exceeded",
            "message": "Daily limit reached",
            "used": 400000,
            "limit": 400000,
            "reset_at": "2026-07-02T00:00:00Z",
        })
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "Quota Exceeded"


def test_raise_if_quota_error_passes_ok():
    quota_service._raise_if_quota_error({"status": "ok", "used": 0})


def test_check_user_message_quota_success():
    with patch.object(
        quota_service,
        "_call_quota_rpc",
        return_value={"status": "ok", "used": 100, "limit": 200000},
    ):
        payload = asyncio.run(quota_service.check_user_message_quota("user-1"))
    assert payload["status"] == "ok"


def test_record_token_usage_logs_when_increment_rejected():
    with patch.object(
        quota_service,
        "_call_quota_rpc",
        return_value={
            "status": "error",
            "message": "Weekly limit of 200000 tokens reached (Free).",
        },
    ):
        with patch.object(quota_service.logger, "warning") as mock_warn:
            asyncio.run(quota_service.record_token_usage("user-1", 5000))
    assert mock_warn.called
    assert any(
        call.args and call.args[0] == "token_increment_rejected"
        for call in mock_warn.call_args_list
    )


def test_record_token_usage_skips_zero_tokens():
    with patch.object(quota_service, "_call_quota_rpc") as mock_rpc:
        asyncio.run(quota_service.record_token_usage("user-1", 0))
    mock_rpc.assert_not_called()


def test_get_user_tier_reads_server_owned_plan():
    client = MagicMock()
    result = MagicMock()
    result.data = {"plan_id": "plan-1", "plans": {"name": "Plus"}}
    (
        client.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute
    ).return_value = result

    with patch.object(quota_service, "get_supabase_client", return_value=client):
        assert quota_service.get_user_tier("user-1") is UserTier.PLUS


def test_get_user_tier_fails_closed():
    with patch.object(
        quota_service,
        "get_supabase_client",
        side_effect=RuntimeError("database unavailable"),
    ):
        assert quota_service.get_user_tier("user-1") is UserTier.FREE


def test_enterprise_resolves_to_pro_feature_tier():
    assert quota_service._tier_from_plan_name("Enterprise") is UserTier.PRO
