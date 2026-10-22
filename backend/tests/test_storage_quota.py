from unittest.mock import MagicMock, patch

import pytest

from app.services.storage_quota import (
    StorageQuotaExceeded,
    enforce_customer_storage_quota,
    get_customer_storage_usage,
)


def test_get_customer_storage_usage_returns_rpc_payload():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = {
        "used_bytes": 123,
        "storage_bytes": 100,
        "database_bytes": 23,
        "limit_bytes": 1000,
    }
    with patch("app.services.storage_quota.get_supabase_client", return_value=client):
        usage = get_customer_storage_usage("user-1")
    assert usage["used_bytes"] == 123
    client.rpc.assert_called_once_with(
        "get_customer_storage_usage", {"p_user_id": "user-1"}
    )


def test_enforce_customer_storage_quota_passes_replacement_path():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = {"projected_bytes": 500}
    with patch("app.services.storage_quota.get_supabase_client", return_value=client):
        result = enforce_customer_storage_quota("user-1", 200, "user-1/data.csv")
    assert result["projected_bytes"] == 500
    client.rpc.assert_called_once_with(
        "enforce_customer_storage_quota",
        {
            "p_user_id": "user-1",
            "p_additional_bytes": 200,
            "p_replacing_path": "user-1/data.csv",
        },
    )


def test_enforce_customer_storage_quota_maps_quota_error():
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = RuntimeError(
        "Customer storage quota exceeded"
    )
    with patch("app.services.storage_quota.get_supabase_client", return_value=client):
        with pytest.raises(StorageQuotaExceeded):
            enforce_customer_storage_quota("user-1", 999)
